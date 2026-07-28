"""Booking service: inquiry → hold → collect details → invoice → owner approval.

All deterministic. Router passes parsed intent fields in; we return reply text
(and optionally trigger owner notification via a callback the router provides).
"""
import os
from datetime import datetime, timedelta

from pgops.core.db import get_db
from pgops.core.logging import get_logger

log = get_logger("booking")

HOLD_HOURS = 48

HOUSE_INFO = {
    "food": "Mess included: breakfast + dinner daily, lunch on Sundays. Veg only.",
    "wifi": "100 Mbps shared fiber, included in rent.",
    "curfew": "Gate closes 11:30 PM. Late entry with prior notice.",
    "location": "Near JSCOE, Hadapsar, Pune. 5 min walk from the bus stop.",
    "rules": "No smoking/alcohol on premises. Guests allowed in common area till 9 PM.",
}


def expire_stale_holds() -> None:
    db = get_db()
    db.execute(
        "UPDATE beds SET status='available', hold_expires_at=NULL "
        "WHERE status='held' AND hold_expires_at < datetime('now')"
    )
    db.commit()


def available_beds() -> list:
    expire_stale_holds()
    db = get_db()
    return db.execute(
        "SELECT b.id, r.number room, r.room_type, b.label, b.rent, b.deposit "
        "FROM beds b JOIN rooms r ON r.id=b.room_id WHERE b.status='available' "
        "ORDER BY r.number, b.label"
    ).fetchall()


def format_availability() -> str:
    beds = available_beds()
    if not beds:
        return "Sorry, no beds available right now. Want me to note your number for the waitlist?"
    lines = ["Available beds right now:"]
    for b in beds:
        lines.append(f"• Room {b['room']} ({b['room_type']}) bed {b['label']} — ₹{b['rent']}/mo, deposit ₹{b['deposit']}")
    lines.append("\nReply like: 'I'll take room 203 bed B' to reserve (held 48h).")
    return "\n".join(lines)


def answer_faq(text: str) -> str | None:
    t = text.lower()
    hits = [v for k, v in HOUSE_INFO.items() if k in t or
            (k == "food" and any(w in t for w in ("mess", "meal", "khana"))) or
            (k == "curfew" and "time" in t and "gate" in t)]
    return "\n".join(hits) if hits else None


def hold_bed(person_id: int, room: str, bed_label: str | None) -> str:
    """Place a hold. Returns reply text."""
    expire_stale_holds()
    db = get_db()
    q = ("SELECT b.id, b.status, b.rent, b.deposit, r.number, b.label FROM beds b "
         "JOIN rooms r ON r.id=b.room_id WHERE r.number=?")
    rows = db.execute(q + (" AND b.label=?" if bed_label else ""),
                      (room, bed_label.upper()) if bed_label else (room,)).fetchall()
    free = [r for r in rows if r["status"] == "available"]
    if not rows:
        return f"I couldn't find room {room}. " + format_availability()
    if not free:
        return f"Room {room} has no free beds right now. " + format_availability()
    bed = free[0]
    expires = (datetime.utcnow() + timedelta(hours=HOLD_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE beds SET status='held', hold_expires_at=? WHERE id=?", (expires, bed["id"]))
    db.execute("UPDATE people SET bed_id=? WHERE id=?", (bed["id"], person_id))
    db.commit()
    log.info("bed_held", person_id=person_id, room=room, bed=bed["label"])
    return (f"Done — room {bed['number']} bed {bed['label']} is held for you for {HOLD_HOURS}h.\n"
            f"Rent ₹{bed['rent']}/mo + deposit ₹{bed['deposit']} = ₹{bed['rent'] + bed['deposit']} to move in.\n\n"
            "To confirm, send me: your full name, phone, email, and joining date "
            "(e.g. 'Rahul Jadhav, 9822012345, rahul@gmail.com, joining 1 Aug').")


def save_details(person_id: int, fields: dict) -> str | None:
    db = get_db()
    updates, vals = [], []
    for col in ("name", "phone", "email", "join_date"):
        if fields.get(col):
            updates.append(f"{col}=?")
            vals.append(fields[col])
    if updates:
        vals.append(person_id)
        db.execute(f"UPDATE people SET {', '.join(updates)} WHERE id=?", vals)
        db.commit()
    p = db.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
    missing = [c for c in ("name", "phone", "email", "join_date") if not p[c]]
    if missing:
        return "Thanks! Still need: " + ", ".join(missing) + "."
    return None  # complete — router will trigger invoice
