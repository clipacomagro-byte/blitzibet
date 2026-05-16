"""Telegram bot entry point. Run with: python -m bot.main"""
import asyncio
import logging
import os
from datetime import datetime

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN
from bot.handlers import start, on_callback, on_text
from bot import menus


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("blitzibet.bot")


async def _notify_admin_on_boot(app):
    """Send a 'bot is online' message to admin after the bot finishes starting.
    Also wipes any previous bot messages so the chat stays clean."""
    admin_str = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    if not admin_str:
        log.info("ADMIN_TELEGRAM_ID not set, skipping boot notification")
        return

    try:
        admin_id = int(admin_str)
    except ValueError:
        log.warning("ADMIN_TELEGRAM_ID is not a number: %r", admin_str)
        return

    # Best-effort wipe of previous bot messages
    try:
        from data import models
        msg_ids = await models.pop_user_messages(admin_id, limit=50)
        for mid in msg_ids:
            try:
                await app.bot.delete_message(
                    chat_id=admin_id, message_id=mid
                )
            except Exception:
                pass
            await asyncio.sleep(0.02)
    except Exception:
        log.info("Chat wipe skipped (pop_user_messages unavailable)")

    # Send the boot notification
    try:
        now = datetime.now().strftime("%H:%M")
        sent = await app.bot.send_message(
            chat_id=admin_id,
            text=(
                "\U0001f504 *Bot redeployed and online*\n\n"
                f"All systems back up at {now}.\n"
                "Chat cleared. Fresh menu below."
            ),
            reply_markup=menus.main_menu(),
            parse_mode="Markdown",
        )

        try:
            from data import models
            await models.track_bot_message(admin_id, sent.message_id)
        except Exception:
            pass

        log.info("Boot notification sent to admin %d", admin_id)
    except Exception:
        log.exception("Failed to send boot notification")


def build_app():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(_notify_admin_on_boot)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_text)
    )
    return app


def main():
    log.info("Blitzibet bot starting...")
    app = build_app()
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
