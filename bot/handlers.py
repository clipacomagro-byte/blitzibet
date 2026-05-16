"""Telegram handlers: /start, callback buttons, test signals, leagues.
NO MORE message deletion - history stays in chat."""
import logging
import random

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from config import TELEGRAM_BOT_TOKEN
from bot.menus import (
    main_menu, football_menu, settings_menu, history_menu, test_market_menu,
    leagues_menu,
)
from data import models
from engine.notifier import _format_signal, build_stats_block
from engine.demo import DEMO_MATCHES, DEMO_SCENARIOS
from engine.rules import Signal
from engine.enrichment import build_narrative

log = logging.getLogger("bot.handlers")

TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def _send_and_track(bot, chat_id, **kwargs):
    msg = await bot.send_message(chat_id=chat_id, **kwargs)
    try:
        await models.track_bot_message(chat_id, msg.message_id)
    except Exception:
        pass
    return msg


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    try:
        await models.upsert_user(user.id, user.username or "")
    except Exception:
        log.exception("upsert_user failed")

    text = (
        "\u26a1\ufe0f *Welcome to Blitzibet*\n\n"
        "Live in-play betting signals powered by AI.\n\n"
        "Tap a sport to pin the markets you care about, "
        "or hit *Test signal now* to see what a signal looks like."
    )
    await _send_and_track(
        context.bot, chat_id,
        text=text, parse_mode="Markdown",
        reply_markup=main_menu(),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await _send_and_track(
        context.bot, chat_id,
        text="Buttons only \U0001f447",
        reply_markup=main_menu(),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user_id = query.from_user.id

    if data == "main":
        await query.edit_message_text(
            "\u26a1\ufe0f *Blitzibet menu*",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return

    if data == "football":
        pins = await models.get_user_pins(user_id)
        pinned = {p["market"] for p in pins if p["sport"] == "football"}
        await query.edit_message_text(
            "\u26bd *Football markets*\n\n"
            "Tap a market to toggle alerts.",
            parse_mode="Markdown",
            reply_markup=football_menu(pinned),
        )
        return

    if data in ("tennis", "basketball", "volleyball"):
        sport_name = data.capitalize()
        await query.edit_message_text(
            f"*{sport_name}* coming soon \u23f3",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return

    if data.startswith("toggle:"):
        _, sport, market = data.split(":")
        await models.upsert_user(user_id, query.from_user.username or "")
        is_on = await models.toggle_pin(user_id, sport, market)
        log.info(
            "User %s toggled %s/%s = %s",
            user_id, sport, market, is_on,
        )
        pins = await models.get_user_pins(user_id)
        pinned = {p["market"] for p in pins if p["sport"] == sport}
        await query.edit_message_text(
            "\u26bd *Football markets*\n\n"
            "Tap a market to toggle alerts.",
            parse_mode="Markdown",
            reply_markup=football_menu(pinned),
        )
        return

    if data == "leagues":
        await models.upsert_user(user_id, query.from_user.username or "")
        enabled = set(await models.get_user_leagues(user_id))
        intro = (
            "\U0001f30d *Leagues*\n\n"
            "Tap to toggle. Nothing selected = *all leagues*.\n"
            "Select at least one to filter signals."
        )
        await query.edit_message_text(
            intro, parse_mode="Markdown",
            reply_markup=leagues_menu(enabled),
        )
        return

    if data.startswith("toggleleague:"):
        league_name = data.split(":", 1)[1]
        await models.upsert_user(user_id, query.from_user.username or "")
        is_on = await models.toggle_user_league(user_id, league_name)
        log.info(
            "User %s toggled league %s = %s",
            user_id, league_name, is_on,
        )
        enabled = set(await models.get_user_leagues(user_id))
        intro = (
            "\U0001f30d *Leagues*\n\n"
            "Tap to toggle. Nothing selected = *all leagues*.\n"
            "Select at least one to filter signals."
        )
        await query.edit_message_text(
            intro, parse_mode="Markdown",
            reply_markup=leagues_menu(enabled),
        )
        return

    if data == "livenow":
        rows = await models.get_active_fixtures(within_minutes=3, limit=15)
        if not rows:
            text = (
                "\U0001f534 *Live now*\n\n"
                "No matches currently being tracked. Check back soon."
            )
        else:
            lines = ["\U0001f534 *Live now*", ""]
            for r in rows:
                lines.append(
                    f"\u26bd {r.get('fixture_label') or '?'}  "
                    f"\u00b7 {r.get('minute') or 0}'  "
                    f"\u00b7 {r.get('home_score') or 0}-"
                    f"{r.get('away_score') or 0}"
                )
                lg = r.get("league")
                if lg:
                    lines.append(f"   _{lg}_")
            text = "\n".join(lines)
        await query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=main_menu(),
        )
        return

    if data == "history":
        stats = await models.user_stats(user_id)
        rows = await models.get_recent_signals(limit=15)

        won = int(stats.get("won") or 0)
        lost = int(stats.get("lost") or 0)
        pending = int(stats.get("pending") or 0)

        win_rate_str = ""
        if won + lost > 0:
            rate = int(round((won / (won + lost)) * 100))
            win_rate_str = f"  \u00b7  *{rate}%* hit rate"

        header = (
            "\U0001f4dc *Your Predictions*\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\u2705 *{won}* won  \u00b7  \u274c *{lost}* lost  "
            f"\u00b7  \u23f3 *{pending}* pending{win_rate_str}\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        )

        if not rows:
            text = header + "\nNo signals yet. Sit tight - they fire when patterns hit."
        else:
            lines = [header]
            for r in rows:
                status = r.get("status") or "pending"
                badge = "\u23f3"
                if status == "won":
                    badge = "\u2705"
                elif status == "lost":
                    badge = "\u274c"
                fx = r.get("fixture_label") or "?"
                market = (r.get("market") or "").upper()
                minute = r.get("minute") or 0
                bet = r.get("suggested_bet") or ""
                # truncate bet if too long
                if len(bet) > 60:
                    bet = bet[:57] + "..."
                lines.append(
                    f"{badge} *{fx}* \u00b7 {minute}'\n"
                    f"   _{market}_ \u2014 {bet}"
                )
            text = "\n\n".join(lines)
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=history_menu(),
        )
        return

    if data == "stats":
        s = await models.user_stats(user_id)
        won = int(s.get("won") or 0)
        lost = int(s.get("lost") or 0)
        rate_line = ""
        if won + lost > 0:
            rate = int(round((won / (won + lost)) * 100))
            rate_line = f"\n\U0001f3af Hit rate: *{rate}%*"
        text = (
            "\U0001f4ca *Your stats*\n\n"
            f"Total signals received: *{s.get('total', 0)}*\n"
            f"\u2705 Won: *{won}*\n"
            f"\u274c Lost: *{lost}*\n"
            f"\u23f3 Pending: *{s.get('pending', 0)}*"
            f"{rate_line}"
        )
        await query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=main_menu(),
        )
        return

    if data == "settings":
        await query.edit_message_text(
            "\u2699\ufe0f *Settings*",
            parse_mode="Markdown", reply_markup=settings_menu(),
        )
        return

    if data == "test":
        await query.edit_message_text(
            "\U0001f9ea *Test signal*\n\nPick a market to test:",
            parse_mode="Markdown",
            reply_markup=test_market_menu(),
        )
        return

    if data.startswith("testfire:"):
        market = data.split(":", 1)[1]
        await _fire_test(query, market)
        return


async def _fire_test(query, market_key):
    user_id = query.from_user.id
    market_scenarios = [
        s for s in DEMO_SCENARIOS if s["market"] == market_key
    ]
    if not market_scenarios:
        available = sorted({s["market"] for s in DEMO_SCENARIOS})
        await query.edit_message_text(
            f"No demo scenarios for *{market_key}* yet.\n\n"
            f"Available: {', '.join(available)}",
            parse_mode="Markdown",
            reply_markup=test_market_menu(),
        )
        return

    scenario = random.choice(market_scenarios)
    match = random.choice(DEMO_MATCHES)
    label = f"{match['home_name']} v {match['away_name']}"

    fake_fixture = {
        "fixture": {
            "id": 888000 + random.randint(0, 9999),
            "status": {"elapsed": scenario["minute"]},
        },
        "teams": {
            "home": {"id": match["home_id"], "name": match["home_name"]},
            "away": {"id": match["away_id"], "name": match["away_name"]},
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
        risk=scenario.get("risk", "medium"),
    )

    narrative = None
    try:
        narrative = await build_narrative(
            fake_fixture, fake_stats, [], fake_signal,
        )
    except Exception:
        log.exception("test narrative failed")

    stats_block = build_stats_block(
        fake_stats, match["home_id"], match["away_id"],
    )

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
        risk=scenario.get("risk", "medium"),
        stats_block=stats_block,
    )

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.post(f"{TG_API}/sendMessage", json={
                "chat_id": user_id,
                "text": text,
                "parse_mode": "Markdown",
            })
            response_data = r.json()
            if not response_data.get("ok"):
                log.warning(
                    "Markdown failed: %s, retrying plain",
                    response_data.get("description", ""),
                )
                r = await client.post(f"{TG_API}/sendMessage", json={
                    "chat_id": user_id,
                    "text": text,
                })
                response_data = r.json()
            if response_data.get("ok"):
                msg_id = response_data.get("result", {}).get("message_id")
                if msg_id:
                    try:
                        await models.track_bot_message(user_id, msg_id)
                    except Exception:
                        pass
        except Exception as e:
            log.exception("Test send failed: %s", e)

    await query.edit_message_text(
        "\u2705 *Test signal sent* \u2014 check above.",
        parse_mode="Markdown",
        reply_markup=test_market_menu(),
    )
