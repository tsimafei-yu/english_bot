from telegram import Update
from telegram.ext import ContextTypes


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    words = db.get_review_words()

    if not words:
        await update.message.reply_text("No words yet. Use /today first.")
        return

    context.bot_data["session"] = {
        "mode": "review",
        "words": words,
        "current_index": 0,
        "correct": 0,
        "wrong": 0
    }

    await update.message.reply_text(f"Review mode. {len(words)} words. /stop to quit.")
    word = words[0]
    await context.bot.send_message(update.effective_chat.id, word["word"])


async def handle_review_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, session: dict):
    db = context.bot_data["db"]
    ai = context.bot_data["ai"]
    user_answer = update.message.text.strip()
    current_word = session["words"][session["current_index"]]

    is_correct = await ai.check_answer(
        word=current_word["word"],
        correct_translation=current_word["translation"],
        user_answer=user_answer
    )

    if is_correct:
        session["correct"] += 1
        await update.message.reply_text(f"Correct. {current_word['word']} — {current_word['translation']}")
    else:
        session["wrong"] += 1
        await update.message.reply_text(
            f"Wrong. {current_word['word']} — {current_word['translation']}\n"
            f"{current_word['example']}"
        )

    session["current_index"] += 1

    if session["current_index"] >= len(session["words"]):
        total = session["correct"] + session["wrong"]
        accuracy = round(session["correct"] / total * 100) if total > 0 else 100
        await update.message.reply_text(
            f"Done. {session['correct']}/{total} correct ({accuracy}%)"
        )
        context.bot_data.pop("session", None)
    else:
        next_word = session["words"][session["current_index"]]
        await context.bot.send_message(update.effective_chat.id, next_word["word"])
