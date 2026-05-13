#!/usr/bin/env python3
"""Schedules today's vocabulary session - selects 5 words and creates a session."""

import json
import random
from datetime import date

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "vocab.db"


def get_today():
    return date.today().isoformat()


def init_pointer_table(conn):
    """Create current_pointer table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS current_pointer (
            date TEXT PRIMARY KEY,
            pointer INTEGER DEFAULT 0
        )
    """)


def get_today_session(conn):
    """Check if a session already exists for today."""
    today = get_today()
    cur = conn.execute("SELECT word_ids FROM sessions WHERE date = ?", (today,))
    row = cur.fetchone()
    if row:
        return json.loads(row[0])
    return None


def select_words(conn, count=5):
    """Select words based on priority: times_shown=0, then times_confirmed=0, then oldest last_shown."""
    # Get all words with their progress data (no ORDER BY limit)
    cur = conn.execute("""
        SELECT w.id, w.word, w.meaning,
               COALESCE(p.times_shown, 0) as times_shown,
               COALESCE(p.times_confirmed, 0) as times_confirmed,
               p.last_shown
        FROM words w
        LEFT JOIN progress p ON w.id = p.word_id
    """)
    all_words = cur.fetchall()

    # Separate by priority
    never_shown = [w for w in all_words if w[3] == 0]  # times_shown = 0
    never_confirmed = [w for w in all_words if w[4] == 0 and w[3] > 0]  # times_confirmed = 0
    others = [w for w in all_words if w[3] > 0 and w[4] > 0]  # both shown and confirmed

    # Shuffle each group
    random.shuffle(never_shown)
    random.shuffle(never_confirmed)
    random.shuffle(others)

    # Combine: never_shown first, then never_confirmed, then others
    prioritized = never_shown + never_confirmed + others

    # If we have fewer than count words, return all of them
    if len(prioritized) <= count:
        return prioritized

    return prioritized[:count]


def save_session(conn, word_ids):
    """Save today's session to the sessions table."""
    today = get_today()
    conn.execute(
        "INSERT INTO sessions (date, word_ids) VALUES (?, ?)",
        (today, json.dumps(word_ids))
    )
    conn.commit()


def init_pointer(conn):
    """Initialize pointer for today."""
    today = get_today()
    conn.execute(
        "INSERT OR REPLACE INTO current_pointer (date, pointer) VALUES (?, 0)",
        (today,)
    )
    conn.commit()


def print_words(words):
    """Print the selected words clearly."""
    print(f"\n{'='*55}")
    print(f"  Today's Vocabulary Session ({get_today()})")
    print(f"{'='*55}")
    for i, w in enumerate(words, 1):
        # Handle both 3-tuple (existing session) and 6-tuple (new selection)
        if len(w) == 3:
            word_id, word, meaning = w
        else:
            word_id, word, meaning = w[0], w[1], w[2]
        print(f"  {i}. {word}")
        print(f"     Meaning: {meaning}")
        print()
    print(f"{'='*55}")
    print(f"  Total words: {len(words)}")
    print(f"{'='*55}\n")


def main():
    conn = sqlite3.connect(DB_PATH)

    # Initialize pointer table if needed
    init_pointer_table(conn)

    # Check if session already exists for today
    existing_session = get_today_session(conn)

    if existing_session:
        print(f"Session already exists for today ({get_today()})")
        # Get the word details for existing session
        placeholders = ",".join("?" * len(existing_session))
        cur = conn.execute(
            f"SELECT id, word, meaning FROM words WHERE id IN ({placeholders})",
            existing_session
        )
        words = cur.fetchall()
        print_words(words)
        conn.close()
        return

    # Select new words for today
    words = select_words(conn, count=5)

    if not words:
        print("No words in database!")
        conn.close()
        return

    # Extract word IDs
    word_ids = [w[0] for w in words]

    # Save session
    save_session(conn, word_ids)

    # Initialize pointer
    init_pointer(conn)

    # Print the selected words
    print_words(words)

    conn.close()


if __name__ == "__main__":
    main()