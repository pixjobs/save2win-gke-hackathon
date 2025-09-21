# AI‑Powered Persona & Transaction Seeder for **Bank of Anthos**

This directory contains a robust, **two‑database** seeding pipeline that populates Bank of Anthos with a **rich, realistic, and predictable** dataset. It’s a powerful alternative to the default load generator—ideal for demos, evaluations, and hackathon work.

The pipeline:
1) uses **Vertex AI (Gemini)** to generate realistic **personas**, then  
2) injects a **3‑month transaction history** directly into the app’s **PostgreSQL** databases.

---

## ✨ Key Features

- **🤖 AI‑Driven Personas** — Generates unique, realistic personas (age group, job title, income) using Vertex AI.
- **🏦 Architecture‑Aware** — Works with BoA’s **two separate databases**: `accounts-db` (users & contacts) and `ledger-db` (transactions).
- **⚡️ Fast & Reliable** — **Bypasses the frontend** and writes directly to PostgreSQL for consistency and speed.
- **🔐 Source‑Aligned** — Mirrors the userservice logic: correct schemas, all required fields, and **bcrypt** password hashes compatible with the real service.

> **Why bypass the frontend?**  
> In automated runs, the Python userservice can be overwhelmed by rapid signups and start dropping/ignoring requests. Direct DB seeding avoids that bottleneck and yields deterministic data.

---

## 🧭 What We Learned (and Why There’s a Fix Script)

When seeding directly into the DBs, the UI and backend must still be **correctly wired** to read and show those transactions. We repeatedly saw these symptoms:

- Frontend shows **no transactions** even though `ledger-db` has rows.
- `transactionhistory` responds **401/403** or **404** to `/transactions/<accountid>`.
- Java logs show `UNAUTHENTICATED: Failed computing credential metadata` or invalid token errors.
- Inconsistent **routing number** between data and services.

Root causes we fixed:
- **JWT key mismatch** — service expected secret `jwt-key` and `PUB_KEY_PATH` `/tmp/.ssh/publickey`, but the secret was missing or differently named.
- **Userservice lacked the private key** — could not sign JWTs that other services verify.
- **LOCAL_ROUTING_NUM mismatch** — data seeded with `123456789` while services used another number.
- **Frontend base address** — `HISTORY_API_ADDR` must be `transactionhistory:8080` (host:port only).
- **Workload Identity noise** — GCP telemetry attempted to fetch access tokens without minimal roles bound, producing noisy 403s.

To make this painless, we include **`boa-fix-auth.sh`**, an idempotent one‑touch script that aligns all of the above automatically.

---

## 🛠 `boa-fix-auth.sh` — What It Does

Idempotently:
1. (Optional) Fetches cluster credentials via `gcloud`.
2. Ensures **`jwt-key`** secret exists (generates RSA keypair if missing).
3. Patches `environment-config` with `LOCAL_ROUTING_NUM` (default `123456789`) and `PUB_KEY_PATH`.
4. Patches **`userservice`** to **mount the private key** and set `PRIV_KEY_PATH` env.
5. Restarts **`transactionhistory`** (reads `PUB_KEY_PATH` from ConfigMap) and sets routing.
6. Ensures **`frontend`** has `HISTORY_API_ADDR=transactionhistory:8080`, then restarts it.
7. (Optional) Binds Workload Identity for the shared KSA to a minimal GSA (quiet Cloud Ops 403s).
8. (Optional) Runs a **smoke test** calling `/healthy` and `/transactions/<acct>` with a short‑lived JWT.

### Quick Start

```bash
# From this directory
chmod +x boa-fix-auth.sh

# If kubectl context is already on your cluster/namespace:
./boa-fix-auth.sh

# Or let it grab GKE credentials:
./boa-fix-auth.sh --project <PROJECT_ID> --region <REGION> --cluster <CLUSTER_NAME>

# Useful flags
# --namespace boa (default)
# --routing 123456789 (default; match your seeded data)
# --account 3566835414 --user sf_structures (smoke test identity)
# --rotate-jwt (force new keypair)
# --no-wi (skip Workload Identity bindings)
# --no-smoke (skip the probe calls)
```

> The script is **safe to re‑run**. It patches by name and restarts only what’s needed.

---

## ✅ Prerequisites for Seeding

- **Python** 3.10+
- **kubectl** configured for your cluster (namespace `boa` assumed)
- Access to the **`accounts-db`** and **`ledger-db`** services
- (Optional) **Vertex AI** credentials if you want to regenerate personas with Gemini

If you already have personas JSON (e.g., `data/personas.json` with `username` and `password`), you can use that directly without calling Vertex AI.

---

## 🔧 Install Dependencies

```bash
# From the 'persona-generation' directory
pip install -r requirements.txt
```

---

## 🔌 Start Port‑Forwards (Two Terminals)

**Terminal 1 — accounts-db → localhost:5432**
```bash
kubectl port-forward service/accounts-db -n boa 5432:5432
```

**Terminal 2 — ledger-db → localhost:5433**
```bash
kubectl port-forward service/ledger-db -n boa 5433:5432
```

> These remain running while you seed. Adjust ports if they’re in use.

---

## 🚀 Run the Seeder

With both tunnels active, open a **third terminal**:

```bash
# From the 'persona-generation' directory
python seed_bank.py
```

**What it does:**  
- Ensures personas exist (users + contacts) with **bcrypt** passwords.  
- Generates and inserts **3 months** of realistic transactions into `ledger-db`.  
- Produces a consistent, demo‑friendly dataset.

---

## 🔁 Restart the App (Critical Final Step)

Running pods won’t automatically re‑load data seeded **behind** the services. Restart them once:

```bash
kubectl -n boa rollout restart deployment userservice balancereader transactionhistory frontend
```

Wait ~1 minute for pods to become ready, then browse to the Bank of Anthos frontend and **log in as any AI persona** (e.g., password `password123`) to view their full history.

---

## 🧪 Quick Verification (Optional)

From another terminal, you can confirm rows exist:

```bash
# If you have psql available
psql "host=localhost port=5432 dbname=accounts user=<user> password=<pass>" -c "SELECT COUNT(*) FROM users;"
psql "host=localhost port=5432 dbname=accounts user=<user> password=<pass>" -c "SELECT COUNT(*) FROM contacts;"
psql "host=localhost port=5433 dbname=ledger   user=<user> password=<pass>" -c "SELECT COUNT(*) FROM transactions;"
```

If counts are >0 and restart is done, the frontend should reflect the data.

---

## 🧱 Data Model Notes

- **Users** and **Contacts** must both exist for a persona; incomplete rows can break login flows.
- **IDs & FKs**: Make sure user/account identifiers match across users ↔ contacts ↔ transactions linkage.
- **Currency types**: Use consistent numeric types (integers for cents or decimals) per schema.
- **Password hashes**: Must be **bcrypt** with the expected prefix (e.g., `$2b$...`).

---

## 🧯 Troubleshooting

- **Transactions don’t show in UI**
  - Run the fixer: `./boa-fix-auth.sh` (aligns JWT keys, routing, and frontend base).
  - Verify ledger rows and that **balancereader/transactionhistory** restarted cleanly.
  - Confirm account/user linkage (`userservice` → `accountid`).

- **401/403 from `/transactions/<accountid>`**
  - The service is verifying JWTs. Use the fixer to mount keys & config.
  - Ensure you’re logging in as the **owner** of the account id you’re querying.

- **UNAUTHENTICATED / getAccessToken 403 spam**
  - Optional in fixer: Workload Identity binding adds minimal Cloud Ops roles to silence this.

- **Port‑forwarding errors**
  - Ports 5432/5433 may be taken; pick alternatives (e.g., `6543:5432`) and update your DSNs.

---

## 🔒 Production‑Minded Note (Optional Upgrade)

For production‑like setups, prefer **JWKS verification** (resource servers fetch public keys from `userservice`) over mounting public keys in pods. Only `userservice` signs JWTs (via **Secret Manager** or **Cloud KMS**). Resource services (e.g., `transactionhistory`) verify against a JWKS URL and enforce `aud`/`scope`/`acct` claims; **no private keys** outside `userservice`, and **key rotation** is painless.

---

## 📄 Personas Format (Example)

```json
[
  {
    "username": "socal_social",
    "age_group": "20s",
    "job_title": "Marketing Coordinator",
    "monthly_income": 4800,
    "transaction_patterns": { "...": "..." },
    "password": "password123"
  }
]
```

Only `username` and `password` are required for the seeder; other keys help drive realistic transaction generation.

---

## 🙌 Acknowledgements

Bank of Anthos © Google. Portions of the app and docs are under the **Apache 2.0** license.
