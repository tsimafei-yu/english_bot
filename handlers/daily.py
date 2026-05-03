from telegram import Update
from telegram.ext import ContextTypes
from core.scheduler import Scheduler


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    chat_id = update.effective_chat.id
    scheduler = Scheduler(context.bot, db, chat_id)
    await scheduler.send_morning_words()


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    words = db.get_words_for_quiz()

    if not words:
        await update.message.reply_text("No words for today yet. Use /today first.")
        return

    context.bot_data["session"] = {
        "mode": "daily",
        "words": words,
        "current_index": 0,
        "wrong_words": [],
        "correct": 0,
        "wrong": 0
    }

    await update.message.reply_text(f"Daily review. {len(words)} words.")
    await _send_next(context, update.effective_chat.id)


async def _send_next(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    session = context.bot_data.get("session")
    if not session:
        return

    idx = session["current_index"]
    if idx >= len(session["words"]):
        await _finish_round(context, chat_id)
        return

    word = session["words"][idx]
    await context.bot.send_message(chat_id, word["word"])


async def _finish_round(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    session = context.bot_data.get("session")
    wrong_words = session.get("wrong_words", [])

    if wrong_words:
        await context.bot.send_message(chat_id, f"Repeating {len(wrong_words)} missed words.")
        session.update({
            "words": wrong_words,
            "current_index": 0,
            "wrong_words": [],
            "wrong": 0
        })
        await _send_next(context, chat_id)
    else:
        total = session["correct"] + session["wrong"]
        accuracy = round(session["correct"] / total * 100) if total > 0 else 100
        await context.bot.send_message(
            chat_id,
            f"Done. {session['correct']}/{total} correct ({accuracy}%)"
        )
        context.bot_data["db"].update_streak()
        context.bot_data.pop("session", None)


async def handle_daily_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, session: dict):
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
        db.mark_daily_answer(current_word["id"], correct=True)
        await update.message.reply_text(f"Correct. {current_word['word']} — {current_word['translation']}")
    else:
        session["wrong"] += 1
        session["wrong_words"].append(current_word)
        db.mark_daily_answer(current_word["id"], correct=False)
        await update.message.reply_text(
            f"Wrong. {current_word['word']} — {current_word['translation']}\n"
            f"{current_word['example']}"
        )

    session["current_index"] += 1
    await _send_next(context, update.effective_chat.id)
