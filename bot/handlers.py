"""Telegram handlers. /start, menus, pinning, test signal per market."""
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
    "Tap a market once to turn it on, again to turn it off.\n\n"
    "No typing needed."
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


def _scenarios_for(market_key):
    return [s for s in DEMO_SCENARIOS if s["market"] == market_key]


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
                "*Football markets*\n\n"
                "\u2705 = ON   \u2b1c = OFF\n"
                "Tap to toggle.",
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
            text = "*Live signals*\n\nNo active games being watched."
        else:
            lines = ["*Live now*\n"]
            for fx in active:
                label = fx.get("fixture_label") or "Fixture"
                league = fx.get("league") or "-"
                home = fx.get("home_score", 0)
                away = fx.get("away_score", 0)
                minute = fx.get("minute", 0)
                lines.append(
                    f"*{label}*\n"
                    f"   {home} - {away}  {minute}'  {league}"
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
            blocks = ["*Recent signals*  last 10"]
            for s in signals:
                label = s.get("fixture_label") or "-"
                league = s.get("league") or ""
                market = (s.get("market") or "").upper()
                minute = s.get("minute") or 0
                conf = s.get("confidence") or 0
                fire = "\U0001f525" * min(conf, 5)
                ago = _ago(s.get("fired_at"))
                status = _status(s.get("status", ""))
                rule = (s.get("rule_name") or "").lower()
                is_watch = "watch" in rule
                head = "WATCH" if is_watch else "SIGNAL"
                block = (
                    f"*{head}* {fire} {conf}/5 _{ago}_\n"
                    f"*{label}*  {league}\n"
                    f"{market} {minute}'  {status}"
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
            f"*Your stats*\n\n"
            f"Total: {s['total']}\n"
            f"Won: {s['won']}\n"
            f"Lost: {s['lost']}\n"
            f"Pending: {s['pending']}\n\n"
            f"Win rate: *{wr}*",
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
        await query.edit_message_text(
            "*Pick a market to test*\n\n"
            "Fires a synthetic signal with full AI analysis "
            "for the market you choose.",
            reply_markup=menus.test_market_menu(),
            parse_mode="Markdown",
        )
        return

    if action == "testmarket":
        if len(parts) < 3:
            return
        market_key = parts[2]
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        market_scenarios = _scenarios_for(market_key)
        if not market_scenarios:
            await query.edit_message_text(
                f"No demo scenarios for *{market_key}* yet.\n\n"
                f"Try Goals, Corners, or Cards.",
                reply_markup=menus.back_menu(),
                parse_mode="Markdown",
            )
            return

        scenario = random.choice(market_scenarios)
        match = random.choice(DEMO_MATCHES)
        label = f"{match['home_name']} v {match['away_name']}"
        market_up = scenario["market"].upper()

        try:
            await query.edit_message_text(
                f"*Generating intelligence report*\n\n"
                f"*{label}*\n"
                f"{market_up}  {match['league']}\n\n"
                f"_Claude is analyzing... ~10 seconds_",
                parse_mode="Markdown",
            )
        except Exception:
            pass

        try:
            note = await _fire_test(
                context.bot, user_id, chat_id, scenario, match, label
            )
            if note:
                msg = f"*Test sent* (warning: {note})"
            else:
                msg = "*Test signal sent.* See the message above."
            await query.edit_message_text(
                msg,
                reply_markup=menus.back_menu(),
                parse_mode="Markdown",
            )
        except Exception as e:
            log.exception("Test failed")
            err_msg = str(e)[:200]
            await query.edit_message_text(
                f"*Test failed*\n\n{type(e).__name__}: {err_msg}",
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

    await models.toggle_pin(user_id, sport, market)

    if sport != "football":
        return

    pins = await models.get_user_pins(user_id)
    pinned = set()
    for p in pins:
        if p["sport"] == "football":
            pinned.add(p["market"])

    await query.edit_message_text(
        "*Football markets*\n\n"
        "\u2705 = ON   \u2b1c = OFF\n"
        "Tap to toggle.",
        reply_markup=menus.football_menu(pinned),
        parse_mode="Markdown",
    )
