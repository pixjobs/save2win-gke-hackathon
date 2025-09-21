import os
import json
import random
import requests
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, Unauthorized

# --- Configuration ---
TRANSACTIONS_API_URL = "http://transactions.boa.svc.cluster.local/transactions"
app = Flask(__name__)

# ==============================================================================
#  NEW: DATA ENRICHMENT LOGIC
# ==============================================================================

# A library of realistic merchant profiles. This is our "knowledge base".
MERCHANT_PROFILES = [
    {"merchant": "The Coffee Spot", "category": "Food & Drink", "min_amt": -15, "max_amt": -5},
    {"merchant": "SuperMart Groceries", "category": "Groceries", "min_amt": -150, "max_amt": -40},
    {"merchant": "City Transit", "category": "Transportation", "min_amt": -30, "max_amt": -20},
    {"merchant": "Gas Station", "category": "Transportation", "min_amt": -70, "max_amt": -50},
    {"merchant": "Quick Eats", "category": "Restaurants", "min_amt": -40, "max_amt": -15},
    {"merchant": "Cinema Plex", "category": "Entertainment", "min_amt": -50, "max_amt": -30},
    {"merchant": "Online Store", "category": "Shopping", "min_amt": -200, "max_amt": -70},
]

def enrich_transactions(transactions):
    """
    This function takes the simple, stubbed transaction data from Bank of Anthos
    and transforms it into realistic, categorized data.
    """
    enriched = []
    for t in transactions:
        amount = t.get('amount', 0)
        
        # Handle deposits (positive amounts)
        if amount > 0:
            t['description'] = "Paycheck Deposit"
            t['category'] = "Income"
            t['merchant'] = "Your Employer"
            enriched.append(t)
            continue

        # Handle withdrawals (negative amounts) by matching to a merchant profile
        matched_profile = None
        for profile in MERCHANT_PROFILES:
            if profile['min_amt'] <= amount <= profile['max_amt']:
                matched_profile = profile
                break
        
        # If a profile is found, enrich the transaction
        if matched_profile:
            # Add some random cents to make it look real
            new_amount = amount + round(random.uniform(-0.99, 0), 2)
            
            enriched.append({
                "fromAccountNum": t.get('fromAccountNum'),
                "toAccountNum": t.get('toAccountNum'),
                "amount": new_amount,
                "timestamp": t.get('timestamp'),
                "description": matched_profile['merchant'], # Use the better description
                "category": matched_profile['category'],   # Add the new category
                "merchant": matched_profile['merchant']    # Add the new merchant
            })
        # If no profile matches, just pass the original transaction through
        else:
            enriched.append(t)
            
    return enriched


# ==============================================================================
#  API Endpoint
# ==============================================================================

@app.route('/v1/context/transactions', methods=['GET'])
def get_transaction_context():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        raise Unauthorized('Authorization header is required.')

    account_id = "1234567890" # Using a consistent demo account ID

    try:
        # 1. Fetch the RAW, STUBBED data from Bank of Anthos
        mcp_response = requests.get(
            TRANSACTIONS_API_URL,
            headers={'Authorization': auth_header},
            params={'account_id': account_id},
            timeout=5
        )
        mcp_response.raise_for_status()
        raw_transactions = mcp_response.json().get("transactions", [])

        # 2. Run the ENRICHMENT process on the raw data
        enriched_data = enrich_transactions(raw_transactions)

        # 3. Return the NEW, RICH data in the context bundle
        return jsonify({
            "ok": True,
            "context": {
                "provider": "bank-of-anthos-enriched",
                "type": "transaction_history",
                "accountId": account_id,
                "data": enriched_data
            }
        })

    except requests.RequestException as e:
        app.logger.error(f"Could not connect to Bank of Anthos: {e}")
        raise InternalServerError(f"Could not connect to Bank of Anthos: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)