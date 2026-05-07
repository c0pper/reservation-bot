import os

from telegram import Bot

SITTER_USER_ID = os.environ.get("SITTER_USER_ID", "")


async def notify_sitter(bot: Bot, message: str) -> None:
    if SITTER_USER_ID:
        try:
            await bot.send_message(chat_id=SITTER_USER_ID, text=message)
        except Exception as e:
            print(f"Failed to notify sitter: {e}")
