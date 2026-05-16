"""Sends signals. Sanitizes rule names + has Markdown->plain fallback."""
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


def _safe_rule_name(rule_name):
    """Replace underscores so Telegram italic doesn't break."""
    return (rule_name or "").replace("_", "-")


def build_stats_block(stats_by_team, home_id, away_id):
    home = stats_by_team.get(home_id) or {}
    away = stats_by_team.get(away_id) or {}

    def pair(key, suffix=""):
        h = home.get(key)
        a = away.get(key)
        h_str = "-" if h is None else f"{h}{suffix}"
        a_str = "-" if a is None else f"{a}{suffix}"
        return f"{h_str} / {a_str}"

    lines = [
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        "\U0001f4ca *LIVE STATS*  _(home / away)_",
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        f"\U0001f3af Shots on goal: {pair('Shots on Goal')}",
        f"\U0001f4cc Total shots: {pair('Total Shots')}",
        f"\U0001f6a9 Corners: {pair('Corner Kicks')}",
        f"\u2694\ufe0f Dangerous attacks: {pair('Dangerous Attacks')}",
        f"\u2696\ufe0f Possession: {pair('Ball Possession', '%')}",
    ]
    if home.get("Goalkeeper Saves") is not None or away.get("Goalkeeper Saves") is not None:
        lines.append(f"\U0001f9e4 GK saves: {pair('Goalkeeper Saves')}")
    if home.get("Yellow Cards") is not None or away.get("Yellow Cards") is not None:
        lines.append(f"\U0001f7e8 Yellow cards: {pair('Yellow Cards')}")
    if home.get("Fouls") is not None or away.get("Fouls") is not None:
        lines.append(f"\U0001f9b5 Fouls: {pair('Fouls')}")

    return "\n".join(lines)


def _build_header(tier, risk, market, confidence):
    dots = CONFIDENCE_DOTS.get(confidence, "\U0001f7e0")
    m = market.upper()
    if tier == "watch":
        return f"\U0001f440 *WATCHING \u00b7 {m}*  \u00b7  {dots} {confidence}/5"
    if risk == "urgent":
        return f"\U0001f6a8 *BIG MOMENT \u00b7 {m}*  \u00b7  {dots} {confidence}/5"
    if risk == "safe":
        return f"\U0001f7e2 *SAFE PLAY \u00b7 {m}*  \u00b7  {dots} {confidence}/5"
    if risk == "risky":
        return f"\U0001f534 *RISKY PLAY \u00b7 {m}*  \u00b7  {dots} {confidence}/5"
    return f"\U0001f7e1 *MEDIUM SIGNAL \u00b7 {m}*  \u00b7  {dots} {confidence}/5"


def _format_signal(fixture_label, league, minute, home_goals, away_goals,
                   market, suggested_bet, confidence, rule_name, tier,
                   narrative, risk="medium", stats_block=None):
    safe_rule = _safe_rule_name(rule_name)
    parts = [
        _build_header(tier, risk, market, confidence),
        "",
        f"\u26bd *{fixture_label}*",
        f"\U0001f3df {league} \u00b7 {minute}' \u00b7 "
        f"{home_goals} \u2014 {away_goals}",
    ]

    if stats_block:
        parts.append("")
        parts.append(stats_block)

    if narrative:
        clean = _sanitize_for_markdown(narrative)
        parts.append("")
        parts.append(clean)

    parts.append("")
    if tier == "watch":
        parts.append("\u2139\ufe0f _Watching only. Not a bet recommendation._")
    else:
        parts.append("\U0001f4a1 *BET*")
        parts.append(suggested_bet)

    parts.append("")
    parts.append(
        f"_rule: {safe_rule}  \u00b7  powered by Blitzibet + Claude_"
    )
    return "\n".join(parts)


async def _send_to_user(client, uid, text):
    """Try Markdown first, fall back to plain on 400. Returns (ok, msg_id, error)."""
    try:
        r = await client.post(TG_API, json={
            "chat_id": uid,
            "text": text,
            "parse_mode": "Markdown",
        })
        data = r.json()
        if r.status_code == 200 and data.get("ok"):
            msg_id = data.get("result", {}).get("message_id")
            return True, msg_id, None
        log.warning(
            "Markdown send failed for %s: %s - retrying plain",
            uid, data.get("description", "")[:100],
        )
    except Exception as e:
        log.warning("Markdown send raised for %s: %s - retrying plain", uid, e)

    try:
        r = await client.post(TG_API, json={
            "chat_id": uid,
            "text": text,
        })
        data = r.json()
        if r.status_code == 200 and data.get("ok"):
            msg_id = data.get("result", {}).get("message_id")
            return True, msg_id, None
        return False, None, (data.get("description") or r.text)[:200]
    except Exception as e:
        return False, None, str(e)[:200]


async def dispatch_signal(signal_id, sport, market, fixture_label, league,
                          minute, home_goals, away_goals, suggested_bet,
                          confidence, rule_name="", tier="signal",
                          narrative=None, risk="medium", stats_block=None):
    user_ids = await models.get_users_for_market(sport, market, league=league)
    if not user_ids:
        log.info(
            "Signal %s no subscribers for %s/%s/%s",
            signal_id, sport, market, league,
        )
        return

    text = _format_signal(
        fixture_label, league, minute, home_goals, away_goals,
        market, suggested_bet, confidence, rule_name, tier, narrative,
        risk=risk, stats_block=stats_block,
    )

    async with httpx.AsyncClient(timeout=10) as client:
        for uid in user_ids:
            try:
                ok, msg_id, error = await _send_to_user(client, uid, text)
                await models.record_notification(signal_id, uid, ok, error)
                if ok and msg_id:
                    try:
                        await models.track_bot_message(uid, msg_id)
                    except Exception:
                        pass
            except Exception as e:
                log.exception("Send failed to %s: %s", uid, e)
                await models.record_notification(
                    signal_id, uid, False, str(e)[:200],
                )
