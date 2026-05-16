"""Sends signals to users whose pins match the signal's market."""
import logging
import httpx

from config import TELEGRAM_BOT_TOKEN
from data import models

log = logging.getLogger("blitzibet.notifier")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

CONFIDENCE_DOTS = {1: "🟠", 2: "🟠🟠", 3: "🟠🟠🟠", 4: "🟠🟠🟠🟠", 5: "🟠🟠🟠🟠🟠"}


def _format_signal(fixture_label, league, minute, home_goals, away_goals,
                   market, suggested_bet, confidence, rule_name, tier, narrative):
    is_watch = tier == "watch"
    if is_watch:
        header = f"👀 *WATCHING · {market.upper()}*  ·  {CONFIDENCE_DOTS.get(confidence, '🟠')} {confidence}/5"
    else:
        header = f"🔴 *LIVE SIGNAL · {market.upper()}*  ·  {CONFIDENCE_DOTS.get(confidence, '🟠')} {confidence}/5"
    parts = [
        header, "",
        f"⚽ *{fixture_label}*",
        f"📊 {home_goals} — {away_goals}  ·  {minute}'  ·  {league}",
    ]
    if narrative:
        parts.append("")
        parts.append(narrative)
    parts.append("")
    if is_watch:
        parts.append("ℹ️ _The engine is watching this game. Not a bet — just a heads-up._")
    else:
        parts.append("💡 *BET*")
        parts.append(suggested_bet)
    parts.append("")
    parts.append(f"_rule: {rule_name}  ·  powered by Blitzibet + Claude_")
    return "\n".join(parts)


async def dispatch_signal(signal_id, sport, market, fixture_label, league,
                          minute, home_goals, away_goals, suggested_bet,
                          confidence, rule_name="", tier="signal", narrative=None):
    user_ids = await models.get_users_for_market(sport, market)
    if not user_ids:
        log.info("Signal %s has no subscribers for %s/%s", signal_id, sport, market)
        return
    text = _format_signal(fixture_label, league, minute, home_goals, away_goals,
                          market, suggested_bet, confidence, rule_name, tier, narrative)
    async with httpx.AsyncClient(timeout=10) as client:
        for uid in user_ids:
            try:
                r = await client.post(TG_API, json={
                    "chat_id": uid, "text": text, "parse_mode": "Markdown",
                })
                ok = r.status_code == 200 and r.json().get("ok")
                await models.record_notification(signal_id, uid, ok,
                                                  None if ok else r.text[:200])
            except Exception as e:
                log.exception("Send failed to %s: %s", uid, e)
                await models.record_notification(signal_id, uid, False, str(e)[:200])
