import sqlite3
from datetime import date, timedelta


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT UNIQUE NOT NULL,
                    translation TEXT NOT NULL,
                    example TEXT NOT NULL,
                    source TEXT DEFAULT 'oxford'
                );

                CREATE TABLE IF NOT EXISTS progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL,
                    times_seen INTEGER DEFAULT 0,
                    times_correct INTEGER DEFAULT 0,
                    times_wrong INTEGER DEFAULT 0,
                    last_seen TEXT,
                    next_review TEXT,
                    learned INTEGER DEFAULT 0,
                    correct_streak INTEGER DEFAULT 0,
                    FOREIGN KEY (word_id) REFERENCES words(id)
                );

                CREATE TABLE IF NOT EXISTS daily_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    FOREIGN KEY (word_id) REFERENCES words(id)
                );

                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    words_shown INTEGER DEFAULT 0,
                    correct INTEGER DEFAULT 0,
                    wrong INTEGER DEFAULT 0
                );
            """)

    def add_word(self, word: str, translation: str, example: str, source: str = "oxford"):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO words (word, translation, example, source) VALUES (?, ?, ?, ?)",
                (word.lower(), translation, example, source)
            )

    def add_custom_word(self, word: str, translation: str, example: str):
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO words (word, translation, example, source) VALUES (?, ?, ?, 'custom')",
                (word.lower(), translation, example)
            )
            word_id = cursor.lastrowid
            if word_id:
                conn.execute(
                    "INSERT OR IGNORE INTO progress (word_id, next_review) VALUES (?, ?)",
                    (word_id, date.today().isoformat())
                )

    def word_exists(self, word: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM words WHERE word = ?", (word.lower(),)).fetchone()
            return row is not None

    def get_words_for_morning(self, count: int = 10) -> list[dict]:
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT w.id, w.word, w.translation, w.example
                FROM words w
                JOIN progress p ON w.id = p.word_id
                WHERE p.learned = 0
                  AND (p.next_review IS NULL OR p.next_review <= ?)
                  AND (p.last_seen IS NULL OR p.last_seen < ?)
                ORDER BY p.next_review ASC, RANDOM()
                LIMIT ?
            """, (today, today, count)).fetchall()

            seen_ids = {r[0] for r in rows}

            if len(rows) < count:
                placeholders = ",".join("?" * len(seen_ids)) if seen_ids else "0"
                extra = conn.execute(f"""
                    SELECT w.id, w.word, w.translation, w.example
                    FROM words w
                    LEFT JOIN progress p ON w.id = p.word_id
                    WHERE p.id IS NULL
                      AND w.id NOT IN ({placeholders})
                    ORDER BY RANDOM()
                    LIMIT ?
                """, (*seen_ids, count - len(rows))).fetchall()
                rows.extend(extra)

            seen = set()
            unique = []
            for r in rows:
                if r[0] not in seen:
                    seen.add(r[0])
                    unique.append({"id": r[0], "word": r[1], "translation": r[2], "example": r[3]})

            return unique[:count]

    def save_daily_words(self, word_ids: list[int]):
        today = date.today().isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM daily_words WHERE date = ?", (today,))
            for word_id in word_ids:
                conn.execute(
                    "INSERT INTO daily_words (word_id, date) VALUES (?, ?)",
                    (word_id, today)
                )
                conn.execute(
                    "INSERT OR IGNORE INTO progress (word_id, last_seen, next_review) VALUES (?, ?, ?)",
                    (word_id, today, today)
                )
                conn.execute(
                    "UPDATE progress SET last_seen = ?, times_seen = times_seen + 1 WHERE word_id = ?",
                    (today, word_id)
                )

    def get_words_for_quiz(self) -> list[dict]:
        today = date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT w.id, w.word, w.translation, w.example
                FROM words w
                JOIN daily_words dw ON w.id = dw.word_id
                WHERE dw.date = ?
                ORDER BY RANDOM()
            """, (today,)).fetchall()
            return [{"id": r[0], "word": r[1], "translation": r[2], "example": r[3]} for r in rows]

    def get_random_review_word(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT w.id, w.word, w.translation, w.example
                FROM words w
                JOIN progress p ON w.id = p.word_id
                WHERE p.learned = 0 AND p.times_seen > 0
                ORDER BY RANDOM()
                LIMIT 1
            """).fetchone()
            return {"id": row[0], "word": row[1], "translation": row[2], "example": row[3]} if row else None

    def mark_answer(self, word_id: int, correct: bool):
        today = date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT times_correct, correct_streak FROM progress WHERE word_id = ?",
                (word_id,)
            ).fetchone()
            if not row:
                return

            times_correct, streak = row

            if correct:
                new_streak = streak + 1
                intervals = [1, 3, 7, 14, 30]
                interval = intervals[min(new_streak - 1, len(intervals) - 1)]
                next_review = (date.today() + timedelta(days=interval)).isoformat()
                learned = 1 if new_streak >= 5 else 0
                conn.execute("""
                    UPDATE progress SET
                        times_correct = ?,
                        correct_streak = ?,
                        next_review = ?,
                        learned = ?
                    WHERE word_id = ?
                """, (times_correct + 1, new_streak, next_review, learned, word_id))
            else:
                conn.execute("""
                    UPDATE progress SET
                        times_wrong = times_wrong + 1,
                        correct_streak = 0,
                        next_review = ?
                    WHERE word_id = ?
                """, (today, word_id))

            conn.execute("""
                INSERT INTO daily_stats (date, correct, wrong) VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    correct = correct + excluded.correct,
                    wrong = wrong + excluded.wrong
            """, (today, 1 if correct else 0, 0 if correct else 1))

    def get_stats(self) -> dict:
        today = date.today().isoformat()
        with self._connect() as conn:
            learned = conn.execute("SELECT COUNT(*) FROM progress WHERE learned = 1").fetchone()[0]
            in_progress = conn.execute(
                "SELECT COUNT(*) FROM progress WHERE learned = 0 AND times_seen > 0"
            ).fetchone()[0]
            today_row = conn.execute(
                "SELECT correct, wrong FROM daily_stats WHERE date = ?", (today,)
            ).fetchone()
            correct = today_row[0] if today_row else 0
            wrong = today_row[1] if today_row else 0
            total = correct + wrong
            accuracy = round(correct / total * 100) if total > 0 else 0
            streak = self._calculate_streak(conn)
            return {"learned": learned, "in_progress": in_progress, "streak": streak, "accuracy_today": accuracy}

    def _calculate_streak(self, conn) -> int:
        rows = conn.execute(
            "SELECT date FROM daily_stats WHERE correct > 0 ORDER BY date DESC"
        ).fetchall()
        if not rows:
            return 0
        streak = 0
        check_date = date.today()
        for (row_date,) in rows:
            d = date.fromisoformat(row_date)
            if d == check_date or d == check_date - timedelta(days=1):
                streak += 1
                check_date = d - timedelta(days=1)
            else:
                break
        return streak

    def update_streak(self):
        today = date.today().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO daily_stats (date, words_shown) VALUES (?, 0) ON CONFLICT(date) DO NOTHING",
                (today,)
            )

    def get_all_seen_words(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT w.id, w.word, w.translation, w.example
                FROM words w
                JOIN progress p ON w.id = p.word_id
                WHERE p.times_seen > 0
                ORDER BY RANDOM()
            """).fetchall()
            return [{"id": r[0], "word": r[1], "translation": r[2], "example": r[3]} for r in rows]

    def update_word_translation(self, word: str, translation: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE words SET translation = ? WHERE word = ?",
                (translation, word.lower())
            )

    def add_word_to_today(self, word_id: int):
        today = date.today().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO daily_words (word_id, date) VALUES (?, ?)",
                (word_id, today)
            )
            conn.execute(
                "INSERT OR IGNORE INTO progress (word_id, last_seen, next_review) VALUES (?, ?, ?)",
                (word_id, today, today)
            )

    def get_word_id(self, word: str) -> int | None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM words WHERE word = ?", (word.lower(),)).fetchone()
            return row[0] if row else None

    def get_flashcards(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT w.id, w.word, w.translation, w.example
                FROM words w
                JOIN progress p ON w.id = p.word_id
                WHERE p.times_seen > 0
                ORDER BY p.times_wrong DESC, RANDOM()
            """).fetchall()
            return [{"id": r[0], "word": r[1], "translation": r[2], "example": r[3]} for r in rows]