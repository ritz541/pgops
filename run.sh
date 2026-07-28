#!/usr/bin/env bash
# PGOps agent runner. Usage: ./run.sh
set -e
cd "$(dirname "$0")"
[ -f data/pgops.db ] || .venv/bin/python scripts/seed_db.py
exec .venv/bin/python -m pgops.main
