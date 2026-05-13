import sqlite3
import re
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH  = BASE_DIR / "data" / "vocab.db"
MD_PATH  = BASE_DIR / "data" / "Crime_Punishment.md"

# ── database setup ────────────────────────────────────────────────────────────

def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS words (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            word        TEXT    NOT NULL UNIQUE,
            meaning     TEXT    NOT NULL,
            source      TEXT    DEFAULT 'Crime & Punishment',
            date_added  TEXT    DEFAULT (date('now'))
        );

        CREATE TABLE IF NOT EXISTS ai_cache (
            word_id     INTEGER PRIMARY KEY REFERENCES words(id),
            ipa         TEXT,
            hint        TEXT,
            sentence    TEXT,
            generated_on TEXT DEFAULT (date('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            date        TEXT PRIMARY KEY,
            word_ids    TEXT    -- JSON array e.g. [1,7,12,23,41]
        );

        CREATE TABLE IF NOT EXISTS progress (
            word_id         INTEGER PRIMARY KEY REFERENCES words(id),
            times_shown     INTEGER DEFAULT 0,
            times_confirmed INTEGER DEFAULT 0,
            quiz_correct    INTEGER DEFAULT 0,
            quiz_total      INTEGER DEFAULT 0,
            last_shown      TEXT,
            last_quizzed    TEXT
        );
    """)
    conn.commit()

# ── markdown parser ───────────────────────────────────────────────────────────

def parse_md(path: Path) -> list[tuple[str, str]]:
    """
    Reads your Obsidian markdown file.
    Returns a list of (word, meaning) tuples, skipping empty rows.
    """
    words = []
    text  = path.read_text(encoding="utf-8")

    for line in text.splitlines():
        # Match lines like: | word | meaning |
        # Ignore separator lines like: | --- | --- |
        match = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if not match:
            continue

        word    = match.group(1).strip()
        meaning = match.group(2).strip()

        # Skip separator rows and empty rows
        if re.match(r"^[-: ]+$", word) or word == "" or meaning == "":
            continue

        # Skip the header rows that are just dashes
        if set(word.replace("-","").replace(" ","")) == set():
            continue

        words.append((word.lower(), meaning))

    return words

# ── load words into db ────────────────────────────────────────────────────────

def load_words(conn, words: list[tuple[str, str]]):
    inserted = 0
    skipped  = 0

    for word, meaning in words:
        try:
            conn.execute(
                "INSERT INTO words (word, meaning) VALUES (?, ?)",
                (word, meaning)
            )
            # Create a blank progress row for every new word
            conn.execute(
                "INSERT INTO progress (word_id) "
                "SELECT id FROM words WHERE word = ?",
                (word,)
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1  # word already in db

    conn.commit()
    return inserted, skipped

# ── report ────────────────────────────────────────────────────────────────────

def print_report(conn):
    rows = conn.execute(
        "SELECT word, meaning FROM words ORDER BY word"
    ).fetchall()

    print(f"\n{'─'*55}")
    print(f"  {'WORD':<22} MEANING")
    print(f"{'─'*55}")
    for word, meaning in rows:
        # Truncate long meanings for display
        m = meaning if len(meaning) <= 30 else meaning[:27] + "..."
        print(f"  {word:<22} {m}")
    print(f"{'─'*55}")
    print(f"  Total words in database: {len(rows)}")
    print()

# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    conn  = sqlite3.connect(DB_PATH)
    init_db(conn)

    words             = parse_md(MD_PATH)
    inserted, skipped = load_words(conn, words)

    print(f"\n✓ Parsed '{MD_PATH.name}'")
    print(f"  {inserted} words inserted, {skipped} already existed")

    print_report(conn)
    conn.close()