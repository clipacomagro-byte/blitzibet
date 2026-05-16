"""Telegram handlers. Routes /start and button taps."""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot import menus
from data import models

log = logging.getLogger(__name__)


WELCOME = (
    "⚡ *Welcome to Blitzibet*\n\n"
    "Tap a sport to pick the markets you want signals for. "
    "Pin a market and we'll ping you the moment our engine spots "
    "an opportunity live.\n\n"
    "Tap to pin · tap again to reset · no typing needed."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return
    await models.upsert_user(user.id, user.username)
    await update.message.reply_text(
        WELCOME, reply_markup=menus.main_menu(), parse_mode="Markdown"
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    parts = query.data.split(":")
    ns = parts[0]

    if ns == "m":
        await _route_menu(parts, query)
    elif ns == "p":
        await _route_pin(parts, query)
    else:
        log.warning("Unknown callback ns: %s", query.data)


async def _route_menu(parts: list[str], query) -> None:
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
                "📍 = pinned · tap again to remove",
                reply_markup=menus.football_menu(pinned_markets),
                parse_mode="Markdown",
            )

    elif action == "soon":
        sport = parts[2] if len(parts) > 2 else "this sport"
        await query.edit_message_text(
            f"🚧 *{sport.title()} coming soon*\n\n"
            "Football is live now. More sports rolling out next.",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )

    elif action == "live":
        active = await models.get_active_fixtures(within_minutes=3)
        if not active:
            text = (
                "🔴 *Live signals*\n\n"
                "No active games being watched right now. "
                "Either no football is currently live, or the engine hasn't "
                "had time to snapshot yet. Check back soon."
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

    elif action == "upcoming":
        await query.edit_message_text(
            "📅 *Upcoming*\n\n"
            "Scheduled games matching your filters will show here. "
            "Coming in the next update.",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
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
            "⚙️ *Settings*\n\n"
            "Plan: Free trial\n"
            "Notifications: On\n\n"
            "Subscription management coming soon.",
            reply_markup=menus.back_menu(),
            parse_mode="Markdown",
        )


async def _route_pin(parts: list[str], query) -> None:
    if len(parts) < 3:
        return
    sport, market = parts[1], parts[2]
    user_id = query.from_user.id

    now_pinned = await models.toggle_pin(user_id, sport, market)

    if sport == "football":
        pins = await models.get_user_pins(user_id)
        pinned_markets = {p["market"] for p in pins if p["sport"] == "football"}
        verb = "Pinned" if now_pinned else "Removed"
        await query.edit_message_text(
            f"⚽ *Football — pick your markets*\n\n"
            f"✓ {verb} *{market}*\n"
            f"📍 = pinned · tap again to remove",
            reply_markup=menus.football_menu(pinned_markets),
            parse_mode="Markdown",
        )
