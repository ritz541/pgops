"""Orchestrator: identify sender → parse intent → dispatch to a service.

Handlers return either a string, or a (fallback_text, blocks) tuple for
rich rendering (buttons on Telegram, HTML on email, text elsewhere).
"""
from pgops.core.db import get_db
from pgops.core.logging import get_logger
from pgops.services.brain import intent as brain
from pgops.services.booking import flow as booking

log = get_logger("router")


def _addr(message):
    s = message.sender
    return s.get("address") if isinstance(s, dict) else str(s)


def identify_or_create(message):
    """Map sender → person row; unknown senders become prospects.
    Links the conversation to the person for future lookups."""
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


# ---- handlers: (person, fields, message) -> str | (text, blocks) ----

def h_inquiry(person, fields, message):
    faq = booking.answer_faq(message.text)
    criteria = fields.get("criteria")
    beds = booking.available_beds()
    
    text, blocks = booking.availability_blocks()
    if criteria and beds:
        pick = brain.resolve_bed(criteria, beds)
        if pick:
            prefix = f"💡 **Recommended ({pick.get('reason')}):** Room {pick['room']} Bed {pick.get('bed', 'A')}\n\n"
            text = prefix + text
            if blocks and blocks[0].get("type") == "heading":
                blocks.insert(1, {"type": "text", "text": f"💡 Recommended for '{criteria}': Room {pick['room']} Bed {pick.get('bed', 'A')}"})
    
    if faq:
        return faq + "\n\n" + text, ([{"type": "text", "text": faq}] + blocks) if blocks else []
    return text, blocks


def h_book(person, fields, message):
    room, bed = fields.get("room"), fields.get("bed")
    if not room:
        criteria = fields.get("criteria") or message.text
        beds = booking.available_beds()
        if not beds:
            return booking.availability_blocks()
        pick = brain.resolve_bed(criteria, beds)
        if not pick:
            text, blocks = booking.availability_blocks()
            return "I couldn't match that to a bed. " + text, blocks
        room, bed = pick["room"], pick.get("bed")
    return booking.hold_bed(person["id"], str(room), bed)

def h_details(person, fields, message):
    missing_msg = booking.save_details(person["id"], fields)
    if missing_msg:
        return missing_msg
    return ("Perfect, all details in ✅ Your booking invoice is on its way to "
            "your email — reply there with the payment screenshot to confirm.")


def h_chitchat(person, fields, message):
    return ("Hey! I run this PG 🙂 I can show you free beds, prices, food & "
            "wifi details, and book you in — right from this chat.\n"
            "Try: 'any beds free?'")


DISPATCH = {
    "inquiry": h_inquiry,
    "book_bed": h_book,
    "provide_details": h_details,
    "chitchat": h_chitchat,
}


def route_message(message) -> None:
    person = identify_or_create(message)
    text = (message.text or "").strip()

    # button callbacks come back as plain text like "book 202 C" — no LLM needed
    if text.lower().startswith("book "):
        parts = text.split()
        room = parts[1] if len(parts) > 1 else None
        bed = parts[2] if len(parts) > 2 else None
        parsed = {"intent": "book_bed", "fields": {"room": room, "bed": bed}}
    else:
        parsed = brain.parse_intent(text, role=person["role"])

    intent, fields = parsed["intent"], parsed.get("fields", {})
    log.info("message_in", person=person["name"], role=person["role"],
             intent=intent, conv=message.conversation_id, text=text[:120])

    handler = DISPATCH.get(intent, h_chitchat)
    result = handler(person, fields, message)
    if isinstance(result, tuple):
        fallback, blocks = result
        if blocks:
            message.reply(fallback, blocks=blocks)
        else:
            message.reply(fallback)
    elif result:
        message.reply(result)
