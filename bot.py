import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from core.database import Database
from core.ai import GeminiAI
from core.scheduler import Scheduler
from handlers.common import start, stats, stop
from handlers.daily import today, quiz, handle_daily_answer
from handlers.flashcards import add_word, yes, flashcards, handle_flashcard_answer
from handlers.review import review, handle_review_answer

load_dotenv()

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YOUR_CHAT_ID = int(os.getenv("YOUR_CHAT_ID"))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # pending /add confirmation
    pending = context.bot_data.get("pending_add")
    if pending:
        db = context.bot_data["db"]
        translation = update.message.text.strip()
        example = pending.get("example") or "—"
        db.add_word(pending["word"], translation, example, source="custom")
        word_id = db.get_word_id(pending["word"])
        if word_id:
            db.add_to_flashcards(word_id)
        context.bot_data.pop("pending_add")
        await update.message.reply_text(f"Saved: {pending['word']} — {translation}")
        return

    session = context.bot_data.get("session")
    if not session:
        return

    mode = session.get("mode")
    if mode == "daily":
        await handle_daily_answer(update, context, session)
    elif mode == "flashcard":
        await handle_flashcard_answer(update, context, session)
    elif mode == "review":
        await handle_review_answer(update, context, session)


def main():
    db = Database("words.db")
    ai = GeminiAI(os.getenv("GEMINI_API_KEY"))

    # load words if db is empty
    from data.words import WORDS
    for word, translation, example in WORDS:
        if not db.word_exists(word):
            db.add_word(word, translation, example)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.bot_data["db"] = db
    app.bot_data["ai"] = ai

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("add", add_word))
    app.add_handler(CommandHandler("yes", yes))
    app.add_handler(CommandHandler("fc", flashcards))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    scheduler = Scheduler(app.bot, db, YOUR_CHAT_ID)
    apscheduler = AsyncIOScheduler()
    apscheduler.add_job(scheduler.send_morning_words, "cron", hour=7, minute=0)
    apscheduler.add_job(scheduler.send_quiz_reminder, "cron", hour=12, minute=0,
                        kwargs={"bot_data": app.bot_data})
    apscheduler.add_job(scheduler.send_quiz_reminder, "cron", hour=18, minute=0,
                        kwargs={"bot_data": app.bot_data})
    apscheduler.start()

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
