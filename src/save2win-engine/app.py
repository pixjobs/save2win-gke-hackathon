import os
import re
import json
import base64
import hashlib
import logging
from typing import Optional, Tuple

import requests
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, Unauthorized

# Vertex AI (leave your existing project/location config in env)
import vertexai
from vertexai.generative_models import GenerativeModel

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
JWT_ALG = os.getenv("JWT_ALG", "RS256")  # should be RS256 for the token you shared
JWT_PUBLIC_KEY_ENV = "JWT_PUBLIC_KEY"
JWT_PUBLIC_KEY_B64_ENV = "JWT_PUBLIC_KEY_B64"

# Gemini
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Init Vertex AI (project/location can be provided via env; this is a no-op otherwise)
try:
    vertexai.init()
except Exception as _e:
    # Don't crash the app if Vertex init is not ready at boot; we handle errors per-request
    pass

# Flask
app = Flask(__name__)
logging.basicConfig(level=LOG_LEVEL)

# In-memory cache of loaded public key & fingerprint
_public_key_obj = None
_public_key_fingerprint = None


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _load_public_key_from_env() -> Tuple[object, str]:
    """
    Load RSA public key (PEM) from env. Supports:
      - JWT_PUBLIC_KEY       : PEM text (real newlines or '\n')
      - JWT_PUBLIC_KEY_B64   : base64 of the PEM
    Returns (public_key_object, sha256_fingerprint_hex)
    Raises RuntimeError if not found/invalid.
    """
    pem_text = os.getenv(JWT_PUBLIC_KEY_ENV)
    if pem_text:
        # tolerate escaped newlines
        pem_bytes = pem_text.replace("\\n", "\n").encode("utf-8")
    else:
        b64 = os.getenv(JWT_PUBLIC_KEY_B64_ENV)
        if not b64:
            raise RuntimeError(
                "No JWT public key provided. Set JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_B64."
            )
        try:
            pem_bytes = base64.b64decode(b64)
        except Exception as e:
            raise RuntimeError(f"Invalid JWT_PUBLIC_KEY_B64: {e}")

    try:
        pub = load_pem_public_key(pem_bytes, backend=default_backend())
    except Exception as e:
        raise RuntimeError(f"Failed to parse JWT public key (PEM): {e}")

    # Compute a stable fingerprint for health/debug
    try:
        der = pub.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        fp = hashlib.sha256(der).hexdigest()
    except Exception as e:
        raise RuntimeError(f"Failed to fingerprint public key: {e}")

    return pub, fp


def _get_public_key():
    """Cached getter for the public key object."""
    global _public_key_obj, _public_key_fingerprint
    if _public_key_obj is None:
        try:
            _public_key_obj, _public_key_fingerprint = _load_public_key_from_env()
            app.logger.info(
                f"Loaded JWT public key from environment. fp={_public_key_fingerprint}"
            )
        except Exception as e:
            app.logger.error(f"FATAL: {e}")
            _public_key_obj = "KEY_NOT_FOUND"
            _public_key_fingerprint = None
    return _public_key_obj


def _decode_jwt(token: str) -> dict:
    """Decode & verify the JWT. Raises Unauthorized on validation errors."""
    public_key = _get_public_key()
    if public_key == "KEY_NOT_FOUND":
        raise InternalServerError("JWT verifier key not loaded.")

    try:
        # small leeway for tiny clock skew
        return jwt.decode(
            token,
            public_key,
            algorithms=[JWT_ALG],
            options={"leeway": 5},
            # If you later add iss/aud, pass issuer=... , audience=... here
        )
    except jwt.ExpiredSignatureError:
        app.logger.warning("JWT expired.")
        raise Unauthorized("Token expired.")
    except jwt.InvalidTokenError as e:
        app.logger.warning(f"JWT invalid: {e}")
        raise Unauthorized(f"Invalid token: {e}")


def _first_json_object(text: str) -> Optional[dict]:
    """Extract the first JSON object from a free-form LLM response."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def apply_game_logic(transactions, ai_content):
    xp = 100
    badges = []
    if any("coffee" in t.get("merchant", "").lower() for t in transactions):
        badges.append({"id": "coffee_crusader", "title": "Coffee Crusader"})
        xp += 250
    if any(t.get("category") == "Income" for t in transactions):
        badges.append({"id": "money_maker", "title": "Big Deposit!"})
        xp += 500
    return {
        "xp": xp,
        "level": 1,
        "quest": ai_content.get("quest", "No quest available."),
        "tip": ai_content.get("tip", "Save a little every day!"),
        "badges": badges,
    }


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------
@app.route("/api/v1/game-state", methods=["GET"])
def get_game_state():
    # Prefer Authorization header (Next.js proxy forwards the cookie as Bearer)
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise Unauthorized("Authorization header is required.")

    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        raise Unauthorized("Authorization header must be Bearer token.")
    token = auth_header[len(prefix) :].strip()

    # 1) Verify JWT; require 'acct' claim
    try:
        decoded = _decode_jwt(token)
        account_id = decoded.get("acct")
        if not account_id:
            raise Unauthorized("JWT is valid but missing the 'acct' claim.")
    except (Unauthorized, InternalServerError):
        raise
    except Exception as e:
        app.logger.error(f"Unexpected error in JWT verification: {e}")
        raise InternalServerError("Failed to process authentication token.")

    # 2) Fetch MCP context (transactions) — pass through same Authorization
    try:
        mcp_resp = requests.get(
            MCP_SERVICE_URL,
            headers={"Authorization": auth_header},
            params={"account_id": account_id},
            timeout=HTTP_TIMEOUT,
        )
        mcp_resp.raise_for_status()
        transactions = mcp_resp.json().get("context", {}).get("data", [])
    except requests.RequestException as e:
        app.logger.error(f"Could not connect to MCP service: {e}")
        raise InternalServerError(f"Could not connect to MCP service: {e}")
    except Exception as e:
        app.logger.error(f"MCP response parsing failed: {e}")
        transactions = []

    # 3) Generate coaching quest & tip (best-effort; fall back on error)
    try:
        model = GenerativeModel(GEMINI_MODEL)
        prompt = (
            "You are a fun financial coach. "
            f"A user has these recent transactions: {transactions}.\n"
            'Return **only** a JSON object with exactly two keys:\n'
            '  "quest": A creative, one-week savings challenge.\n'
            '  "tip": A short, motivational financial tip.\n'
        )
        resp = model.generate_content(prompt)
        ai_text = (getattr(resp, "text", "") or "").replace("```json", "").replace("```", "").strip()
        ai_content = _first_json_object(ai_text) or {}
    except Exception as e:
        app.logger.error(f"Vertex AI call failed, using fallback content. Error: {e}")
        ai_content = {}

    if "quest" not in ai_content or "tip" not in ai_content:
        ai_content = {
            "quest": "The Frugal Foodie! Pack your lunch twice this week for 500 XP.",
            "tip": "Small swaps add up—try a homemade coffee this week.",
        }

    # 4) Apply game logic & respond
    game_state = apply_game_logic(transactions, ai_content)
    return jsonify(game_state)


@app.get("/health")
def health():
    ok = _get_public_key() != "KEY_NOT_FOUND"
    return jsonify(
        {
            "ok": ok,
            "version": VERSION,
            "jwt_alg": JWT_ALG,
        }
    ), (200 if ok else 500)


@app.get("/health/jwt")
def health_jwt():
    # Expose the fingerprint (not the key)
    key = _get_public_key()
    if key == "KEY_NOT_FOUND":
        return jsonify({"ok": False, "error": "key_not_loaded"}), 500
    return jsonify(
        {
            "ok": True,
            "alg": JWT_ALG,
            "fingerprint_sha256": _public_key_fingerprint,
        }
    )
