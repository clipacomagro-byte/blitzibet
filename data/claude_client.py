"""Anthropic Claude client. Graceful degradation."""
import logging
from anthropic import AsyncAnthropic, APIError

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

log = logging.getLogger("blitzibet.claude")

_client = None
_warned_missing = False


def _get_client():
    global _client, _warned_missing
    if not ANTHROPIC_API_KEY:
        if not _warned_missing:
            log.warning(
                "ANTHROPIC_API_KEY is not set "
                "- Claude narratives will be skipped"
            )
            _warned_missing = True
        return None
    if _client is None:
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        log.info("Claude client initialized (model=%s)", CLAUDE_MODEL)
    return _client


SYSTEM_PROMPT = (
    "You are an elite in-play sports betting analyst writing "
    "Bloomberg-terminal-style alerts for the Blitzibet Telegram bot. "
    "Your job: maximum signal, minimum words.\n\n"
    "Given live match data, write EXACTLY this format:\n\n"
    "\u26a1 THE EDGE\n"
    "ONE sentence describing what's happening RIGHT NOW that creates "
    "the betting edge. Specific numbers. ~15-20 words.\n\n"
    "\U0001f9e0 PATTERN\n"
    "ONE sentence with the statistical or historical backing. "
    "~15-20 words.\n\n"
    "STRICT RULES:\n"
    "- Total under 50 words across BOTH lines.\n"
    "- Never invent numbers - only use what's in the data.\n"
    "- Sharp, professional, confident. Like a trader on a desk.\n"
    "- No markdown bold/italic - Telegram will format.\n"
    "- No fluffy phrases like 'looks interesting' or 'could be'.\n"
    "- For watch-tier signals, end with: "
    "'Heads-up only, not a bet.'\n"
    "\nThink: \"5 corners in 10' as Liverpool batter Chelsea's box, "
    "61% possession.\" Sharp. Specific. Done."
)


async def write_signal_narrative(context, tier="signal"):
    client = _get_client()
    if client is None:
        return None

    tier_note = ""
    if tier == "watch":
        tier_note = (
            "\n\nIMPORTANT: This is a WATCH-tier alert, not a "
            "bet recommendation. End the PATTERN line with "
            "'Heads-up only, not a bet.'"
        )

    user_prompt = (
        f"Match: {context.get('fixture_label', '')}\n"
        f"Score: {context.get('home_goals', 0)}-"
        f"{context.get('away_goals', 0)} at "
        f"{context.get('minute', 0)}'\n"
        f"League: {context.get('league', '')}\n"
        f"Rule: {context.get('rule_name', '')}\n\n"
        f"Live stats:\n{context.get('live_stats_text', 'no data')}\n\n"
        f"Change in last 10 min:\n"
        f"{context.get('delta_text', 'no data')}\n\n"
        f"H2H (last 5):\n"
        f"{context.get('h2h_text', 'no recent meetings')}"
        f"{tier_note}\n\n"
        f"Write the 2-line response now. Be sharp."
    )

    try:
        log.info(
            "Calling Claude for %s (tier=%s)",
            context.get("fixture_label", "?"), tier,
        )
        msg = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
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
