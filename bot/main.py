"""Entry point for the Telegram bot process.
Run with: python -m bot.main
Railway: declared as the 'bot' process in Procfile.
"""
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from config import TELEGRAM_BOT_TOKEN
from bot.handlers import start, on_callback


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("blitzibet.bot")


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    return app


def main() -> None:
    log.info("Blitzibet bot starting...")
    app = build_app()
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
