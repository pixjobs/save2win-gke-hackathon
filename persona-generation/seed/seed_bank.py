import json
import psycopg2
import uuid
import random
import bcrypt
from tqdm import tqdm
from pathlib import Path
import sys

# --- Configuration ---
DB_ACCOUNTS_CONFIG = {
    "host": "localhost", "port": 5432, "dbname": "accounts-db",
    "user": "accounts-admin", "password": "password"
}
DB_LEDGER_CONFIG = {
    "host": "localhost", "port": 5433, "dbname": "postgresdb",
    "user": "admin", "password": "password"
}

PERSONAS_FILE = "data/personas.json"
TRANSACTIONS_FILE = "data/transactions.json"
LOCAL_ROUTING_NUM = "123456789"

def load_json(path_str: str):
    path = Path(path_str)
    if not path.exists(): raise FileNotFoundError(f"Data file not found: {path}")
    with path.open("r", encoding="utf-8") as f: return json.load(f)

def hash_password_bcrypt(password: str) -> bytes:
    """Hashes the password using bcrypt, matching the userservice source code."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def seed_users_and_contacts(personas):
    """
    Connects to accounts-db and seeds users and contacts. For each user, it
    generates a random 10-digit accountid, which is the critical link to
    their transaction history.
    """
    print("\n--- Seeding Users and Contacts into accounts-db ---")
    user_map = {} # This will store username -> generated 10-digit accountid
    conn = None
    try:
        conn = psycopg2.connect(**DB_ACCOUNTS_CONFIG)
        cur = conn.cursor()
        print("✅ Connected to accounts-db.")
        
        cur.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE;")
        
        # Combine AI personas with the necessary utility/fictional accounts
        all_users_to_create = personas + [
            {"username": "testuser", "password": "password"},
            {"username": "employer_payroll", "password": "password123"},
            {"username": "landlord_llc", "password": "password123"},
            {"username": "city_power_water", "password": "password123"},
            {"username": "grocery_mart", "password": "password123"},
        ]
        
        for user_data in tqdm(all_users_to_create, desc="👤 Seeding Users"):
            username = user_data['username']
            password = user_data.get('password', 'password123')
            
            # 1. Generate the correct bcrypt hash.
            passhash = hash_password_bcrypt(password)
            
            # 2. Generate a random 10-digit accountid, the critical link.
            account_id = str(random.randrange(10**9, 10**10 - 1))
            user_map[username] = account_id
            
            # 3. Insert the complete user record.
            cur.execute(
                """INSERT INTO users (accountid, username, passhash, firstname, lastname, birthday, timezone, address, state, zip, ssn) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);""",
                (account_id, username, passhash, 'Demo', 'User', '1990-01-01', 'UTC', '123 Demo St', 'CA', '90210', '000-00-0000')
            )
            
            # 4. Create the required "self-contact" to ensure full application functionality.
            cur.execute(
                """INSERT INTO contacts (username, label, account_num, routing_num, is_external)
                   VALUES (%s, %s, %s, %s, %s);""",
                (username, 'My Checking Account', account_id, LOCAL_ROUTING_NUM, False)
            )
            
        conn.commit()
        print("✅ Users and contacts seeded successfully.")
        return user_map
    finally:
        if conn: conn.close()

def seed_transactions(transactions, user_map):
    """Connects to ledger-db and seeds transactions using the accountid map."""
    print("\n--- Seeding Transactions into ledger-db ---")
    conn = None
    try:
        conn = psycopg2.connect(**DB_LEDGER_CONFIG)
        cur = conn.cursor()
        print("✅ Connected to ledger-db.")
        
        cur.execute("TRUNCATE TABLE TRANSACTIONS RESTART IDENTITY;")
        
        for tx in tqdm(transactions, desc="💸 Seeding Transactions"):
            sender_id = user_map.get(tx.get("from_username"))
            recipient_id = user_map.get(tx.get("to_username"))
            if not sender_id or not recipient_id: continue
            amount_in_cents = int(float(tx['amount']) * 100)
            timestamp = tx.get('date', 'NOW()')
            cur.execute(
                """INSERT INTO TRANSACTIONS (FROM_ACCT, TO_ACCT, FROM_ROUTE, TO_ROUTE, AMOUNT, TIMESTAMP) 
                   VALUES (%s, %s, %s, %s, %s, %s);""", 
                (sender_id, recipient_id, LOCAL_ROUTING_NUM, LOCAL_ROUTING_NUM, amount_in_cents, timestamp)
            )
        conn.commit()
        print("✅ Transactions seeded successfully.")
    finally:
        if conn: conn.close()

def main():
    print("\n" + "="*50)
    print("🤖 Bank of Anthos Seeder (Source Code Aligned)")
    print("="*50)
    
    try:
        personas = load_json(PERSONAS_FILE)
        transactions = load_json(TRANSACTIONS_FILE)
        
        user_id_map = seed_users_and_contacts(personas)
        seed_transactions(transactions, user_id_map)

    except FileNotFoundError as e:
        print(f"\n🛑 FILE ERROR: {e}")
    except psycopg2.OperationalError as e:
        print(f"\n🛑 DATABASE CONNECTION ERROR: {e}")
        print("   Did you remember to start BOTH 'kubectl port-forward' commands?")
        sys.exit(1)
    except Exception as e:
        print(f"\n🛑 An unexpected error occurred: {e}")

    print("\n" + "="*50)
    print("🎉 All done! Databases are populated with a valid state.")
    print("   You MUST now restart the application pods to see the changes.")
    print("   Run: 'kubectl rollout restart deployment userservice balancereader transactionhistory frontend contacts -n boa'")
    print("="*50)

if __name__ == "__main__":
    main()