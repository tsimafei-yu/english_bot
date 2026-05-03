from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "English word trainer\n\n"
        "9:00 — 10 new words\n"
        "14:00, 20:00 — daily review\n\n"
        "/today — get today's words now\n"
        "/quiz — repeat today's words\n"
        "/add <word> — add word to flashcards\n"
        "/fc — start flashcard session\n"
        "/review — all seen words\n"
        "/stats — progress\n"
        "/stop — stop current session"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    s = db.get_stats()
    await update.message.reply_text(
        f"Learned: {s['learned']}\n"
        f"In progress: {s['in_progress']}\n"
        f"Flashcards: {s['flashcards']}\n"
        f"Streak: {s['streak']} days\n"
        f"Accuracy today: {s['accuracy_today']}%"
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.bot_data.get("session"):
        context.bot_data.pop("session")
        await update.message.reply_text("Session stopped.")
    else:
        await update.message.reply_text("Nothing is running.")
