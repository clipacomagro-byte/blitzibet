"""Signal sender with risk-tier headers."""
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
    if not text:
        return text
    for char in ("_", "*", "[", "]", "(", ")", "`"):
        text = text.replace(char, "")
    return text


def _build_header(tier, risk, market, confidence):
    dots = CONFIDENCE_DOTS.get(confidence, "\U0001f7e0")
    market_up = market.upper()
    if tier == "watch":
        return (
            f"\U0001f440 *WATCHING \u00b7 {market_up}*  "
            f"\u00b7  {dots} {confidence}/5"
        )
    if risk == "safe":
        return (
            f"\U0001f7e2 *SAFE PLAY \u00b7 {market_up}*  "
            f"\u00b7  {dots} {confidence}/5"
        )
    if risk == "risky":
        return (
            f"\U0001f534 *RISKY PLAY \u00b7 {market_up}*  "
            f"\u00b7  {dots} {confidence}/5"
        )
    # default medium
    return (
        f"\U0001f7e1 *MEDIUM SIGNAL \u00b7 {market_up}*  "
        f"\u00b7  {dots} {confidence}/5"
    )


def _format_signal(fixture_label, league, minute, home_goals, away_goals,
                   market, suggested_bet, confidence, rule_name, tier,
                   narrative, risk="medium"):
    header = _build_header(tier, risk, market, confidence)

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
    if tier == "watch":
        parts.append(
            "\u2139\ufe0f _The engine is watching this game. "
            "Not a bet - just a heads-up._"
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
                          narrative=None, risk="medium"):
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
        risk=risk,
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
