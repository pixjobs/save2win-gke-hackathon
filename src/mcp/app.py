import os
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, BadRequest

# ---- Config (override via env) ----
# This service no longer needs AI-related configs.
# It only needs to know where to fetch data from.
TRANSACTIONS_API_URL = os.getenv(
    "TRANSACTIONS_API_URL",
    "http://transactionhistory.boa.svc.cluster.local/transactions",
)

# ---- Flask App Setup ----
app = Flask(__name__)
# Use Flask's logger for consistent logging
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

# ---- HTTP Session with Retries ----
# A resilient session for making calls to the downstream transactionhistory service.
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
    Fetches raw transaction data from the transactionhistory service and
    returns it directly without modification or enrichment.
    """
    account_id = request.args.get("account_id")
    if not account_id:
        app.logger.error("Request is missing 'account_id' query parameter.")
        raise BadRequest("Missing 'account_id' query parameter.")

    try:
        headers = {"Accept": "application/json"}
        # Pass through the Authorization header if it exists
        if auth_header := request.headers.get("Authorization"):
            headers["Authorization"] = auth_header

        # Construct the URL with the account_id as a path variable
        full_transactions_url = f"{TRANSACTIONS_API_URL}/{account_id}"
        app.logger.info(f"Fetching transactions for account '{account_id}' from {full_transactions_url}")

        r = _session.get(full_transactions_url, headers=headers, timeout=5.0)
        
        # Raise an exception for bad status codes (4xx or 5xx)
        r.raise_for_status()
        
        payload = r.json()

        # Robustly handle both direct list and object-wrapped list responses
        if isinstance(payload, list):
            raw_transactions = payload
        elif isinstance(payload, dict):
            raw_transactions = payload.get("transactions", [])
        else:
            raw_transactions = []
        
        app.logger.info(f"Successfully fetched and returning {len(raw_transactions)} raw transactions.")

        # Return the data in the expected context structure
        return jsonify({
            "ok": True,
            "context": {
                "provider": "bank-of-anthos", # Provider is now just the raw source
                "type": "transaction_history",
                "accountId": account_id,
                "data": raw_transactions  # Pass the raw data directly
            }
        })

    except requests.RequestException as e:
        app.logger.error(f"Could not connect to Bank of Anthos service: {e}")
        raise InternalServerError(f"Could not connect to downstream service: {e}")
    except json.JSONDecodeError as e:
        app.logger.error(f"Failed to decode JSON from upstream service: {e}")
        raise InternalServerError("Invalid response from downstream service.")