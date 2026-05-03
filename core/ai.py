import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


class GeminiAI:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def _ask(self, prompt: str) -> str | None:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500}
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{GEMINI_URL}?key={self.api_key}", json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"Gemini error: {resp.status}")
                        return None
                    data = await resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"Gemini failed: {e}")
            return None

    async def get_word_info(self, word: str) -> dict | None:
        prompt = f"""Return JSON for the English word "{word}". Translation must be in Russian.
Strict format, no extra text:
{{
  "translation": "translation in Russian (1-3 words)",
  "example": "short English sentence using this word (max 12 words)"
}}"""
        result = await self._ask(prompt)
        if not result:
            return None
        try:
            clean = result.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(clean)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {result}")
            return None

    async def check_answer(self, word: str, correct_translation: str, user_answer: str) -> bool:
        user = user_answer.lower().strip()
        correct = correct_translation.lower().strip()

        if len(user) < 2:
            return False

        correct_words = [w.strip() for w in correct.replace(",", " ").split()]
        if user in correct_words or correct in user or user in correct:
            return True

        prompt = f"""English word: "{word}"
Correct translation: "{correct_translation}"
User answer: "{user_answer}"

Is this a correct translation? Accept synonyms and close meanings.
Reply with one word only: YES or NO"""

        result = await self._ask(prompt)
        if not result:
            return False
        return "YES" in result.upper()
