import os
import json
import requests
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, Unauthorized

# Import the official Vertex AI library
import vertexai
from vertexai.generative_models import GenerativeModel

# --- Configuration ---
# Get Project and Region from environment variables.
# These are automatically available in the GKE environment.
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
REGION = os.environ.get("GCP_REGION")

if not PROJECT_ID or not REGION:
    raise RuntimeError("FATAL: GCP_PROJECT_ID and GCP_REGION env vars are required.")

# Internal Kubernetes DNS names for microservice communication
# The .boa namespace is critical for service discovery.
MCP_SERVICE_URL = "http://mcp-service.boa.svc.cluster.local/v1/context/transactions"

# Initialize Vertex AI. Because we are using Workload Identity,
# it automatically authenticates with the pod's service account. No API key needed.
vertexai.init(project=PROJECT_ID, location=REGION)

app = Flask(__name__)

# --- Core Game Logic (No changes needed here) ---
def apply_game_logic(transactions, ai_content):
    """Applies deterministic game logic to the AI-generated content."""
    xp = 100
    badges = []
    if any("coffee" in t.get("description", "").lower() for t in transactions):
        badges.append({"id": "coffee_crusader", "title": "Coffee Crusader"})
        xp += 250
    if any(t.get("amount", 0) > 500 for t in transactions):
         badges.append({"id": "money_maker", "title": "Big Deposit!"})
         xp += 500
    return { "xp": xp, "level": 1, "quest": ai_content.get("quest", "No quest available."), "tip": ai_content.get("tip", "Save a little every day!"), "badges": badges }

# --- Main API Endpoint ---
@app.route('/api/v1/game-state', methods=['GET'])
def get_game_state():
    """The main endpoint called by the frontend to get the user's game state."""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        raise Unauthorized('Authorization header is required.')

    account_id = "1234567890" 

    # 1. Call MCP to get transaction context
    try:
        mcp_response = requests.get(
            MCP_SERVICE_URL,
            headers={'Authorization': auth_header},
            params={'account_id': account_id},
            timeout=5
        )
        mcp_response.raise_for_status()
        transactions = mcp_response.json().get("context", {}).get("data", [])
    except requests.RequestException as e:
        app.logger.error(f"Could not connect to MCP service: {e}")
        raise InternalServerError(f"Could not connect to MCP service: {e}")

    # 2. Call Vertex AI Gemini for creative content
    try:
        # Use a modern, fast Vertex AI model
        model = GenerativeModel("gemini-1.5-flash-001")
        prompt = f"""
        You are a fun financial coach. A user has these recent transactions: {transactions}.
        Based on this, generate a valid JSON object with two keys only:
        1. "quest": A creative, one-week savings challenge.
        2. "tip": A short, motivational financial tip.
        """
        response = model.generate_content(prompt)
        ai_text_content = response.text.replace("```json", "").replace("```", "").strip()
        ai_content = json.loads(ai_text_content)
    except Exception as e:
        app.logger.error(f"Vertex AI call failed, using fallback content. Error: {e}")
        ai_content = {
            "quest": "The Frugal Foodie! Try packing your lunch twice this week for 500 XP.",
            "tip": "Did you know that packing your lunch can save you over $100 a month?"
        }

    # 3. Apply game logic and return the final state
    game_state = apply_game_logic(transactions, ai_content)
    return jsonify(game_state)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)