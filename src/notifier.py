import logging
import os

from telegram import Bot
from telegram.error import Forbidden

logger = logging.getLogger(__name__)

SITTER_USER_IDS = [
    uid.strip()
    for uid in os.environ.get("SITTER_USER_ID", "").split(",")
    if uid.strip()
]

SITTER_NAMES = {
    "128727299": "Simone",
    "66475383": "Carolina",
}


async def notify_sitter(bot: Bot, message: str, latitude: float | None = None, longitude: float | None = None) -> None:
    for sitter_id in SITTER_USER_IDS:
        name = SITTER_NAMES.get(sitter_id, sitter_id)
        personal_msg = f"Ciao {name},\n\n{message}"
        try:
            if latitude and longitude:
                await bot.send_location(chat_id=sitter_id, latitude=latitude, longitude=longitude)
            await bot.send_message(chat_id=sitter_id, text=personal_msg)
            logger.debug("Sitter %s (%s) notified: %s", name, sitter_id, message.split("\n")[0])
        except Forbidden:
            logger.warning("Sitter %s (%s) has either blocked or didn't start the bot — skipping", name, sitter_id)
        except Exception as e:
            logger.exception("Failed to notify sitter %s (%s): %s", name, sitter_id, e)
