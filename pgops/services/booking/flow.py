"""Booking service: inquiry → hold → collect details. Deterministic only."""
from datetime import datetime, timedelta

from pgops.core.db import get_db
from pgops.core.logging import get_logger

log = get_logger("booking")

HOLD_HOURS = 48

HOUSE_INFO = {
    "food": "🍛 Mess included: breakfast + dinner daily, lunch on Sundays. Veg only.",
    "wifi": "📶 100 Mbps fiber, included in rent.",
    "curfew": "🚪 Gate closes 11:30 PM (late entry with prior notice).",
    "location": "📍 Near JSCOE, Hadapsar, Pune — 5 min from the bus stop.",
    "rules": "House rules: no smoking/alcohol on premises; guests in common area till 9 PM.",
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
        "ORDER BY b.rent, r.number, b.label"
    ).fetchall()


def availability_blocks() -> tuple[str, list]:
    """Returns (fallback_text, blocks) — beds grouped by type, tap-to-book buttons."""
    beds = available_beds()
    if not beds:
        return ("No beds free right now 😕 — want me to put you on the waitlist?", [])
    blocks: list[dict] = [{"type": "heading", "text": "🛏️ Available beds"}]
    items = [f"Room {b['room']} ({b['room_type']}) · bed {b['label']} — ₹{b['rent']:,}/mo (deposit ₹{b['deposit']:,})"
             for b in beds]
    blocks.append({"type": "list", "items": items})
    blocks.append({"type": "text", "text": "Tap a bed to reserve it — held for 48h, no payment needed yet."})
    blocks.append({"type": "buttons", "buttons": [
        {"label": f"{b['room']}·{b['label']} ₹{b['rent']//1000}k", "value": f"book {b['room']} {b['label']}"}
        for b in beds[:8]
    ]})
    fallback = "Available beds:\n" + "\n".join("• " + i for i in items) + \
               "\n\nReply like 'room 203 bed B' to reserve (held 48h)."
    return fallback, blocks


def answer_faq(text: str) -> str | None:
    t = text.lower()
    hits = [v for k, v in HOUSE_INFO.items() if k in t or
            (k == "food" and any(w in t for w in ("mess", "meal", "khana"))) or
            (k == "curfew" and "time" in t and "gate" in t)]
    return "\n".join(hits) if hits else None


def hold_bed(person_id: int, room: str, bed_label: str | None) -> tuple[str, list]:
    """Place a hold. Returns (fallback_text, blocks)."""
    expire_stale_holds()
    db = get_db()
    q = ("SELECT b.id, b.status, b.rent, b.deposit, r.number, b.label FROM beds b "
         "JOIN rooms r ON r.id=b.room_id WHERE r.number=?")
    rows = db.execute(q + (" AND b.label=?" if bed_label else ""),
                      (room, bed_label.upper()) if bed_label else (room,)).fetchall()
    free = [r for r in rows if r["status"] == "available"]
    if not rows:
        t, blk = availability_blocks()
        return f"Hmm, I don't have a room {room}. Here's what's free:\n\n{t}", blk
    if not free:
        t, blk = availability_blocks()
        return f"Room {room} is full right now. Here's what's free:\n\n{t}", blk
    bed = free[0]
    expires = (datetime.utcnow() + timedelta(hours=HOLD_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE beds SET status='held', hold_expires_at=? WHERE id=?", (expires, bed["id"]))
    db.execute("UPDATE people SET bed_id=? WHERE id=?", (bed["id"], person_id))
    db.commit()
    log.info("bed_held", person_id=person_id, room=room, bed=bed["label"])
    blocks = [{"type": "card",
               "title": f"✅ Room {bed['number']} · bed {bed['label']} is yours (held 48h)",
               "text": (f"Rent ₹{bed['rent']:,}/mo · deposit ₹{bed['deposit']:,} · "
                        f"move-in total ₹{bed['rent'] + bed['deposit']:,}"),
               },
              {"type": "text",
               "text": ("To lock it in, just send your details in one message:\n"
                        "name, phone, email, joining date\n"
                        "e.g. Rahul Jadhav, 9822012345, rahul@gmail.com, 1 Aug")}]
    fallback = (f"Room {bed['number']} bed {bed['label']} is held for you (48h) ✅\n"
                f"Rent ₹{bed['rent']:,}/mo + deposit ₹{bed['deposit']:,}.\n\n"
                "To lock it in, send: name, phone, email, joining date — e.g. "
                "'Rahul Jadhav, 9822012345, rahul@gmail.com, 1 Aug'.")
    return fallback, blocks


PRETTY = {"name": "your name", "phone": "phone number", "email": "email", "join_date": "joining date"}


def save_details(person_id: int, fields: dict) -> str | None:
    """Save provided details. Returns a 'still missing' message or None when complete."""
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
    missing = [PRETTY[c] for c in ("name", "phone", "email", "join_date") if not p[c]]
    if missing:
        return "Got it 👍 Just need " + " and ".join(missing) + " to finish up."
    return None
