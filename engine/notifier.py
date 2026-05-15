"""Routes signals to users whose pins match. Uses the bot token to send messages
directly via the HTTP Bot API — keeps the worker independent of the bot process."""
import logging
import httpx

from config import TELEGRAM_BOT_TOKEN
from data import models

log = logging.getLogger("blitzibet.notifier")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

CONFIDENCE_BAR = {1: "🔥", 2: "🔥🔥", 3: "🔥🔥🔥", 4: "🔥🔥🔥🔥", 5: "🔥🔥🔥🔥🔥"}


def _format_signal(fixture_label: str, league: str, minute: int,
                   home_goals: int, away_goals: int,
                   market: str, suggested_bet: str, confidence: int) -> str:
    return (
        f"🔴 *LIVE SIGNAL — {market.upper()}*\n\n"
        f"⚽ *{fixture_label}*\n"
        f"📊 {home_goals} — {away_goals}   ·   {minute}'\n"
        f"🏆 {league}\n\n"
        f"💡 *Suggested bet:*\n{suggested_bet}\n\n"
        f"Confidence: {CONFIDENCE_BAR.get(confidence, '🔥')}"
    )


async def dispatch_signal(signal_id: int, sport: str, market: str,
                          fixture_label: str, league: str, minute: int,
                          home_goals: int, away_goals: int,
                          suggested_bet: str, confidence: int) -> None:
    user_ids = await models.get_users_for_market(sport, market)
    if not user_ids:
        log.info("Signal %s has no subscribers for %s/%s", signal_id, sport, market)
        return

    text = _format_signal(fixture_label, league, minute, home_goals, away_goals,
                          market, suggested_bet, confidence)

    async with httpx.AsyncClient(timeout=10) as client:
        for uid in user_ids:
            try:
                r = await client.post(TG_API, json={
                    "chat_id": uid,
                    "text": text,
                    "parse_mode": "Markdown",
                })
                ok = r.status_code == 200 and r.json().get("ok")
                await models.record_notification(signal_id, uid, ok,
                                                  None if ok else r.text[:200])
            except Exception as e:
                log.exception("Send failed to %s: %s", uid, e)
                await models.record_notification(signal_id, uid, False, str(e)[:200])
