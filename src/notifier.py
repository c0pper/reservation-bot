import logging
import os

from telegram import Bot

logger = logging.getLogger(__name__)

SITTER_USER_ID = os.environ.get("SITTER_USER_ID", "")


async def notify_sitter(bot: Bot, message: str) -> None:
    if SITTER_USER_ID:
        try:
            await bot.send_message(chat_id=SITTER_USER_ID, text=message)
            logger.debug("Sitter notified: %s", message.split("\n")[0])
        except Exception as e:
            logger.exception("Failed to notify sitter: %s", e)
