"""Anthropic Claude client. Graceful degradation: if anything fails,
returns None and the signal fires without the AI narrative."""
import logging
from anthropic import AsyncAnthropic, APIError

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

log = logging.getLogger("blitzibet.claude")

_client: AsyncAnthropic | None = None
_warned_missing = False


def _get_client() -> AsyncAnthropic | None:
    global _client, _warned_missing
    if not ANTHROPIC_API_KEY:
        if not _warned_missing:
            log.warning("ANTHROPIC_API_KEY is not set — Claude narratives will be skipped")
            _warned_missing = True
        return None
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        log.info("Claude client initialized (model=%s)", CLAUDE_MODEL)
    return _client


SYSTEM_PROMPT = """You are an in-play sports betting analyst writing brief, punchy live signal alerts for a Telegram bot called Blitzibet.

You will be given live match data and recent context. Write a response with these three sections, in this exact format and order:

📈 LAST 10 MIN
(2–3 short lines describing the momentum shift — specific numbers from the data only. No invented stats.)

🧠 PATTERN CONTEXT
(2–4 bullets starting with "•" — historical/statistical backing, again only using what was provided.)

💬 AI READ
(2–3 italic sentences interpreting what's happening, like a sharp friend talking to you in a sports bar. Honest about uncertainty.)

Rules:
- Max 200 words total
- Never invent or estimate stats not in the input — if you don't have it, don't mention it
- Bettor language but not gambling promotion; be honest about confidence
- For "watch tier" signals, the AI READ ends with a note that this is just a heads-up, not a bet recommendation
- Use plain text, no markdown emphasis (no asterisks — Telegram will format)"""


async def write_signal_narrative(context: dict, tier: str = "signal") -> str | None:
    client = _get_client()
    if client is None:
        return None

    tier_note = ""
    if tier == "watch":
        tier_note = "\n\nIMPORTANT: This is a WATCH-tier alert, not a bet recommendation. End the AI READ section noting this is informational only, the engine is watching but not confident enough to recommend a bet."

    user_prompt = f"""Match: {context.get('fixture_label', '')}
Score: {context.get('home_goals', 0)}-{context.get('away_goals', 0)} at {context.get('minute', 0)}'
League: {context.get('league', '')}
Rule fired: {context.get('rule_name', '')}

Live stats (current snapshot):
{context.get('live_stats_text', 'no data')}

Change in last ~10 min:
{context.get('delta_text', 'no data')}

Head-to-head (last 5 meetings):
{context.get('h2h_text', 'no recent meetings on file')}
{tier_note}

Write the three-section response now."""

    try:
        log.info("Calling Claude for %s (tier=%s)",
                 context.get('fixture_label', '?'), tier)
        msg = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        if msg.content and len(msg.content) > 0:
            return msg.content[0].text.strip()
    except APIError as e:
        log.warning("Claude API error: %s", e)
    except Exception as e:
        log.exception("Unexpected Claude failure: %s", e)

    return None
