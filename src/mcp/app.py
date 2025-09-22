import os
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, BadRequest

# ---- Config (override via env) ----
TRANSACTIONS_API_URL = os.getenv(
    "TRANSACTIONS_API_URL",
    "http://transactionhistory.boa.svc.cluster.local/transactions",
)

# ---- Flask App Setup ----
app = Flask(__name__)
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

# ---- HTTP Session with Retries ----
_session = requests.Session()
_retries = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
_adapter = HTTPAdapter(max_retries=_retries)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


# ---- Health Endpoints ----
@app.get("/healthz")
@app.get("/health")
def healthz():
    return "ok", 200

@app.get("/")
def root():
    return jsonify({"service": "mcp-service", "status": "ok"}), 200


# ---- Main API Endpoint ----
@app.get("/v1/context/transactions")
def get_transaction_context():
    """
    Fetches raw transaction data from the transactionhistory service for a
    specific account_id and returns it directly.
    """
    account_id = request.args.get("account_id")
    if not account_id:
        app.logger.error("Request is missing 'account_id' query parameter.")
        raise BadRequest("Missing 'account_id' query parameter.")

    try:
        headers = {"Accept": "application/json"}
        if auth_header := request.headers.get("Authorization"):
            headers["Authorization"] = auth_header

        # The URL is correctly constructed with the account_id in the path.
        full_transactions_url = f"{TRANSACTIONS_API_URL}/{account_id}"
        app.logger.info(f"Fetching transactions for account '{account_id}' from {full_transactions_url}")

        # --- START OF FIX ---
        # The incorrect 'params' argument has been removed.
        # The requests library will now make the GET request to the exact URL
        # specified in full_transactions_url, which is the correct behavior.
        r = _session.get(
            full_transactions_url, 
            headers=headers, 
            timeout=5.0
        )
        # --- END OF FIX ---
        
        r.raise_for_status()
        
        payload = r.json()

        if isinstance(payload, list):
            raw_transactions = payload
        elif isinstance(payload, dict):
            raw_transactions = payload.get("transactions", [])
        else:
            raw_transactions = []
        
        app.logger.info(f"Successfully fetched {len(raw_transactions)} transactions for account {account_id}.")

        return jsonify({
            "ok": True,
            "context": {
                "provider": "bank-of-anthos",
                "type": "transaction_history",
                "accountId": account_id,
                "data": raw_transactions
            }
        })

    except requests.RequestException as e:
        app.logger.error(f"Could not connect to Bank of Anthos service: {e}")
        raise InternalServerError(f"Could not connect to downstream service: {e}")
    except json.JSONDecodeError as e:
        app.logger.error(f"Failed to decode JSON from upstream service: {e}")
        raise InternalServerError("Invalid response from downstream service.")