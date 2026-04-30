import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
import os

from database import Database
from ai import GeminiAI
from scheduler import Scheduler

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YOUR_CHAT_ID = int(os.getenv("YOUR_CHAT_ID"))

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database("words.db")
ai = GeminiAI(os.getenv("GEMINI_API_KEY"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "English word trainer\n\n"
        "9:00 — 10 new words\n"
        "14:00, 20:00 — review\n\n"
        "/today — get today's words now\n"
        "/quiz — start review now\n"
        "/word — random word\n"
        "/stats — progress\n"
        "/add <word> — add custom word"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats()
    await update.message.reply_text(
        f"Learned: {s['learned']}\n"
        f"In progress: {s['in_progress']}\n"
        f"Streak: {s['streak']} days\n"
        f"Accuracy today: {s['accuracy_today']}%"
    )


async def add_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /add <word>")
        return

    word = context.args[0].lower().strip()

    if db.word_exists(word):
        await update.message.reply_text(f"{word} is already in your list.")
        return

    await update.message.reply_text(f"Looking up '{word}'...")

    word_data = await ai.get_word_info(word)
    if not word_data:
        await update.message.reply_text("Could not find the word. Try again.")
        return

    db.add_custom_word(word, word_data["translation"], word_data["example"])
    await update.message.reply_text(
        f"{word} — {word_data['translation']}\n"
        f"{word_data['example']}"
    )


async def random_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    word = db.get_random_review_word()
    if not word:
        await update.message.reply_text("No words to review yet.")
        return

    await update.message.reply_text(
        f"{word['word']} — {word['translation']}\n"
        f"{word['example']}"
    )


async def send_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scheduler = Scheduler(context.bot, db, YOUR_CHAT_ID)
    await scheduler.send_morning_words()


async def quiz_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_quiz(context, update.effective_chat.id)


async def start_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    words = db.get_words_for_quiz()

    if not words:
        await context.bot.send_message(chat_id, "No words to review right now.")
        return

    context.bot_data["quiz"] = {
        "words": words,
        "current_index": 0,
        "wrong_words": [],
        "correct": 0,
        "wrong": 0
    }

    await context.bot.send_message(chat_id, f"Review started. {len(words)} words.")
    await send_next_quiz_word(context, chat_id)


async def send_next_quiz_word(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    quiz = context.bot_data.get("quiz")
    if not quiz:
        return

    idx = quiz["current_index"]
    if idx >= len(quiz["words"]):
        await finish_quiz_round(context, chat_id)
        return

    word = quiz["words"][idx]
    await context.bot.send_message(chat_id, word["word"])


async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quiz = context.bot_data.get("quiz")
    if not quiz:
        return

    user_answer = update.message.text.strip()
    current_word = quiz["words"][quiz["current_index"]]

    is_correct = await ai.check_answer(
        word=current_word["word"],
        correct_translation=current_word["translation"],
        user_answer=user_answer
    )

    if is_correct:
        quiz["correct"] += 1
        db.mark_answer(current_word["id"], correct=True)
        await update.message.reply_text(f"Correct. {current_word['word']} — {current_word['translation']}")
    else:
        quiz["wrong"] += 1
        quiz["wrong_words"].append(current_word)
        db.mark_answer(current_word["id"], correct=False)
        await update.message.reply_text(
            f"Wrong. {current_word['word']} — {current_word['translation']}\n"
            f"{current_word['example']}"
        )

    quiz["current_index"] += 1
    await send_next_quiz_word(context, update.effective_chat.id)


async def finish_quiz_round(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    quiz = context.bot_data.get("quiz")
    wrong_words = quiz.get("wrong_words", [])

    if wrong_words:
        await context.bot.send_message(chat_id, f"Repeating {len(wrong_words)} missed words.")
        context.bot_data["quiz"] = {
            "words": wrong_words,
            "current_index": 0,
            "wrong_words": [],
            "correct": quiz["correct"],
            "wrong": 0
        }
        await send_next_quiz_word(context, chat_id)
    else:
        total = quiz["correct"] + quiz["wrong"]
        accuracy = round(quiz["correct"] / total * 100) if total > 0 else 100
        await context.bot.send_message(
            chat_id,
            f"Done. {quiz['correct']}/{total} correct ({accuracy}%)"
        )
        db.update_streak()
        context.bot_data.pop("quiz", None)


def main():
    from load_words_offline import WORDS
    for word, translation, example in WORDS:
        if not db.word_exists(word):
            db.add_word(word, translation, example)

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("add", add_word))
    app.add_handler(CommandHandler("word", random_word))
    app.add_handler(CommandHandler("quiz", quiz_now))
    app.add_handler(CommandHandler("today", send_today))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quiz_answer))

    scheduler = Scheduler(app.bot, db, YOUR_CHAT_ID)
    apscheduler = AsyncIOScheduler()
    apscheduler.add_job(scheduler.send_morning_words, "cron", hour=9, minute=0)
    apscheduler.add_job(scheduler.send_quiz_reminder, "cron", hour=14, minute=0,
                        kwargs={"bot_data": app.bot_data})
    apscheduler.add_job(scheduler.send_quiz_reminder, "cron", hour=20, minute=0,
                        kwargs={"bot_data": app.bot_data})
    apscheduler.start()

    logger.info("Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
