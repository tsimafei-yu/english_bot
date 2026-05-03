import logging
from telegram import Bot
from core.database import Database

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, bot: Bot, db: Database, chat_id: int):
        self.bot = bot
        self.db = db
        self.chat_id = chat_id

    async def send_morning_words(self):
        words = self.db.get_words_for_morning(count=10)
        if not words:
            await self.bot.send_message(self.chat_id, "No words left. Add new ones with /add")
            return

        self.db.save_daily_words([w["id"] for w in words])
        await self.bot.send_message(self.chat_id, "Words for today:\n")

        for i, word in enumerate(words, 1):
            await self.bot.send_message(
                self.chat_id,
                f"{i}. {word['word']} — {word['translation']}\n{word['example']}"
            )

        await self.bot.send_message(self.chat_id, "Review at 14:00 and 20:00.")

    async def send_quiz_reminder(self, bot_data: dict):
        words = self.db.get_words_for_quiz()
        if not words:
            return

        await self.bot.send_message(self.chat_id, "Time to review.")

        bot_data["session"] = {
            "mode": "daily",
            "words": words,
            "current_index": 0,
            "wrong_words": [],
            "correct": 0,
            "wrong": 0
        }

        await self.bot.send_message(self.chat_id, words[0]["word"])
