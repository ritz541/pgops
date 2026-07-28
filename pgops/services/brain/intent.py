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
- book_bed: the user wants to book/reserve/take a bed. Triggers include:
  * explicit room/bed: "room 202 bed A", "202 A", "get me 203B"
  * described choice: "cheapest", "any single", "something under 8k", "which is cheaper"
  * comparisons or recommendations: "which one is best", "what do you suggest", "cheap option"
  * acceptance after seeing availability: "I'll take that one", "book the second one", "yes"
- inquiry: ONLY when the user is purely asking about info and gives NO signal they want to book right now.
  Examples: "what is the wifi speed", "do you have parking", "tell me about the mess"
- provide_details: giving personal details (name, phone, email, joining date) — usually right after a hold.
- payment_claim: says they paid / sent money / attached a screenshot.
- my_status: asks their own balance, rent due, booking status.
- complaint: reports a problem.
- owner_query (owner only): occupancy, defaulters, pending approvals.
- owner_approve (owner only): approve/reject + person name.
- broadcast (owner only): send an announcement.
- chitchat: greetings, thanks, capability questions, anything else.

DEFAULT TO book_bed when the user is evaluating beds or expressing preference — only use inquiry if they're clearly asking a fact question.

Return STRICT JSON, no markdown fences:
{"intent":"...","fields":{"room":null,"bed":null,"criteria":null,"name":null,"phone":null,"email":null,"join_date":null,"decision":null,"person":null,"amount":null,"text":null}}
- room/bed: only if named explicitly (e.g. "203 B").
- criteria: for book_bed/inquiry when choice is described, copy the description (e.g. "cheapest").
- join_date: normalize to ISO YYYY-MM-DD (assume 2026 if year missing).
Only include fields actually present. Use null otherwise.
"""

RESOLVER = """You help pick a bed in a PG. Given the user's request and the list of available beds, pick the single best match.
Return STRICT JSON, no markdown fences: {"room":"...","bed":"...","reason":"<=12 words"} or {"room":null,"bed":null,"reason":"no match"}.
Never invent beds not in the list."""


def _complete(system: str, user: str, max_tokens: int = 300) -> str:
    models = [
        dict(model=os.getenv("LLM_MODEL"), api_key=os.getenv("AGNES_API_KEY"),
             base_url=os.getenv("LLM_BASE_URL")),
        dict(model=os.getenv("LLM_FALLBACK_MODEL"), api_key=os.getenv("OPENROUTER_API_KEY")),
    ]
    last = None
    for m in models:
        try:
            resp = litellm.completion(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.1, max_tokens=max_tokens, timeout=25, **m,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last = e
            log.warning("llm_call_failed", model=m.get("model"), error=str(e)[:200])
    raise RuntimeError(f"all LLM models failed: {last}")


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


def resolve_bed(request: str, beds: list) -> dict | None:
    """Pick a bed matching a described request ('cheapest', 'any single'...).
    beds: rows with room, room_type, label, rent, deposit. Returns
    {"room":..., "bed":..., "reason":...} or None."""
    listing = "\n".join(
        f"room {b['room']} ({b['room_type']}) bed {b['label']}: rent {b['rent']}/mo, deposit {b['deposit']}"
        for b in beds)
    try:
        out = _json(_complete(RESOLVER, f"Request: {request}\nAvailable beds:\n{listing}", 150))
        if out.get("room"):
            log.info("bed_resolved", room=out["room"], bed=out.get("bed"), reason=out.get("reason"))
            return out
    except Exception:
        log.exception("bed_resolve_failed")
    return None
