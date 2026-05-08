import logging
import os

from telegram import Bot

logger = logging.getLogger(__name__)

SITTER_USER_IDS = [
    uid.strip()
    for uid in os.environ.get("SITTER_USER_ID", "").split(",")
    if uid.strip()
]


async def notify_sitter(bot: Bot, message: str) -> None:
    for sitter_id in SITTER_USER_IDS:
        try:
            await bot.send_message(chat_id=sitter_id, text=message)
            logger.debug("Sitter %s notified: %s", sitter_id, message.split("\n")[0])
        except Exception as e:
            logger.exception("Failed to notify sitter %s: %s", sitter_id, e)
