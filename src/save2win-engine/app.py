import os
import re
import json
import base64
import hashlib
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, Unauthorized, BadRequest

# Vertex AI (project/location via env)
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    _HAS_VERTEX = True
except ImportError:
    _HAS_VERTEX = False
    print("[save2win] Warning: vertexai SDK not found. Disabling Gemini features.")

# JWT verify (RS256) with cryptography key objects
import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------
VERSION = os.getenv("VERSION", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
PORT = int(os.getenv("PORT", "8080"))

# Engine inputs
MCP_SERVICE_URL = os.getenv(
    "MCP_SERVICE_URL",
    "http://mcp-service.boa.svc.cluster.local/v1/context/transactions",
)
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "5.0"))

# JWT config (env-only)
JWT_ALG = os.getenv("JWT_ALG", "RS256")
JWT_PUBLIC_KEY_ENV = "JWT_PUBLIC_KEY"
JWT_PUBLIC_KEY_B64_ENV = "JWT_PUBLIC_KEY_B64"

# Gemini
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Flask
app = Flask(__name__)
# Use Flask's logger for consistent logging
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

# Try to init Vertex AI (no-op if not configured)
if _HAS_VERTEX:
    try:
        vertexai.init()  # respects env if set
        app.logger.info("Vertex AI initialized.")
    except Exception as e:
        app.logger.warning(f"Vertex AI init failed, Gemini features may be unavailable. Error: {e}")

# In-memory cache of loaded public key & fingerprint
_public_key_obj = None
_public_key_fingerprint = None


# ------------------------------------------------------------------------------
# JWT Helpers
# ------------------------------------------------------------------------------
def _load_public_key_from_env() -> Tuple[object, str]:
    pem_text = os.getenv(JWT_PUBLIC_KEY_ENV)
    if pem_text:
        pem_bytes = pem_text.replace("\\n", "\n").encode("utf-8")
    else:
        b64 = os.getenv(JWT_PUBLIC_KEY_B64_ENV)
        if not b64:
            raise RuntimeError("No JWT public key. Set JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_B64.")
        try:
            pem_bytes = base64.b64decode(b64)
        except Exception as e:
            raise RuntimeError(f"Invalid JWT_PUBLIC_KEY_B64: {e}")

    try:
        pub = load_pem_public_key(pem_bytes, backend=default_backend())
        der = pub.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        fp = hashlib.sha256(der).hexdigest()
        return pub, fp
    except Exception as e:
        raise RuntimeError(f"Failed to parse or fingerprint JWT public key (PEM): {e}")


def _get_public_key():
    global _public_key_obj, _public_key_fingerprint
    if _public_key_obj is None:
        try:
            _public_key_obj, _public_key_fingerprint = _load_public_key_from_env()
            app.logger.info(f"Loaded JWT public key. fp={_public_key_fingerprint}")
        except Exception as e:
            app.logger.error(f"FATAL: Could not load JWT public key: {e}")
            _public_key_obj = "KEY_NOT_FOUND"
            _public_key_fingerprint = None
    return _public_key_obj


def _decode_jwt(token: str) -> dict:
    public_key = _get_public_key()
    if public_key == "KEY_NOT_FOUND":
        raise InternalServerError("JWT verifier key not loaded.")
    try:
        return jwt.decode(token, public_key, algorithms=[JWT_ALG], options={"leeway": 5})
    except jwt.ExpiredSignatureError:
        app.logger.warning("JWT expired.")
        raise Unauthorized("Token expired.")
    except jwt.InvalidTokenError as e:
        app.logger.warning(f"JWT invalid: {e}")
        raise Unauthorized(f"Invalid token: {e}")


def _first_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------------------------------
# Transaction Normalization & Bucketing
# ------------------------------------------------------------------------------
def _tofloat(x, default=0.0):
    if x is None:
        return default
    try:
        # Handle string inputs which may have currency symbols or commas
        if isinstance(x, str):
            x = x.replace(",", "").replace("$", "").strip()
        return float(x)
    except (ValueError, TypeError):
        return default

def _parsetime(s):
    if not s:
        return None
    # Add support for more flexible ISO 8601 parsing
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass
    # Fallback to original formats
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return None

def _normalize_tx(raw):
    date = raw.get("date") or raw.get("time") or raw.get("timestamp")
    amt = raw.get("amount")
    typ = raw.get("type") or raw.get("category")
    lab = raw.get("label") or raw.get("description") or raw.get("merchant") or ""
    acct = raw.get("account") or raw.get("toAccountId") or raw.get("fromAccountId")

    amount_float = _tofloat(amt)

    if typ:
        t_lower = str(typ).lower()
        if "credit" in t_lower or "income" in t_lower or amount_float > 0:
            normalized_type = "Credit"
        else:
            normalized_type = "Debit"
    else:
        normalized_type = "Credit" if amount_float > 0 else "Debit"

    if normalized_type == "Credit" and amount_float < 0:
        amount_float = abs(amount_float)
    if normalized_type == "Debit" and amount_float > 0:
        amount_float = -amount_float

    return {
        "date": _parsetime(date),
        "type": normalized_type,
        "account": str(acct) if acct is not None else None,
        "label": str(lab),
        "amount": amount_float,
        "_raw": raw,
    }

KEYWORDS = {
    "coffee": ["coffee", "cafe", "starbucks", "peet", "blue bottle", "costa", "nero"],
    "groceries": ["grocery", "grocer", "market", "safeway", "tesco", "asda", "aldi", "lidl", "whole foods"],
    "transport": ["uber", "lyft", "taxi", "transport", "bus", "train", "tube", "metro"],
    "bills": ["utility", "utilities", "electric", "gas", "water", "internet", "phone", "bill"],
    "entertainment": ["netflix", "spotify", "cinema", "theatre", "concert", "amc"],
}

def _bucket_for(tx):
    label = (tx.get("label") or "").lower()
    if tx.get("type") == "Credit":
        return "Income"
    for bucket, words in KEYWORDS.items():
        if any(w in label for w in words):
            return bucket.capitalize()
    return "Other"

def _tx_to_json(t):
    return {
        "date": (t["date"].isoformat().replace("+00:00", "Z") if isinstance(t["date"], datetime) else None),
        "type": t["type"],
        "account": t["account"],
        "label": t["label"],
        "amount": round(t.get("amount", 0.0), 2),
    }

def _summarize(transactions):
    tx = [_normalize_tx(t) for t in transactions if isinstance(t, dict)]
    
    # --- START OF FIX ---
    # REMOVED: The aggressive filter that was deleting all transactions.
    # We will now pass through all transactions, even if their amount is zero.
    # tx = [t for t in tx if t["amount"] != 0.0]
    app.logger.info(f"Summarizing {len(tx)} normalized transactions.")
    # --- END OF FIX ---

    now = datetime.now(timezone.utc)
    for i, t in enumerate(tx):
        if t["date"] is None:
            t["date"] = now - timedelta(minutes=i)

    tx.sort(key=lambda x: x["date"], reverse=True)

    buckets = defaultdict(lambda: {"total": 0.0, "count": 0})
    for t in tx:
        b = _bucket_for(t)
        buckets[b]["total"] += t["amount"]
        buckets[b]["count"] += 1

    debits = [t for t in tx if t["amount"] < 0]
    credits = [t for t in tx if t["amount"] > 0]
    largest_debit = min(debits, key=lambda t: t["amount"], default=None)
    last_income = credits[0] if credits else None

    def _sum_amt(items):
        return round(sum(x["amount"] for x in items), 2)

    def _window(days):
        cutoff = now - timedelta(days=days)
        items = [t for t in tx if t["date"] >= cutoff]
        spend = _sum_amt([t for t in items if t["amount"] < 0])
        income = _sum_amt([t for t in items if t["amount"] > 0])
        return {"spend": spend, "income": income, "net": round(income + spend, 2)}

    stats_30d = _window(30)

    # --- START OF FIX ---
    # REMOVED: The hardcoded limit of 50 transactions.
    # The frontend will now receive all available transactions.
    recent = [_tx_to_json(t) for t in tx]
    # --- END OF FIX ---

    return {
        "recent": recent,
        "buckets": {k: {"total": round(v["total"], 2), "count": v["count"]} for k, v in sorted(buckets.items())},
        "highlights": {
            "largest_debit": (_tx_to_json(largest_debit) if largest_debit else None),
            "last_income": (_tx_to_json(last_income) if last_income else None),
        },
        "stats": {
            "last_7d": _window(7),
            "last_30d": stats_30d,
            "avg_daily_spend_30d": round(abs(stats_30d["spend"]) / 30.0, 2) if stats_30d["spend"] != 0 else 0.0,
        },
        "count": len(tx),
    }


# ------------------------------------------------------------------------------
# Game logic & AI helper
# ------------------------------------------------------------------------------
def apply_game_logic(transactions, ai_content):
    xp = 100
    badges = []
    if any("coffee" in (t.get("merchant") or t.get("label") or "").lower() for t in transactions):
        badges.append({"id": "coffee_crusader", "title": "Coffee Crusader"})
        xp += 250
    if any((t.get("category") == "Income") or (t.get("type") == "Credit") or (t.get("amount", 0) > 0)
           for t in transactions):
        badges.append({"id": "money_maker", "title": "Big Deposit!"})
        xp += 500
    return {
        "xp": xp,
        "level": 1,
        "quest": ai_content.get("quest", "No quest available."),
        "tip": ai_content.get("tip", "Save a little every day!"),
        "badges": badges,
    }

def _ai_or_fallback(transactions):
    fallback_content = {
        "quest": "The Frugal Foodie! Pack your lunch twice this week for 500 XP.",
        "tip": "Small swaps add up—try a homemade coffee this week.",
    }
    
    if not _HAS_VERTEX or not transactions:
        return fallback_content
        
    try:
        model = GenerativeModel(GEMINI_MODEL)
        prompt = (
            "You are a fun financial coach. "
            f"A user has these recent transactions: {json.dumps(transactions[:20])}.\n" # Limit prompt size
            'Return **only** a JSON object with exactly two keys:\n'
            '  "quest": A creative, one-week savings challenge based on the spending.\n'
            '  "tip": A short, motivational financial tip related to the transactions.\n'
        )
        resp = model.generate_content(prompt)
        ai_text = getattr(resp, "text", "")
        ai_content = _first_json_object(ai_text) or {}
        if "quest" in ai_content and "tip" in ai_content:
            return ai_content
        else:
            app.logger.warning("Gemini response was malformed, using fallback.")
            return fallback_content
    except Exception as e:
        # --- START OF FIX ---
        # IMPROVED LOGGING: Log the actual error to help debug auth/API issues.
        app.logger.error(f"Vertex AI call failed; using fallback. Error: {e}")
        # --- END OF FIX ---
        return fallback_content


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
def _get_transactions_from_mcp(headers, params):
    """Helper to fetch and parse transactions from MCP service."""
    try:
        mcp_resp = requests.get(
            MCP_SERVICE_URL,
            headers=headers,
            params=params,
            timeout=HTTP_TIMEOUT,
        )
        mcp_resp.raise_for_status()
        response_json = mcp_resp.json()
        transactions = response_json.get("context", {}).get("data", [])
        app.logger.info(f"Successfully fetched {len(transactions)} transactions from MCP.")
        return transactions
    except requests.RequestException as e:
        app.logger.error(f"Could not connect to MCP service: {e}")
        raise InternalServerError(f"Could not connect to MCP service: {e}")
    except json.JSONDecodeError as e:
        app.logger.error(f"Failed to decode JSON from MCP service: {e}")
        # Return empty list to prevent crash but log the error
        return []

@app.route("/api/v1/game-state", methods=["GET"])
def get_game_state():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise Unauthorized("Authorization header must be a Bearer token.")
    token = auth_header[len("Bearer "):].strip()

    decoded = _decode_jwt(token)
    account_id = decoded.get("acct")
    if not account_id:
        raise Unauthorized("JWT is valid but missing the 'acct' claim.")

    transactions = _get_transactions_from_mcp(
        headers={"Authorization": auth_header},
        params={"account_id": account_id}
    )
    ai_content = _ai_or_fallback(transactions)
    game_state = apply_game_logic(transactions, ai_content)
    return jsonify(game_state)

@app.route("/api/v1/game-state/summary", methods=["GET"])
def get_game_state_summary():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise Unauthorized("Authorization header must be a Bearer token.")
    token = auth_header[len("Bearer "):].strip()
    
    decoded = _decode_jwt(token)
    account_id = decoded.get("acct")
    if not account_id:
        raise Unauthorized("JWT is valid but missing the 'acct' claim.")

    transactions = _get_transactions_from_mcp(
        headers={"Authorization": auth_header},
        params={"account_id": account_id}
    )

    summary = _summarize(transactions)
    ai_content = _ai_or_fallback(transactions)
    game = apply_game_logic(transactions, ai_content)

    return jsonify({
        "account_id": account_id,
        "version": VERSION,
        "summary": summary,
        "game": game,
    })

@app.get("/health")
def health():
    key_ok = _get_public_key() != "KEY_NOT_FOUND"
    return jsonify({
        "ok": key_ok,
        "version": VERSION,
        "jwt_alg": JWT_ALG,
    }), (200 if key_ok else 500)