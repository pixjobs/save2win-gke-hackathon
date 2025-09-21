import json
import os
import random
from datetime import datetime, timedelta
import vertexai
from vertexai.generative_models import GenerativeModel

# --- Configuration ---
# IMPORTANT: Replace with your actual GCP Project ID and a supported Location.
PROJECT_ID = "gke-trial-472609"  # Your GCP project ID
LOCATION = "europe-west1"         # e.g., "us-central1", "europe-west1"
PERSONA_COUNT = 20                # How many unique users to create
OUTPUT_PERSONAS_FILE = "data/personas.json"
OUTPUT_TRANSACTIONS_FILE = "data/transactions.json"

# --- Fictional Merchant & Payee Lists for Enhanced Realism ---
MERCHANTS = {
    "groceries": ["GreenLeaf Grocers", "MegaMart", "The People's Market", "City Produce"],
    "cafes": ["The Daily Grind", "MeowCafe", "Aroma Mocha", "Bean Scene"],
    "restaurants": ["Gourmet Burger Kitchen", "The Golden Ladle", "Pizza Palace", "Sushi Station"],
    "shopping": ["Urban Threads", "Byte & Binge Electronics", "The Book Nook", "Home Harmony"],
    "entertainment": ["Cinephile Central", "Pixel Palace Arcade", "The Local Theater", "Starlight Bowl"],
    "transport": ["Metro Transit", "City Gas Co.", "RideNow Share", "Bay Bridge Toll"],
    "utilities": ["City Power & Water", "ConnectNet Internet", "SoCal Gas"],
    "subscriptions": ["Streamify", "Velocity Gym", "NewsNow Online", "FitFlex Yoga"],
    "healthcare": ["Community Health Clinic", "Citywide Pharmacy", "Dr. Eva's Office"],
    "education": ["State University Bookstore", "Online Learning Hub", "ProSkill Courses"],
    "charities": ["Hope Foundation", "Global Relief Fund", "Local Animal Shelter"],
    "insurance": ["SafeGuard Insurance", "Golden State Health", "AutoSecure Co."],
    "landlords": ["Oakwood Properties", "Cityscape Rentals LLC", "Golden Key Management"],
    "lenders": ["Federal Student Loan Servicing", "Capital Credit Bank"]
}

P2P_MEMOS = ["Dinner split 🍕", "Movie tickets 🎬", "Rent contribution", "Thanks for the coffee!", "Gift 🎁"]

def generate_personas():
    """Uses Gemini to generate realistic user personas."""
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        # Using a stable, well-known model version
        model = GenerativeModel("gemini-2.5-pro")
    except Exception as e:
        print(f"Error initializing Vertex AI. Please check your PROJECT_ID and LOCATION.")
        print(f"Underlying error: {e}")
        return None

    prompt = f"""
    Generate a list of {PERSONA_COUNT} realistic user personas based in California, USA.

    Each persona must be a JSON object with the following fields:
    - "username": A unique, creative, lowercase username (e.g., "techguru88", "sf_artist", "legalbeagle").
    - "age_group": One of "20s", "30s", or "50s".
    - "job_title": A realistic USA-specific job title that matches their age group.
      - For "20s": Use titles like "University Student", "Software Engineer I", "Marketing Coordinator", "Graphic Designer", "Barista".
      - For "30s": Use titles like "Product Manager", "Registered Nurse", "Senior Software Engineer", "Lawyer", "Architect".
      - For "50s": Use titles like "Doctor", "University Professor", "CEO", "Lead Architect", "Financial Advisor".
    - "monthly_income": A realistic monthly income in USD for their job title.
    - "transaction_patterns": A JSON object detailing typical monthly expenses. Include:
        - "rent_mortgage": A monthly housing cost.
        - "groceries": An average weekly grocery budget.
        - "utilities": A monthly utility cost (e.g., electricity, internet).
        - "transportation": A monthly transportation cost (e.g., gas, public transit).
        - "discretionary": A budget for shopping, dining, and entertainment.
        - "savings_percentage": A percentage of income they typically save each month.
        - "debt_payments": Monthly debt obligations (e.g., student loans, credit cards).
        - "holidays": An annual budget for vacations and holidays.
        - "insurance": Monthly insurance costs (e.g., health, car, home).
        - "subscriptions": Monthly costs for subscriptions (e.g., streaming services, gym).
        - "healthcare": Monthly healthcare expenses (e.g., medications, doctor visits).
        - "education": Monthly expenses related to education (e.g., courses, books).
        - "gifts_donations": Monthly budget for gifts and charitable donations.
        - "miscellaneous": A small buffer for unexpected expenses.

    Ensure the final output is a single, valid JSON array containing these {PERSONA_COUNT} persona objects. Do not include any text or markdown outside of the JSON array itself.
    """

    print("Generating personas with Vertex AI Gemini... (This may take a moment)")
    try:
        response = model.generate_content(prompt)
        # Robustly clean the response to extract only the JSON array
        json_text = response.text[response.text.find('['):response.text.rfind(']')+1]
        personas_data = json.loads(json_text)
        
        # Add a standard password for local seeding/testing purposes
        for persona in personas_data:
            persona["password"] = "password123"

        os.makedirs(os.path.dirname(OUTPUT_PERSONAS_FILE), exist_ok=True)
        with open(OUTPUT_PERSONAS_FILE, 'w') as f:
            json.dump(personas_data, f, indent=2)
        
        print(f"Successfully generated and saved {len(personas_data)} personas to {OUTPUT_PERSONAS_FILE}")
        return personas_data

    except (json.JSONDecodeError, AttributeError, ValueError) as e:
        print(f"Error: Failed to parse Gemini response as JSON. This can happen due to API variability.")
        print(f"Error details: {e}")
        if 'response' in locals():
            print("--- Raw Gemini Response ---")
            print(response.text)
            print("---------------------------")
        return None

def generate_transactions(personas):
    """Generates a 3-month transaction history based on persona patterns with enhanced realism."""
    if not personas:
        print("No personas provided. Skipping transaction generation.")
        return

    transactions = []
    today = datetime.now()
    start_date = today - timedelta(days=90)
    usernames = [p["username"] for p in personas]

    for persona in personas:
        patterns = persona.get("transaction_patterns", {})

        # --- Income ---
        for i in range(3):
            transactions.append({
                "from_username": "employer_payroll",
                "to_username": persona["username"],
                "amount": persona.get("monthly_income", 0),
                "description": "Monthly Salary",
                "date": (start_date + timedelta(days=30*i + random.randint(0, 2))).strftime('%Y-%m-%d')
            })

        # --- Recurring Monthly Fixed Expenses ---
        for i in range(3):
            base_date = start_date + timedelta(days=30*i)
            transactions.extend([
                {"from_username": persona["username"], "to_username": random.choice(MERCHANTS["landlords"]), "amount": patterns.get("rent_mortgage", 0), "description": "Monthly Rent", "date": (base_date + timedelta(days=random.randint(0, 2))).strftime('%Y-%m-%d')},
                {"from_username": persona["username"], "to_username": random.choice(MERCHANTS["utilities"]), "amount": patterns.get("utilities", 0), "description": "Utilities Bill", "date": (base_date + timedelta(days=random.randint(12, 16))).strftime('%Y-%m-%d')},
                {"from_username": persona["username"], "to_username": random.choice(MERCHANTS["lenders"]), "amount": patterns.get("debt_payments", 0), "description": "Loan Payment", "date": (base_date + timedelta(days=random.randint(18, 22))).strftime('%Y-%m-%d')},
                {"from_username": persona["username"], "to_username": random.choice(MERCHANTS["insurance"]), "amount": patterns.get("insurance", 0), "description": "Insurance Premium", "date": (base_date + timedelta(days=random.randint(3, 6))).strftime('%Y-%m-%d')},
                {"from_username": persona["username"], "to_username": random.choice(MERCHANTS["subscriptions"]), "amount": round(patterns.get("subscriptions", 0) * random.uniform(0.9, 1.1), 2), "description": "Subscription Service", "date": (base_date + timedelta(days=random.randint(8, 28))).strftime('%Y-%m-%d')}
            ])

        # --- Variable Daily/Weekly Expenses over 90 days ---
        for day in range(90):
            current_date = start_date + timedelta(days=day)
            
            # Weekly Groceries (e.g., on a weekend)
            if current_date.weekday() in [5, 6] and random.random() < 0.8: # 80% chance on a weekend
                merchant = random.choice(MERCHANTS["groceries"])
                transactions.append({
                    "from_username": persona["username"], "to_username": merchant,
                    "amount": round(patterns.get("groceries", 50) * random.uniform(0.7, 1.3), 2),
                    "description": f"Grocery shopping at {merchant}", "date": current_date.strftime('%Y-%m-%d')
                })

            # Daily small spends (e.g., coffee, transport)
            if random.random() < 0.4: # 40% chance of a small spend each day
                category = random.choice(["cafes", "transport"])
                merchant = random.choice(MERCHANTS[category])
                amount = round(random.uniform(3, 15) if category == "cafes" else random.uniform(5, 25), 2)
                transactions.append({
                    "from_username": persona["username"], "to_username": merchant, "amount": amount,
                    "description": f"{category.capitalize()} at {merchant}", "date": current_date.strftime('%Y-%m-%d')
                })

            # Occasional discretionary & other spends
            if random.random() < 0.15: # 15% chance of a larger, non-essential spend
                category = random.choice(["restaurants", "shopping", "entertainment", "healthcare", "gifts_donations", "education"])
                merchant = random.choice(MERCHANTS.get(category, ["Misc Merchant"]))
                base_amount = patterns.get(category, patterns.get("discretionary", 50) / 4) # Fallback to discretionary
                amount = round(base_amount * random.uniform(0.3, 1.5), 2)
                transactions.append({
                    "from_username": persona["username"], "to_username": merchant, "amount": amount,
                    "description": f"Purchase at {merchant}", "date": current_date.strftime('%Y-%m-%d')
                })
            
            # Peer-to-peer transaction
            if random.random() < 0.05: # 5% chance of a P2P transaction
                # Exclude self from recipient list
                other_users = [u for u in usernames if u != persona["username"]]
                if other_users:
                    recipient = random.choice(other_users)
                    transactions.append({
                        "from_username": persona["username"], "to_username": recipient,
                        "amount": round(random.uniform(10, 100), 2),
                        "description": random.choice(P2P_MEMOS), "date": current_date.strftime('%Y-%m-%d')
                    })

    # Filter out any zero-amount transactions that might have been created due to missing persona data
    final_transactions = [t for t in transactions if t.get("amount", 0) > 0]

    os.makedirs(os.path.dirname(OUTPUT_TRANSACTIONS_FILE), exist_ok=True)
    with open(OUTPUT_TRANSACTIONS_FILE, 'w') as f:
        json.dump(final_transactions, f, indent=2)
    
    print(f"Successfully generated {len(final_transactions)} realistic transactions to {OUTPUT_TRANSACTIONS_FILE}")

if __name__ == "__main__":
    generated_personas = generate_personas()
    if generated_personas:
        generate_transactions(generated_personas)