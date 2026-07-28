"""Orchestrator: identify sender → parse intent → dispatch to a service.

Dispatch table maps (role, intent) → handler. Adding a service later =
import it + add rows here. Nothing else changes.
"""
from pgops.core.db import get_db
from pgops.core.logging import get_logger
from pgops.services.brain.intent import parse_intent
from pgops.services.booking import flow as booking

log = get_logger("router")


def _addr(message):
    s = message.sender
    return s.get("address") if isinstance(s, dict) else str(s)


def identify_or_create(message):
    """Map sender → person row. Unknown senders become new prospects.
    Also links this conversation to the person for future lookups."""
    db = get_db()
    addr = _addr(message)
    channel = getattr(message, "channel", None) or ("email" if "@" in addr else "telegram")

    row = db.execute(
        "SELECT p.* FROM conversations c JOIN people p ON p.id=c.person_id "
        "WHERE c.conversation_id=?", (message.conversation_id,)).fetchone()
    if row:
        return row

    row = db.execute("SELECT * FROM people WHERE telegram_address=? OR email=?",
                     (addr, addr)).fetchone()
    if not row:
        name = message.sender.get("name") if isinstance(message.sender, dict) else None
        col = "email" if channel == "email" else "telegram_address"
        cur = db.execute(
            f"INSERT INTO people(name, role, {col}) VALUES (?, 'prospect', ?)", (name, addr))
        db.commit()
        row = db.execute("SELECT * FROM people WHERE id=?", (cur.lastrowid,)).fetchone()
        log.info("prospect_created", person_id=row["id"], addr=addr, channel=channel)

    db.execute("INSERT OR IGNORE INTO conversations(conversation_id, person_id, channel) VALUES (?,?,?)",
               (message.conversation_id, row["id"], channel))
    db.commit()
    return row


# ---- handlers: (person, fields, message) -> reply text ----

def h_inquiry(person, fields, message):
    faq = booking.answer_faq(message.text)
    avail = booking.format_availability()
    return f"{faq}\n\n{avail}" if faq else avail


def h_book(person, fields, message):
    room, bed = fields.get("room"), fields.get("bed")
    if not room:
        return "Which room would you like? " + booking.format_availability()
    return booking.hold_bed(person["id"], str(room), bed)


def h_details(person, fields, message):
    missing_msg = booking.save_details(person["id"], fields)
    if missing_msg:
        return missing_msg
    # details complete → invoice step lands next (billing service)
    return ("All details received ✅. I'm preparing your booking invoice — "
            "you'll get it on email shortly.")


def h_chitchat(person, fields, message):
    if person["role"] == "owner":
        return "Hello boss 👋 — ask me 'who hasn't paid', 'occupancy', or 'broadcast: <msg>'."
    return ("Hi! I'm the PGOps assistant 🤖 — I manage this PG.\n"
            "Ask me about available beds, rent, food, wifi, or rules.")


def h_not_implemented(person, fields, message):
    return "That's coming soon — this part of me is still being built."


DISPATCH = {
    "inquiry": h_inquiry,
    "book_bed": h_book,
    "provide_details": h_details,
    "chitchat": h_chitchat,
    "payment_claim": h_not_implemented,
    "my_status": h_not_implemented,
    "complaint": h_not_implemented,
    "owner_query": h_not_implemented,
    "owner_approve": h_not_implemented,
    "broadcast": h_not_implemented,
}

OWNER_ONLY = {"owner_query", "owner_approve", "broadcast"}


def route_message(message) -> None:
    person = identify_or_create(message)
    parsed = parse_intent(message.text, role=person["role"])
    intent, fields = parsed["intent"], parsed.get("fields", {})
    log.info("message_in", person=person["name"], role=person["role"],
             intent=intent, conv=message.conversation_id, text=message.text[:120])

    if intent in OWNER_ONLY and person["role"] != "owner":
        message.reply("That's an owner-only action.")
        return
    handler = DISPATCH.get(intent, h_chitchat)
    reply = handler(person, fields, message)
    if reply:
        message.reply(reply)
