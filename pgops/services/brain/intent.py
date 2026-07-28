"""Brain service: LiteLLM intent parsing. The LLM only classifies/extracts —
it never writes to the DB and never does money math.
"""
import json
import os

import litellm

from pgops.core.logging import get_logger

log = get_logger("brain")

litellm.suppress_debug_info = True

SYSTEM = """You are the intent parser for PGOps, an agent that manages a paying-guest (PG) accommodation over Telegram and email.
Classify the user's message into exactly one intent and extract fields.

Intents (role: anyone unless noted):
- inquiry: asking about available beds/rooms, rent, deposit, or PG facilities (food, wifi, rules, location)
- book_bed: wants to book/reserve a specific room/bed, or says yes to taking one
- provide_details: giving personal details (name, phone, email, joining date)
- payment_claim: says they paid / sent payment / attached a payment screenshot
- my_status: asks their own balance, rent due, booking status
- complaint: reports a problem (geyser broken, food issue, wifi down...)
- owner_query (owner only): occupancy, defaulters, who hasn't paid, pending approvals
- owner_approve (owner only): approve/reject a booking or payment. Extract decision + person name
- broadcast (owner only): send an announcement to all tenants
- chitchat: greetings, thanks, anything else

Return STRICT JSON, no markdown fences:
{"intent": "...", "fields": {"room": "203", "bed": "B", "name": null, "phone": null, "email": null, "join_date": null, "decision": null, "person": null, "amount": null, "text": null}}
Only include fields actually present in the message. Use null otherwise.
"""


def parse_intent(text: str, role: str, context: str = "") -> dict:
    """Classify a message. Returns {"intent": str, "fields": dict}. Never raises."""
    user = f"Sender role: {role}\n"
    if context:
        user += f"Conversation context: {context}\n"
    user += f"Message: {text}"

    models = [
        dict(model=os.getenv("LLM_MODEL"), api_key=os.getenv("AGNES_API_KEY"),
             base_url=os.getenv("LLM_BASE_URL")),
        dict(model=os.getenv("LLM_FALLBACK_MODEL"), api_key=os.getenv("OPENROUTER_API_KEY")),
    ]
    for m in models:
        try:
            resp = litellm.completion(
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": user}],
                temperature=0.1, max_tokens=300, timeout=25, **m,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").removeprefix("json").strip()
            out = json.loads(raw)
            if "intent" not in out:
                raise ValueError(f"no intent key in {raw[:100]}")
            out.setdefault("fields", {})
            log.info("intent_parsed", intent=out["intent"], model=m["model"])
            return out
        except Exception:
            log.exception("intent_parse_failed", model=m.get("model"))
    return {"intent": "chitchat", "fields": {}}
