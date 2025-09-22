import os
import json
import requests
from flask import Flask, jsonify, request
from werkzeug.exceptions import InternalServerError, Unauthorized
import vertexai
from vertexai.generative_models import GenerativeModel

# --- Corrected Imports for JWT Decoding ---
import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.backends import default_backend
# -----------------------------------

vertexai.init()

MCP_SERVICE_URL = "http://mcp-service.boa.svc.cluster.local/v1/context/transactions"
app = Flask(__name__)

# --- JWT Verifier Setup ---
PUBLIC_KEY_PATH = os.getenv("PUB_KEY_PATH", "/var/private/boa_jwt_key.pub")
_public_key = None

def _get_public_key():
    """Loads the RSA public key from a file to verify JWTs."""
    global _public_key
    if _public_key is None:
        try:
            with open(PUBLIC_KEY_PATH, "rb") as key_file:
                # --- FIX: Use the correct function to load a public key directly ---
                _public_key = load_pem_public_key(key_file.read(), default_backend())
            app.logger.info(f"Successfully loaded public key from {PUBLIC_KEY_PATH}")
        except FileNotFoundError:
            app.logger.error(f"FATAL: Public key file not found at {PUBLIC_KEY_PATH}. JWT verification will fail.")
            _public_key = "KEY_NOT_FOUND"
        except Exception as e:
            app.logger.error(f"FATAL: Error loading public key: {e}")
            _public_key = "KEY_NOT_FOUND"
    return _public_key

def _decode_jwt(token):
    """Decodes and verifies the JWT, returning the payload."""
    public_key = _get_public_key()
    if public_key == "KEY_NOT_FOUND":
        raise InternalServerError("Public key for JWT verification not loaded.")

    try:
        decoded = jwt.decode(token, public_key, algorithms=["RS256"])
        return decoded
    except jwt.ExpiredSignatureError:
        app.logger.warning("JWT verification failed: Token has expired.")
        raise Unauthorized("Token expired.")
    except jwt.InvalidTokenError as e:
        app.logger.warning(f"JWT verification failed: {e}")
        raise Unauthorized(f"Invalid token: {e}")
# -----------------------------------


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

    token_prefix = "Bearer "
    if not auth_header.startswith(token_prefix):
        raise Unauthorized('Authorization header must be Bearer token.')
    token = auth_header[len(token_prefix):]

    try:
        decoded_token = _decode_jwt(token)
        account_id = decoded_token.get("acct")
        if not account_id:
            raise Unauthorized("JWT is valid but missing the 'acct' claim.")
    except (Unauthorized, InternalServerError) as e:
        raise e
    except Exception as e:
        app.logger.error(f"An unexpected error occurred during JWT decoding: {e}")
        raise InternalServerError("Failed to process authentication token.")

    try:
        mcp_response = requests.get(
            MCP_SERVICE_URL, headers={'Authorization': auth_header},
            params={'account_id': account_id},
            timeout=5
        )
        mcp_response.raise_for_status()
        transactions = mcp_response.json().get("context", {}).get("data", [])
    except requests.RequestException as e:
        app.logger.error(f"Could not connect to MCP service: {e}")
        raise InternalServerError(f"Could not connect to MCP service: {e}")
    try:
        model = GenerativeModel("gemini-2.5-flash")
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