import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "habits.db"

FREE_HABIT_LIMIT = 3


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                is_premium INTEGER DEFAULT 0,
                premium_until TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS habits (
                habit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                remind_time TEXT DEFAULT '09:00',
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS completions (
                completion_id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER,
                completed_date TEXT,
                FOREIGN KEY (habit_id) REFERENCES habits (habit_id)
            )
        """)


def ensure_user(user_id: int, username: str):
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
                (user_id, username, datetime.utcnow().isoformat()),
            )


def is_premium(user_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT is_premium, premium_until FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return False
        if not row["is_premium"]:
            return False
        if row["premium_until"]:
            until = datetime.fromisoformat(row["premium_until"])
            if until < datetime.utcnow():
                return False
        return True


def set_premium(user_id: int, until_iso: str | None = None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?",
            (until_iso, user_id),
        )


def count_habits(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM habits WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["c"]


def add_habit(user_id: int, name: str, remind_time: str = "09:00") -> int | None:
    if not is_premium(user_id) and count_habits(user_id) >= FREE_HABIT_LIMIT:
        return None
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO habits (user_id, name, remind_time, created_at) VALUES (?, ?, ?, ?)",
            (user_id, name, remind_time, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def list_habits(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM habits WHERE user_id = ? ORDER BY habit_id", (user_id,)
        ).fetchall()


def remove_habit(user_id: int, habit_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM habits WHERE habit_id = ? AND user_id = ?", (habit_id, user_id)
        )
        return cur.rowcount > 0


def set_remind_time(user_id: int, habit_id: int, remind_time: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE habits SET remind_time = ? WHERE habit_id = ? AND user_id = ?",
            (remind_time, habit_id, user_id),
        )
        return cur.rowcount > 0


def mark_done(user_id: int, habit_id: int) -> bool:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_conn() as conn:
        habit = conn.execute(
            "SELECT 1 FROM habits WHERE habit_id = ? AND user_id = ?", (habit_id, user_id)
        ).fetchone()
        if not habit:
            return False
        already = conn.execute(
            "SELECT 1 FROM completions WHERE habit_id = ? AND completed_date = ?",
            (habit_id, today),
        ).fetchone()
        if already:
            return False
        conn.execute(
            "INSERT INTO completions (habit_id, completed_date) VALUES (?, ?)",
            (habit_id, today),
        )
        return True


def get_streak(habit_id: int) -> int:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT completed_date FROM completions WHERE habit_id = ? ORDER BY completed_date DESC",
            (habit_id,),
        ).fetchall()
    if not rows:
        return 0
    dates = [datetime.strptime(r["completed_date"], "%Y-%m-%d").date() for r in rows]
    streak = 1
    for i in range(1, len(dates)):
        if (dates[i - 1] - dates[i]).days == 1:
            streak += 1
        else:
            break
    return streak


def all_habits_for_reminders():
    with get_conn() as conn:
        return conn.execute(
            "SELECT h.*, u.user_id as uid FROM habits h JOIN users u ON h.user_id = u.user_id"
        ).fetchall()
