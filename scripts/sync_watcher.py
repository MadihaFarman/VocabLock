#!/usr/bin/env python3
"""Watches data/Crime_Punishment.md and auto-runs parser logic when saved."""

import sqlite3
import re
import sys
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "vocab.db"
MD_PATH = BASE_DIR / "data" / "Crime_Punishment.md"


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
            word_ids    TEXT
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


def parse_md(path: Path):
    words = []
    text = path.read_text(encoding="utf-8")

    for line in text.splitlines():
        match = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if not match:
            continue

        word = match.group(1).strip()
        meaning = match.group(2).strip()

        if re.match(r"^[-: ]+$", word) or word == "" or meaning == "":
            continue

        if set(word.replace("-", "").replace(" ", "")) == set():
            continue

        words.append((word.lower(), meaning))

    return words


def load_words(conn, words):
    inserted = 0
    skipped = 0

    for word, meaning in words:
        try:
            conn.execute(
                "INSERT INTO words (word, meaning) VALUES (?, ?)",
                (word, meaning)
            )
            conn.execute(
                "INSERT INTO progress (word_id) "
                "SELECT id FROM words WHERE word = ?",
                (word,)
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    return inserted, skipped


def run_parser():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    words = parse_md(MD_PATH)
    inserted, skipped = load_words(conn, words)

    conn.close()

    return inserted, skipped


class MarkdownChangeHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.processing = False

    def on_modified(self, event):
        if event.is_directory:
            return

        event_path = Path(event.src_path).resolve()
        if event_path == MD_PATH.resolve():
            self.trigger_parse()

    def on_created(self, event):
        if event.is_directory:
            return

        event_path = Path(event.src_path).resolve()
        if event_path == MD_PATH.resolve():
            self.trigger_parse()

    def trigger_parse(self):
        if self.processing:
            return
        self.processing = True

        print(f"[sync_watcher] Detected change in {MD_PATH.name}", flush=True)

        try:
            inserted, skipped = run_parser()
            print(f"[sync_watcher] {inserted} new words added, {skipped} already existed", flush=True)
        except Exception as e:
            print(f"[sync_watcher] Error: {e}", flush=True)
        finally:
            self.processing = False


def main():
    if not MD_PATH.exists():
        print(f"[sync_watcher] Warning: {MD_PATH} does not exist yet")

    print(f"[sync_watcher] Watching {MD_PATH} for changes...", flush=True)

    event_handler = MarkdownChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, str(MD_PATH.parent), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[sync_watcher] Stopping...", flush=True)
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()