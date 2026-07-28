"""Route inbound messages: identify sender, parse intent, dispatch handler.

V0 placeholder: echoes with identification info. Intent parsing (LiteLLM)
and flow handlers land next.
"""
from pgops.core.db import get_db


def identify(message):
    """Map a caspian sender/conversation to a person row (or None)."""
    db = get_db()
    addr = message.sender.get("address") if isinstance(message.sender, dict) else str(message.sender)
    row = db.execute(
        "SELECT p.* FROM conversations c JOIN people p ON p.id = c.person_id WHERE c.conversation_id = ?",
        (message.conversation_id,),
    ).fetchone()
    if row:
        return row
    row = db.execute(
        "SELECT * FROM people WHERE telegram_address = ? OR email = ?",
        (addr, addr),
    ).fetchone()
    return row


def route_message(message) -> None:
    person = identify(message)
    who = person["name"] if person else "stranger"
    role = person["role"] if person else "unknown"
    print(f"[IN] {who}({role}) conv={message.conversation_id}: {message.text!r}", flush=True)
    # TODO: LiteLLM intent parse -> dispatch to flows (inquiry/booking/rent/complaint/owner)
    message.reply(f"PGOps here. I recognized you as: {who} ({role}). Agent brain coming soon.")
