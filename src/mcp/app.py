import os
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, Unauthorized, BadRequest

import vertexai
from vertexai.generative_models import GenerativeModel

# ---- Config (override via env) ----
PROJECT_ID = os.getenv("PROJECT_ID")                              # optional
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "europe-west1")
TRANSACTIONS_API_URL = os.getenv(
    "TRANSACTIONS_API_URL",
    "http://transactionhistory.boa.svc.cluster.local/transactions",
)
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash") # Note: You had gemini-1.5-flash before, updated to your latest version
MAX_TXNS_FOR_ENRICH = int(os.getenv("MAX_TXNS_FOR_ENRICH", "50"))
DISABLE_GEMINI = os.getenv("DISABLE_GEMINI", "false").lower() in ("1", "true", "yes")

# ---- Initialize Vertex ----
try:
    if not DISABLE_GEMINI:
        if PROJECT_ID:
            vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
        else:
            vertexai.init(location=VERTEX_LOCATION)
except Exception as e:
    # Don't crash the process if Vertex init fails; we can still serve /healthz
    print(f"[mcp] Vertex init warning: {e}")

# Reuse an HTTP session with retries for BoA calls
_session = requests.Session()
_retries = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)
_adapter = HTTPAdapter(max_retries=_retries)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

# Lazy model
_model = None
def _get_model():
    global _model
    if _model is None:
        _model = GenerativeModel(MODEL_NAME)
    return _model

app = Flask(__name__)

def _clean_and_validate_enriched(raw_text, fallback):
    """
    Accepts Gemini text, strips code fences, parses JSON, and returns
    a validated list of {merchant:str, category:str, amount:float, timestamp:?}
    Falls back to original transactions on error.
    """
    try:
        cleaned = (raw_text or "").replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned)
        if not isinstance(data, list):
            raise ValueError("Enriched payload is not a list")

        out = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            merchant = str(item.get("merchant", "")).strip()
            category = str(item.get("category", "")).strip()
            amount = item.get("amount", None)
            try:
                amount = float(amount)
            except Exception:
                continue
            row = {"merchant": merchant, "category": category, "amount": amount}
            # carry over timestamp if present in original
            if i < len(fallback) and isinstance(fallback[i], dict):
                ts = fallback[i].get("timestamp")
                if ts is not None:
                    row["timestamp"] = ts
            out.append(row)

        # Only accept if we got at least 1 valid row
        return out if out else fallback
    except Exception as e:
        app.logger.error(f"Enrichment JSON parse/validate failed: {e}")
        return fallback

def enrich_transactions_with_gemini(transactions):
    if DISABLE_GEMINI:
        return transactions

    # Limit the size of prompt
    txns = transactions[-MAX_TXNS_FOR_ENRICH:]

    try:
        prompt = (
            "You are a data enrichment specialist. Convert a list of bank transactions "
            "into a realistic, categorized list. For each item, invent a plausible "
            '"merchant", set a "category", and make "amount" realistic with cents. '
            'Return ONLY a valid JSON array of objects with keys ["merchant","category","amount"]. '
            "No extra text, no explanations.\n\n"
            f"Input: {json.dumps(txns)}"
        )
        model = _get_model()
        resp = model.generate_content(prompt)
        return _clean_and_validate_enriched(getattr(resp, "text", ""), txns)
    except Exception as e:
        app.logger.error(f"Gemini enrichment failed: {e}. Returning original data.")
        return transactions

# ---- Health endpoints for K8s probes ----
@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/")
def root():
    return jsonify({"service": "mcp-service", "status": "ok"}), 200

# ---- Main API ----
@app.get("/v1/context/transactions")
def get_transaction_context():
    auth_header = request.headers.get("Authorization")  # Optional depending on BoA setup

    # --- START OF PATCH: Rely on account_id from save2win-engine ---
    # The account_id is now expected as a query parameter from the upstream engine.
    account_id = request.args.get("account_id")

    # If the engine fails to provide the account_id, it's a bad request.
    if not account_id:
        app.logger.error("Request from engine is missing 'account_id' query parameter.")
        raise BadRequest("Missing 'account_id' query parameter.")
    # --- END OF PATCH ---

    try:
        headers = {"Accept": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header

        # Construct the URL with the account_id as a path variable, as required by transactionhistory.
        full_transactions_url = f"{TRANSACTIONS_API_URL}/{account_id}"

        r = _session.get(
            full_transactions_url,  # Use the correctly formatted URL
            headers=headers,
            # The 'params' argument is removed, as account_id is now in the path.
            timeout=5,
        )

        r.raise_for_status()
        payload = r.json()
        # The TransactionHistory service returns a list directly, not a dict with a "transactions" key.
        raw = payload if isinstance(payload, list) else []
        enriched = enrich_transactions_with_gemini(raw)

        return jsonify({
            "ok": True,
            "context": {
                "provider": "bank-of-anthos-ai-enriched",
                "type": "transaction_history",
                "accountId": account_id,
                "data": enriched
            }
        })
    except requests.RequestException as e:
        app.logger.error(f"Could not connect to Bank of Anthos: {e}")
        raise InternalServerError(f"Could not connect to Bank of Anthos: {e}")