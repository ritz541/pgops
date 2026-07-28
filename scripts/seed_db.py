"""Seed the PGOps DB with the demo PG: rooms, beds, rates, owner."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()
from pgops.core.db import get_db, init_db

ROOMS = [
    # (number, type, beds: [(label, rent, deposit)])
    ("101", "single", [("A", 11000, 15000)]),
    ("102", "double", [("A", 8500, 10000), ("B", 8500, 10000)]),
    ("103", "double", [("A", 8500, 10000), ("B", 8500, 10000)]),
    ("201", "single", [("A", 12000, 15000)]),
    ("202", "triple", [("A", 7000, 8000), ("B", 7000, 8000), ("C", 7000, 8000)]),
    ("203", "double", [("A", 9000, 10000), ("B", 9000, 10000)]),
]


def main():
    init_db()
    db = get_db()
    if db.execute("SELECT COUNT(*) c FROM rooms").fetchone()["c"]:
        print("DB already seeded, skipping.")
        return
    for number, rtype, beds in ROOMS:
        cur = db.execute("INSERT INTO rooms(number, room_type) VALUES (?,?)", (number, rtype))
        for label, rent, deposit in beds:
            db.execute(
                "INSERT INTO beds(room_id, label, rent, deposit) VALUES (?,?,?,?)",
                (cur.lastrowid, label, rent, deposit),
            )
    db.execute(
        "INSERT INTO people(name, role, telegram_address, email) VALUES (?,?,?,?)",
        ("Owner", "owner", os.getenv("OWNER_TELEGRAM", ""), os.getenv("OWNER_EMAIL", "")),
    )
    db.commit()
    n = db.execute("SELECT COUNT(*) c FROM beds").fetchone()["c"]
    print(f"Seeded {len(ROOMS)} rooms, {n} beds, 1 owner.")


if __name__ == "__main__":
    main()
