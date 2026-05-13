#!/usr/bin/env python3
"""Generates AI data (IPA, hint, sentence) for words missing from ai_cache."""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "vocab.db"

# Load .env
load_dotenv(BASE_DIR / ".env")
API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    print("Error: GROQ_API_KEY not found in .env")
    sys.exit(1)


def get_words_without_cache():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        SELECT w.id, w.word, w.meaning
        FROM words w
        LEFT JOIN ai_cache c ON w.id = c.word_id
        WHERE c.word_id IS NULL
        ORDER BY w.id
    """)
    result = cur.fetchall()
    conn.close()
    return result


def call_groq(word: str, meaning: str) -> dict | None:
    url = "https://api.groq.com/openai/v1/chat/completions"

    prompt = f"""Given the word "{word}" with meaning "{meaning}", provide a JSON object with exactly these keys:
- ipa: International Phonetic Alphabet pronunciation
- hint: Syllable-by-syllable pronunciation guide in plain English (e.g., "pur-spi-KAY-shus")
- sentence: A short example sentence using the word

Return ONLY valid JSON, no other text."""

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 200
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        text = data["choices"][0]["message"]["content"]
        # Try to extract JSON from response
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        return json.loads(text)
    except Exception as e:
        print(f"  Error for '{word}': {e}")
        return None


def store_in_cache(word_id: int, ipa: str, hint: str, sentence: str):
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO ai_cache (word_id, ipa, hint, sentence) VALUES (?, ?, ?, ?)",
        (word_id, ipa, hint, sentence)
    )
    conn.commit()
    conn.close()


def main():
    words = get_words_without_cache()
    total = len(words)

    if total == 0:
        print("All words already have AI cache entries.")
        return

    print(f"Found {total} words without AI cache.")
    print(f"Fetching data from Groq API (llama-3.1-8b-instant)...\n")

    for i, (word_id, word, meaning) in enumerate(words, 1):
        print(f"[{i}/{total}] Processing: {word}", end=" ... ", flush=True)

        result = call_groq(word, meaning)

        if result:
            ipa = result.get("ipa", "")
            hint = result.get("hint", "")
            sentence = result.get("sentence", "")
            store_in_cache(word_id, ipa, hint, sentence)
            print("done")
        else:
            print("failed")

        if i < total:
            time.sleep(1)

    print(f"\n✓ Completed {total} words")


if __name__ == "__main__":
    main()