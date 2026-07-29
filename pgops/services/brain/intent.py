"""Brain service: LiteLLM calls. The LLM classifies, resolves and phrases —
it never writes to the DB and never does money math.
"""
import json
import os

import litellm

from pgops.core.logging import get_logger

log = get_logger("brain")

litellm.suppress_debug_info = True
os.environ.setdefault("LITELLM_LOG", "ERROR")

SYSTEM = """You are the intent parser for PGOps, an agent that manages a paying-guest (PG) over Telegram and email.
Classify the user's message into exactly one intent and extract fields.

INTENT RULES (apply in order):
- inquiry: asking about information, availability, prices, or room options. Triggers include:
  * asking for free/available beds: "any beds free", "what's available", "show rooms"
  * asking about preferences: "cheapest", "cheapest bed", "single room", "under 8k", "which is cheaper"
  * general questions: "wifi speed", "mess details", "curfew", "location"
- book_bed: the user explicitly wants to book, reserve, hold, or take a specific bed. Triggers include:
  * explicit room/bed request: "book room 202 bed A", "book 202A", "hold 101 A", "reserve 203 B"
  * explicit commitment: "I want to book", "I'll take 202 A", "lock in 101A", "yes book it"
  * button value: "book 202 A"
- provide_details: giving personal details (name, phone, email, joining date).
- payment_claim: says they paid / sent money / attached a screenshot.
- my_status: asks their own balance, rent due, booking status.
- complaint: reports a problem.
- owner_query (owner only): occupancy, defaulters, pending approvals.
- owner_approve (owner only): approve/reject + person name.
- broadcast (owner only): send an announcement.
- chitchat: greetings, thanks, capability questions, anything else.

Return STRICT JSON, no markdown fences:
{"intent":"...","fields":{"room":null,"bed":null,"criteria":null,"name":null,"phone":null,"email":null,"join_date":null,"decision":null,"person":null,"amount":null,"text":null}}
- room/bed: only if named explicitly (e.g. "203 B").
- criteria: for inquiry, extract filter description (e.g. "cheapest", "single", "double", "under 8k").
- join_date: normalize to ISO YYYY-MM-DD (assume 2026 if year missing).
Only include fields actually present. Use null otherwise.
"""

RESOLVER = """You help pick a bed in a PG. Given the user's request and the list of available beds, pick the single best match.
Return STRICT JSON, no markdown fences: {"room":"...","bed":"...","reason":"<=12 words"} or {"room":null,"bed":null,"reason":"no match"}.
Never invent beds not in the list."""


def _complete(system: str, user: str, max_tokens: int = 300) -> str:
    model = os.getenv("LLM_MODEL", "openrouter/inclusionai/ling-3.0-flash:free")
    if not model:
        raise RuntimeError("LLM_MODEL is not set")

    kwargs = {}
    if os.getenv("OPENROUTER_API_KEY"):
        kwargs["api_key"] = os.getenv("OPENROUTER_API_KEY")

    try:
        resp = litellm.completion(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.1, max_tokens=max_tokens, timeout=25, **kwargs,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning("llm_call_failed", model=model, error=str(e)[:200])
        raise RuntimeError(f"LLM call failed: {e}") from e
def _json(raw: str) -> dict:
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    return json.loads(raw)


def parse_intent(text: str, role: str) -> dict:
    """Classify a message. Returns {"intent": str, "fields": dict}. Never raises."""
    try:
        out = _json(_complete(SYSTEM, f"Sender role: {role}\nMessage: {text}"))
        if "intent" not in out:
            raise ValueError("no intent key")
        out.setdefault("fields", {})
        log.info("intent_parsed", intent=out["intent"])
        return out
    except Exception:
        log.exception("intent_parse_failed")
        return {"intent": "chitchat", "fields": {}}


def resolve_bed(request: str | None, beds: list) -> dict | None:
    """Pick a bed matching criteria ('cheapest', 'single', etc.) deterministically in Python (0ms).
    beds: list of dicts/Rows with room, room_type, label, rent, deposit."""
    if not beds:
        return None
    if not request:
        b = beds[0]
        return {"room": str(b["room"]), "bed": b["label"], "reason": "First available"}

    c = request.lower()
    if "single" in c:
        singles = [b for b in beds if b["room_type"] == "single"]
        if singles:
            b = singles[0]
            return {"room": str(b["room"]), "bed": b["label"], "reason": "Single room"}
    if "double" in c:
        doubles = [b for b in beds if b["room_type"] == "double"]
        if doubles:
            b = doubles[0]
            return {"room": str(b["room"]), "bed": b["label"], "reason": "Double sharing"}
    if "triple" in c:
        triples = [b for b in beds if b["room_type"] == "triple"]
        if triples:
            b = triples[0]
            return {"room": str(b["room"]), "bed": b["label"], "reason": "Triple sharing"}

    # Default: cheapest (beds is already sorted by rent)
    b = beds[0]
    return {"room": str(b["room"]), "bed": b["label"], "reason": f"Cheapest at ₹{b['rent']:,}/mo"}
