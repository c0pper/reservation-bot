import asyncio
import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import db
import handlers

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


async def post_init(app: Application) -> None:
    db.init_db()
    logger.info("Database initialized at %s", db.get_db_path())


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not BOT_TOKEN:
        msg = "BOT_TOKEN environment variable is not set"
        raise RuntimeError(msg)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_command))
    app.add_handler(handlers.book_conv)
    app.add_handler(CommandHandler("my_bookings", handlers.my_bookings))
    app.add_handler(handlers.cancel_conv)
    app.add_handler(CommandHandler("available", handlers.available))
    app.add_handler(handlers.set_schedule_conv)
    app.add_handler(CommandHandler("admin", handlers.admin))

    logger.info("Bot is polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
