import json
import os
import random
from datetime import datetime, timedelta
import vertexai
from vertexai.generative_models import GenerativeModel, Part

# --- Configuration ---
PROJECT_ID = "gke-trial-472609"  # Your GCP project ID
LOCATION = "europe-west1"         # The region for your project
PERSONA_COUNT = 20                # How many unique users to create
OUTPUT_PERSONAS_FILE = "data/personas.json"
OUTPUT_TRANSACTIONS_FILE = "data/transactions.json"

def generate_personas():
    """Uses Gemini to generate realistic user personas."""

    vertexai.init(project=PROJECT_ID, location=LOCATION)
    model = GenerativeModel("gemini-2.5-pro")

    prompt = f"""
    Generate a list of {PERSONA_COUNT} realistic user personas based in the California, USA.

    Each persona must be a JSON object with the following fields:
    - "username": A unique, creative, lowercase username (e.g., "techguru88", "nycartist", "legalbeagle").
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

    Ensure the final output is a single, valid JSON array containing these {PERSONA_COUNT} persona objects. Do not include any text or markdown outside of the JSON array.
    """

    print("Generating personas with Vertex AI Gemini... (This may take a moment)")
    response = model.generate_content(prompt)
    
    try:
        # Clean up the response to extract only the JSON part
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        personas_data = json.loads(json_text)
        
        # Add a standard password for seeding purposes
        for persona in personas_data:
            persona["password"] = "password123"

        os.makedirs(os.path.dirname(OUTPUT_PERSONAS_FILE), exist_ok=True)
        with open(OUTPUT_PERSONAS_FILE, 'w') as f:
            json.dump(personas_data, f, indent=2)
        
        print(f"Successfully generated and saved {len(personas_data)} personas to {OUTPUT_PERSONAS_FILE}")
        return personas_data

    except (json.JSONDecodeError, AttributeError) as e:
        print(f"Error: Failed to parse Gemini response as JSON. Error: {e}")
        print("Raw response:", response.text)
        return None

def generate_transactions(personas):
    """Generates a 3-month transaction history based on persona patterns."""
    if not personas:
        print("No personas provided. Skipping transaction generation.")
        return

    transactions = []
    today = datetime.now()
    start_date = today - timedelta(days=90)
    usernames = [p["username"] for p in personas]

    for persona in personas:
        # --- Income ---
        for i in range(3): # Monthly income for 3 months
            transactions.append({
                "from_username": "employer_payroll", # A fictional source
                "to_username": persona["username"],
                "amount": persona["monthly_income"],
                "date": (start_date + timedelta(days=30*i + 1)).strftime('%Y-%m-%d')
            })
        
        # --- Recurring Expenses (Rent, Utilities) ---
        for i in range(3):
            # Rent
            transactions.append({
                "from_username": persona["username"],
                "to_username": "landlord_llc", # Fictional recipient
                "amount": persona["transaction_patterns"]["rent_mortgage"],
                "date": (start_date + timedelta(days=30*i + 5)).strftime('%Y-%m-%d')
            })
            # Utilities
            transactions.append({
                "from_username": persona["username"],
                "to_username": "city_power_water", # Fictional recipient
                "amount": persona["transaction_patterns"]["utilities"],
                "date": (start_date + timedelta(days=30*i + 15)).strftime('%Y-%m-%d')
            })

        # --- Variable Expenses (Groceries, etc.) ---
        for day in range(90):
            current_date = start_date + timedelta(days=day)
            # Weekly groceries
            if current_date.weekday() == 6: # Sunday
                transactions.append({
                    "from_username": persona["username"],
                    "to_username": "grocery_mart", # Fictional
                    "amount": round(persona["transaction_patterns"]["groceries"] * random.uniform(0.8, 1.2), 2),
                    "date": current_date.strftime('%Y-%m-%d')
                })
            
            # Random discretionary spending
            if random.random() < 0.2: # 20% chance of a discretionary spend each day
                transactions.append({
                    "from_username": persona["username"],
                    "to_username": random.choice(usernames), # Send money to another user
                    "amount": round(persona["transaction_patterns"]["discretionary"] / 30 * random.uniform(0.5, 5.0), 2),
                    "date": current_date.strftime('%Y-%m-%d')
                })

    os.makedirs(os.path.dirname(OUTPUT_TRANSACTIONS_FILE), exist_ok=True)
    with open(OUTPUT_TRANSACTIONS_FILE, 'w') as f:
        json.dump(transactions, f, indent=2)
    
    print(f"Successfully generated {len(transactions)} transactions to {OUTPUT_TRANSACTIONS_FILE}")


if __name__ == "__main__":
    generated_personas = generate_personas()
    generate_transactions(generated_personas)