"""Telegram handlers. /start, menus, pinning, test signal."""
import logging
import random
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from bot import menus
from data import models
from engine.demo import DEMO_MATCHES, DEMO_SCENARIOS
from engine.enrichment import build_narrative
from engine.rules import Signal
from engine.notifier import _format_signal

log = logging.getLogger(__name__)


WELCOME = (
    "\u26a1 *Welcome to Blitzibet*\n\n"
    "Tap a sport to pick the markets you want signals for. "
    "Pin a market and we'll ping you the moment our engine spots "
    "an opportunity live.\n\n"
    "Tap to pin \u00b7 tap again to reset \u00b7 no typing needed."
)


async def start(update, context):
    user = update.effective_user
    if user is None:
        return
    await models.upsert_user(user.id, user.username)
    await update.message.reply_text(
        WELCOME,
        reply_markup=menus.main_menu(),
        parse_mode="Markdown",
    )


async def on_text(update, context):
    if update.message is None:
        return
    await update.message.reply_text(
        "Buttons only. Tap below to navigate.",
        reply_markup=menus.main_menu(),
    )


async def on_callback(update, context):
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    parts = query.data.split(":")
    ns = parts[0]

    if ns == "m":
        await _route_menu(parts, query, context)
    elif ns == "p":
        await _route_pin(parts, query, context)


def _ago(when):
    if when is None:
        return ""
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    secs = (now - when).total_seconds()
    if secs < 60:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _status(s):
    return {
        "won": "\u2705 WON",
        "lost": "\u274c LOST",
        "pending": "\u23f3 Pending",
    }.get(s, "\u23f3 Pending")


async def _send_resilient(bot, chat_id, text):
    try:
        sent = await bot.send_message(
            chat_id=chat_id, text=text, parse_mode="Markdown"
        )
        return sent.message_id
    except Exception as e:
        log.warning("Markdown failed: %s, retrying plain", e)
    try:
        sent = await bot.send_message(chat_id=chat_id, text=text)
        return sent.message_id
    except Exception:
        log.exception("Plain send also failed")
        return None


def _pick_scenario(pinned):
    matching = []
    if pinned:
        for s in DEMO_SCENARIOS:
            if s["market"] in pinned:
                matching.append(s)
    if matching:
        return random.choice(matching)
    return random.choice(DEMO_SCENARIOS)


async def _fire_test(bot, user_id, chat_id, scenario, match, label):
    fixture_id = 999000 + random.randint(0, 9999)
    fake_fixture = {
        "fixture": {
            "id": fixture_id,
            "status": {"elapsed": scenario["minute"]},
        },
        "teams": {
            "home": {
                "id": match["home_id"],
                "name": match["home_name"],
            },
            "away": {
                "id": match["away_id"],
                "name": match["away_name"],
            },
        },
        "league": {"name": match["league"]},
        "goals": {
            "home": scenario["home_goals"],
            "away": scenario["away_goals"],
        },
    }
    fake_stats = {
        match["home_id"]: scenario["home_stats"],
        match["away_id"]: scenario["away_stats"],
    }
    fake_signal = Signal(
        rule_name=scenario["rule_name"],
        market=scenario["market"],
        suggested_bet=scenario["suggested_bet"],
        confidence=scenario["confidence"],
        criteria=scenario["criteria"],
        tier=scenario["tier"],
    )

    signal_id = await models.insert_signal(
        sport="football",
        market=scenario["market"],
        fixture_id=fixture_id,
        fixture_label=label,
        league=match["league"],
        minute=scenario["minute"],
        rule_name=scenario["rule_name"],
        criteria=scenario["criteria"],
        suggested_bet=scenario["suggested_bet"],
        confidence=scenario["confidence"],
    )

    narrative = None
    try:
        narrative = await build_narrative(
            fake_fixture, fake_stats, [], fake_signal
        )
    except Exception:
        log.exception("Enrichment failed")

    text = _format_signal(
        fixture_label=label,
        league=match["league"],
        minute=scenario["minute"],
        home_goals=scenario["home_goals"],
        away_goals=scenario["away_goals"],
        market=scenario["market"],
        suggested_bet=scenario["suggested_bet"],
        confidence=scenario["confidence"],
        rule_name=scenario["rule_name"],
        tier=scenario["tier"],
        narrative=narrative,
    )

    note = None
    if not narrative:
        note = "AI block empty - ANTHROPIC_API_KEY missing on bot service"

    msg_id = await _send_resilient(bot, chat_id, text)
    if msg_id is None:
        raise RuntimeError("Telegram refused both Markdown and plain")

    return note


async def _route_menu(parts, query, context):
    action = parts[1] if len(parts) > 1 else "home"

    if action == "home":
        await query.edit_message_text(
            WELCOME,
            reply_markup=menus.main_menu(),
            parse_mode="Markdown",
        )
        return

    if action == "sport":
        sport = parts[2]
        if sport == "football":
            pins = await models.get_user_pins(query.from_user.id)
            pinned = set()
            for p in pins:
                if p["sport"] == "football":
                    pinned.add(p["market"])
            await query.edit_message_text(
                "*Football - pick your markets*\n\nPin all 6 to receive every signal.",
                reply_markup=menus.football_menu(pinned),
                parse_mode="Markdown",
            )
        return

    if action == "soon":
        sport = parts[2] if len(parts) > 2 else "this sport"
        await query.edit_message_text(
            f"*{sport.title()} coming soon*\n\nFootball is live now.",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )
        return

    if action == "live":
        active = await models.get_active_fixtures(within_minutes=3)
        if not active:
            text = "*Live signals*\n\nNo active games being watched right now."
        else:
            lines = ["*Live now*\n"]
            for fx in active:
                label = fx.get("fixture_label") or "Fixture"
                league = fx.get("league") or "-"
                home = fx.get("home_score", 0)
                away = fx.get("away_score", 0)
                minute = fx.get("minute", 0)
                lines.append(
                    f"*{label}*\n   {home} - {away} \u00b7 {minute}' \u00b7 {league}"
                )
            text = "\n\n".join(lines)
        await query.edit_message_text(
            text,
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )
        return

    if action == "history":
        signals = await models.get_recent_signals(limit=10)
        if not signals:
            text = "*History*\n\nNo signals yet."
        else:
            blocks = ["*Recent signals*  last 10 from the engine"]
            for s in signals:
                label = s.get("fixture_label") or "-"
                league = s.get("league") or ""
                market = (s.get("market") or "").upper()
                minute = s.get("minute") or 0
                bet = s.get("suggested_bet") or "-"
                conf = s.get("confidence") or 0
                fire = "\U0001f525" * min(conf, 5)
                ago = _ago(s.get("fired_at"))
                status = _status(s.get("status", ""))
                rule = (s.get("rule_name") or "").lower()
                is_watch = "watch" in rule
                head = "WATCH" if is_watch else "SIGNAL"
                emoji = "\U0001f440" if is_watch else "\U0001f3af"
                block = (
                    f"{emoji} *{head}* {fire} {conf}/5 _{ago}_\n"
                    f"*{label}*\n"
                    f"{league} \u00b7 {minute}'\n"
                    f"{market}\n"
                    f"_{bet}_\n"
                    f"{status}"
                )
                blocks.append(block)
            text = "\n\n".join(blocks)
        await query.edit_message_text(
            text,
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )
        return

    if action == "stats":
        s = await models.user_stats(query.from_user.id)
        decided = s["won"] + s["lost"]
        wr = f"{(s['won']/decided*100):.0f}%" if decided else "-"
        await query.edit_message_text(
            f"*Your stats*\n\nTotal: {s['total']}\nWon: {s['won']}\nLost: {s['lost']}\nPending: {s['pending']}\n\nWin rate: *{wr}*",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )
        return

    if action == "settings":
        await query.edit_message_text(
            "*Settings*\n\nPlan: Free trial\nNotifications: On",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )
        return

    if action == "test":
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        pins = await models.get_user_pins(user_id)
        pinned = set()
        for p in pins:
            if p["sport"] == "football":
                pinned.add(p["market"])

        scenario = _pick_scenario(pinned)
        match = random.choice(DEMO_MATCHES)
        label = f"{match['home_name']} v {match['away_name']}"
        market_up = scenario["market"].upper()

        try:
            await query.edit_message_text(
                f"*Generating intelligence report*\n\n*{label}*\n{market_up} \u00b7 {match['league']}\n\n_Claude is analyzing... ~15 seconds_",
                parse_mode="Markdown",
            )
        except Exception:
            pass

        try:
            note = await _fire_test(
                context.bot, user_id, chat_id, scenario, match, label
            )
            if note:
                msg = f"*Test sent* (with warning)\n\n{note}"
            else:
                msg = "*Test signal sent.* Check the message above."
            await query.edit_message_text(
                msg,
                reply_markup=menus.back_menu(),
                parse_mode="Markdown",
            )
        except Exception as e:
            log.exception("Test failed")
            await query.edit_message_text(
                f"*Test failed*\n\n{type(e).__name__}: {str(e)[:200]}",
                reply_markup=menus.back_menu(),
                parse_mode="Markdown",
            )
        return


async def _route_pin(parts, query, context):
    if len(parts) < 3:
        return
    sport = parts[1]
    market = parts[2]
    user_id = query.from_user.id

    now_pinned = await models.toggle_pin(user_id, sport, market)

    if sport != "football":
        return

    pins = await models.get_user_pins(user_id)
    pinned = set()
    for p in pins:
        if p["sport"] == "football":
            pinned.add(p["market"])
    verb = "Pinned" if now_pinned else "Removed"
    await query.edit_message_text(
        f"*Football - pick your markets*\n\n{verb} *{market}*",
        reply_markup=menus.football_menu(pinned),
        parse_mode="Markdown",
    )
