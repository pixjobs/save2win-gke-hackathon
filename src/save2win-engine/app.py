import os
import json
import requests
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, Unauthorized
import vertexai
from vertexai.generative_models import GenerativeModel

# Initialize Vertex AI. It automatically discovers the project and location.
vertexai.init()

MCP_SERVICE_URL = "http://mcp-service.boa.svc.cluster.local/v1/context/transactions"
app = Flask(__name__)

def apply_game_logic(transactions, ai_content):
    xp = 100
    badges = []
    if any("coffee" in t.get("merchant", "").lower() for t in transactions):
        badges.append({"id": "coffee_crusader", "title": "Coffee Crusader"})
        xp += 250
    if any(t.get("category") == "Income" for t in transactions):
         badges.append({"id": "money_maker", "title": "Big Deposit!"})
         xp += 500
    return { "xp": xp, "level": 1, "quest": ai_content.get("quest", "No quest available."), "tip": ai_content.get("tip", "Save a little every day!"), "badges": badges }

@app.route('/api/v1/game-state', methods=['GET'])
def get_game_state():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        raise Unauthorized('Authorization header is required.')
    account_id = "1234567890" 
    try:
        mcp_response = requests.get(
            MCP_SERVICE_URL, headers={'Authorization': auth_header},
            params={'account_id': account_id}, timeout=5
        )
        mcp_response.raise_for_status()
        transactions = mcp_response.json().get("context", {}).get("data", [])
    except requests.RequestException as e:
        app.logger.error(f"Could not connect to MCP service: {e}")
        raise InternalServerError(f"Could not connect to MCP service: {e}")
    try:
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
    game_state = apply_game_logic(transactions, ai_content)
    return jsonify(game_state)

# The problematic "if __name__ == '__main__'" block has been removed.