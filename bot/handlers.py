"""Telegram handlers. /start, button callbacks, text rejection, chat cleanup,
on-demand test signal."""
import logging
import asyncio
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
    "⚡ *Welcome to Blitzibet*\n\n"
    "Tap a sport to pick the markets you want signals for. "
    "Pin a market and we'll ping you the moment our engine spots "
    "an opportunity live.\n\n"
    "Tap to pin · tap again to reset · no typing needed."
)


async def _wipe_chat_for(user_id: int, chat_id: int, bot, limit: int = 50) -> None:
    msg_ids = await models.pop_user_messages(user_id, limit=limit)
    for mid in msg_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
        await asyncio.sleep(0.02)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    await models.upsert_user(user.id, user.username)
    chat_id = update.effective_chat.id

    try:
        await update.message.delete()
    except Exception:
        pass

    await _wipe_chat_for(user.id, chat_id, context.bot)

    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=WELCOME,
        reply_markup=menus.main_menu(),
        parse_mode="Markdown",
    )
    await models.track_bot_message(user.id, sent.message_id)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user = update.effective_user
    chat_id = update.effective_chat.id

    try:
        await update.message.delete()
    except Exception:
        pass

    sent = await context.bot.send_message(
        chat_id=chat_id,
        text="👋 *Buttons only.*\n\n"
             "This bot doesn't read typed messages — tap below to navigate.",
        reply_markup=menus.main_menu(),
        parse_mode="Markdown",
    )
    if user is not None:
        await models.track_bot_message(user.id, sent.message_id)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    else:
        log.warning("Unknown callback ns: %s", query.data)


def _ago(when) -> str:
    if when is None:
        return ""
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    diff = now - when
    secs = diff.total_seconds()
    if secs < 60:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _status_label(status: str) -> str:
    return {
        "won": "✅ WON",
        "lost": "❌ LOST",
        "pending": "⏳ Pending",
        "void": "➖ Void",
    }.get(status, "⏳ Pending")


async def _send_signal_resilient(bot, chat_id: int, text: str) -> int | None:
    """Try Markdown first; fall back to plain text if Telegram rejects.
    Returns message_id on success, None on failure."""
    try:
        sent = await bot.send_message(
            chat_id=chat_id, text=text, parse_mode="Markdown",
        )
        return sent.message_id
    except Exception as e:
        log.warning("Markdown send failed (%s), retrying without parse_mode", e)
    try:
        sent = await bot.send_message(chat_id=chat_id, text=text)
        return sent.message_id
    except Exception:
        log.exception("Plain send also failed")
        return None


async def _fire_test_with(bot, user_id: int, chat_id: int,
                          scenario: dict, match: dict, label: str) -> str | None:
    """Run a synthetic signal through the full pipeline and send to one user.
    Returns a non-None note string if anything degraded (e.g. Claude missing)."""
    fake_fixture = {
        "fixture": {"id": 999000 + random.randint(0, 9999),
                    "status": {"elapsed": scenario["minute"]}},
        "teams": {
            "home": {"id": match["home_id"], "name": match["home_name"]},
            "away": {"id": match["away_id"], "name": match["away_name"]},
        },
        "league": {"name": match["league"]},
        "goals": {"home": scenario["home_goals"], "away": scenario["away_goals"]},
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
        sport="football", market=scenario["market"],
        fixture_id=fake_fixture["fixture"]["id"],
        fixture_label=label, league=match["league"],
        minute=scenario["minute"],
        rule_name=scenario["rule_name"],
        criteria=scenario["criteria"],
        suggested_bet=scenario["suggested_bet"],
        confidence=scenario["confidence"],
    )

    narrative = None
    try:
        narrative = await build_narrative(fake_fixture, fake_stats, [], fake_signal)
    except Exception:
        log.exception("Test enrichment failed")

    text = _format_signal(
        fixture_label=label, league=match["league"],
        minute=scenario["minute"],
        home_goals=scenario["home_goals"], away_goals=scenario["away_goals"],
        market=scenario["market"],
        suggested_bet=scenario["suggested_bet"],
        confidence=scenario["confidence"],
        rule_name=scenario["rule_name"],
        tier=scenario["tier"],
        narrative=narrative,
    )

    note = None
    if not narrative:
        note = "AI narrative is empty — `ANTHROPIC_API_KEY` is missing on the bot service"

    msg_id = await _send_signal_resilient(bot, chat_id, text)
    if msg_id is None:
        raise RuntimeError("Telegram refused both Markdown and plain text — signal text may be malformed")

    try:
        await models.track_bot_message(user_id, msg_id)
    except Exception:
        pass

    return note


async def _route_menu(parts: list[str], query, context) -> None:
    action = parts[1] if len(parts) > 1 else "home"

    if action == "home":
        await query.edit_message_text(
            WELCOME, reply_markup=menus.main_menu(), parse_mode="Markdown"
        )

    elif action == "sport":
        sport = parts[2]
        if sport == "football":
            pins = await models.get_user_pins(query.from_user.id)
            pinned_markets = {p["market"] for p in pins if p["sport"] == "football"}
            await query.edit_message_text(
                "⚽ *Football — pick your markets*\n\n"
                "📍 = pinned · tap again to remove\n"
                "_Pin all 6 to receive every signal_",
                reply_markup=menus.football_menu(pinned_markets),
                parse_mode="Markdown",
            )

    elif action == "soon":
        sport = parts[2] if len(parts) > 2 else "this sport"
        await query.edit_message_text(
            f"🚧 *{sport.title()} coming soon*\n\nFootball is live now.",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )

    elif action == "live":
        active = await models.get_active_fixtures(within_minutes=3)
        if not active:
            text = (
                "🔴 *Live signals*\n\n"
                "No active games being watched right now. "
                "Check back when football is playing."
            )
        else:
            lines = ["🔴 *Live now*  ·  games the engine is watching\n"]
            for fx in active:
                label = fx.get("fixture_label") or f"Fixture {fx.get('fixture_id')}"
                league = fx.get("league") or "—"
                lines.append(
                    f"⚽ *{label}*\n"
                    f"   {fx.get('home_score', 0)} — {fx.get('away_score', 0)}  ·  "
                    f"{fx.get('minute', 0)}'  ·  {league}\n"
                )
            lines.append("_updated within the last ~3 minutes_")
            text = "\n".join(lines)
        await query.edit_message_text(
            text, reply_markup=menus.back_menu(), parse_mode="Markdown"
        )

    elif action == "history":
        signals = await models.get_recent_signals(limit=10)
        if not signals:
            text = (
                "📜 *History*\n\n"
                "No signals have fired yet. Once games go live and the engine "
                "catches something, they'll show up here."
            )
        else:
            blocks = ["📜 *Recent signals*  ·  last 10 from the engine"]
            for s in signals:
                label = s.get("fixture_label") or "—"
                league = s.get("league") or ""
                market = (s.get("market") or "").upper()
                minute = s.get("minute") or 0
                bet = s.get("suggested_bet") or "—"
                conf = s.get("confidence") or 0
                fire = "🔥" * min(conf, 5)
                ago = _ago(s.get("fired_at"))
                status = _status_label(s.get("status", ""))
                rule = (s.get("rule_name") or "").lower()
                is_watch = "watch" in rule

                header_emoji = "👀" if is_watch else "🎯"
                header_label = "WATCH" if is_watch else "SIGNAL"

                block = (
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"{header_emoji} *{header_label}* · {fire} {conf}/5 · _{ago}_\n"
                    f"⚽ *{label}*\n"
                    f"📊 {league} · {minute}'\n"
                    f"📍 {market}\n"
                    f"💡 _{bet}_\n"
                    f"   {status}"
                )
                blocks.append(block)
            text = "\n\n".join(blocks)
        await query.edit_message_text(
            text, reply_markup=menus.back_menu(), parse_mode="Markdown"
        )

    elif action == "stats":
        s = await models.user_stats(query.from_user.id)
        total = s["total"]
        won = s["won"]
        lost = s["lost"]
        pending = s["pending"]
        decided = won + lost
        wr = f"{(won / decided * 100):.0f}%" if decided else "—"
        await query.edit_message_text(
            f"📊 *Your stats*\n\n"
            f"Total signals: {total}\n"
            f"✅ Won: {won}\n"
            f"❌ Lost: {lost}\n"
            f"⏳ Pending: {pending}\n\n"
            f"Win rate: *{wr}*",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )

    elif action == "settings":
        await query.edit_message_text(
            "⚙️ *Settings*\n\nPlan: Free trial\nNotifications: On\n\n"
            "Subscription management coming soon.",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )

    elif action == "test":
        user_id = query.from_user.id
        chat_id = query.message.chat_id

        # Pick scenario + match BEFORE showing loading state so we can name it
        pins = await models.get_user_pins(user_id)
        pinned_markets = {p["market"] for p in pins if p["sport"] == "football"}
        matching = [s for s in DEMO_SCENARIOS if s["market"] in pinned_markets] if pinned_markets else []
        scenario = random.choice(matching) if matching else random.choice(DEM
