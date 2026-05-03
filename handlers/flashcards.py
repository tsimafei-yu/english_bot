from telegram import Update
from telegram.ext import ContextTypes


async def add_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /add <word>")
        return

    db = context.bot_data["db"]
    ai = context.bot_data["ai"]
    word = context.args[0].lower().strip()

    if db.word_exists(word):
        word_id = db.get_word_id(word)
        db.add_to_flashcards(word_id)
        await update.message.reply_text(f"{word} added to flashcards.")
        return

    await update.message.reply_text(f"Looking up '{word}'...")

    word_data = await ai.get_word_info(word)

    if word_data:
        context.bot_data["pending_add"] = {
            "word": word,
            "translation": word_data["translation"],
            "example": word_data["example"]
        }
        await update.message.reply_text(
            f"{word} — {word_data['translation']}\n"
            f"{word_data['example']}\n\n"
            f"/yes to accept or type your own translation:"
        )
    else:
        context.bot_data["pending_add"] = {"word": word, "translation": None, "example": "—"}
        await update.message.reply_text(
            f"Could not fetch '{word}' automatically.\n"
            f"Type your translation:"
        )


async def yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.bot_data.get("pending_add")
    if not pending:
        return

    db = context.bot_data["db"]
    db.add_word(pending["word"], pending["translation"], pending["example"], source="custom")
    word_id = db.get_word_id(pending["word"])
    if word_id:
        db.add_to_flashcards(word_id)

    context.bot_data.pop("pending_add")
    await update.message.reply_text(f"Saved: {pending['word']} — {pending['translation']}")


async def flashcards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    words = db.get_flashcards()

    if not words:
        await update.message.reply_text("No flashcards. Add words with /add <word>")
        return

    context.bot_data["session"] = {
        "mode": "flashcard",
        "words": words,
        "current_index": 0,
        "correct": 0,
        "wrong": 0
    }

    await update.message.reply_text(f"Flashcard session. {len(words)} words. /stop to quit.")
    await _send_next_fc(context, update.effective_chat.id)


async def _send_next_fc(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    session = context.bot_data.get("session")
    if not session:
        return

    if session["current_index"] >= len(session["words"]):
        # all words done — reload remaining flashcards
        db = context.bot_data["db"]
        remaining = db.get_flashcards()
        if not remaining:
            total = session["correct"] + session["wrong"]
            accuracy = round(session["correct"] / total * 100) if total > 0 else 100
            await context.bot.send_message(
                chat_id,
                f"All flashcards learned! {session['correct']}/{total} ({accuracy}%)"
            )
            context.bot_data.pop("session", None)
            return
        session["words"] = remaining
        session["current_index"] = 0

    word = session["words"][session["current_index"]]
    await context.bot.send_message(chat_id, word["word"])


async def handle_flashcard_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, session: dict):
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
        graduated = db.mark_flashcard_answer(current_word["id"], correct=True)
        if graduated:
            await update.message.reply_text(
                f"Correct. {current_word['word']} — {current_word['translation']}\n"
                f"Learned! Removed from flashcards."
            )
        else:
            await update.message.reply_text(f"Correct. {current_word['word']} — {current_word['translation']}")
    else:
        session["wrong"] += 1
        db.mark_flashcard_answer(current_word["id"], correct=False)
        await update.message.reply_text(
            f"Wrong. {current_word['word']} — {current_word['translation']}\n"
            f"{current_word['example']}"
        )

    session["current_index"] += 1
    await _send_next_fc(context, update.effective_chat.id)
