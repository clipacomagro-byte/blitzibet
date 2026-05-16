"""Sends signals to users whose pins match the signal's market.
Sanitizes Claude's narrative to keep Telegram's Markdown happy."""
import logging
import httpx

from config import TELEGRAM_BOT_TOKEN
from data import models

log = logging.getLogger("blitzibet.notifier")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

CONFIDENCE_DOTS = {
    1: "\U0001f7e0",
    2: "\U0001f7e0\U0001f7e0",
    3: "\U0001f7e0\U0001f7e0\U0001f7e0",
    4: "\U0001f7e0\U0001f7e0\U0001f7e0\U0001f7e0",
    5: "\U0001f7e0\U0001f7e0\U0001f7e0\U0001f7e0\U0001f7e0",
}


def _sanitize_for_markdown(text):
    """Strip characters that break Telegram's Markdown entity parser.
    We told Claude not to use markdown formatting, but it sometimes
    sneaks them in. This makes it bulletproof."""
    if not text:
        return text
    for char in ("_", "*", "[", "]", "(", ")", "`"):
        text = text.replace(char, "")
    return text


def _format_signal(fixture_label, league, minute, home_goals, away_goals,
                   market, suggested_bet, confidence, rule_name, tier,
                   narrative):
    is_watch = tier == "watch"
    dots = CONFIDENCE_DOTS.get(confidence, "\U0001f7e0")

    if is_watch:
        header = (
            f"\U0001f440 *WATCHING \u00b7 {market.upper()}*  \u00b7  "
            f"{dots} {confidence}/5"
        )
    else:
        header = (
            f"\U0001f534 *LIVE SIGNAL \u00b7 {market.upper()}*  \u00b7  "
            f"{dots} {confidence}/5"
        )

    parts = [
        header,
        "",
        f"\u26bd *{fixture_label}*",
        f"\U0001f4ca {home_goals} \u2014 {away_goals}  \u00b7  "
        f"{minute}'  \u00b7  {league}",
    ]

    if narrative:
        clean = _sanitize_for_markdown(narrative)
        parts.append("")
        parts.append(clean)

    parts.append("")
    if is_watch:
        parts.append(
            "\u2139\ufe0f _The engine is watching this game. "
            "Not a bet — just a heads-up._"
        )
    else:
        parts.append("\U0001f4a1 *BET*")
        parts.append(suggested_bet)

    parts.append("")
    parts.append(
        f"_rule: {rule_name}  \u00b7  powered by Blitzibet + Claude_"
    )
    return "\n".join(parts)


async def dispatch_signal(signal_id, sport, market, fixture_label, league,
                          minute, home_goals, away_goals, suggested_bet,
                          confidence, rule_name="", tier="signal",
                          narrative=None):
    user_ids = await models.get_users_for_market(sport, market)
    if not user_ids:
        log.info(
            "Signal %s no subscribers for %s/%s",
            signal_id, sport, market,
        )
        return

    text = _format_signal(
        fixture_label, league, minute, home_goals, away_goals,
        market, suggested_bet, confidence, rule_name, tier, narrative,
    )

    async with httpx.AsyncClient(timeout=10) as client:
        for uid in user_ids:
            try:
                r = await client.post(TG_API, json={
                    "chat_id": uid,
                    "text": text,
                    "parse_mode": "Markdown",
                })
                response_data = r.json()
                ok = r.status_code == 200 and response_data.get("ok")
                await models.record_notification(
                    signal_id, uid, ok,
                    None if ok else r.text[:200],
                )
                if ok:
                    msg_id = response_data.get("result", {}).get("message_id")
                    if msg_id:
                        try:
                            await models.track_bot_message(uid, msg_id)
                        except Exception:
                            log.warning(
                                "Failed to track msg %s for %s",
                                msg_id, uid,
                            )
            except Exception as e:
                log.exception("Send failed to %s: %s", uid, e)
                await models.record_notification(
                    signal_id, uid, False, str(e)[:200],
                )
