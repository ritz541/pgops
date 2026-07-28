# PGOps — a PG that runs itself over chat

**Caspian Buildathon 2026 entry.** Full tenant lifecycle for an Indian PG — inquiry → booking → rent → complaints — run entirely over **Telegram + Email through one `on_message` handler** (caspian-sdk).

- Tenants talk to the agent on Telegram (natural language: "any single bed free?").
- Paperwork travels over email: PDF invoices, payment screenshots, ID documents.
- Owner approves bookings/payments from Telegram or email, plus a small FastAPI dashboard.

## Stack
Python · caspian-sdk (Telegram + Email) · LiteLLM (intent parsing) · SQLite · FastAPI + Bootstrap · PDF invoices

**Design rule:** the LLM only parses intent; all money/DB logic is deterministic Python.

## Run
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in keys
.venv/bin/python scripts/seed_db.py
.venv/bin/python -m pgops.main
```

> Demo uses dummy documents only. No real payments are moved — the agent tracks payment claims + owner confirmations. Document encryption-at-rest is on the roadmap.
