#!/usr/bin/env python3
"""
Background daemon that schedules and triggers vocabulary popups throughout the day.
"""
import os
import sys
import json
import random
import subprocess
import atexit
from datetime import date, datetime, timedelta
from pathlib import Path

import sqlite3

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "vocab.db"
LOG_PATH = BASE_DIR / "data" / "scheduler.log"
SCRIPT_DIR = BASE_DIR / "scripts"


def get_today():
    return date.today().isoformat()


def log(msg):
    """Write timestamped log entry."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"
    with open(LOG_PATH, "a") as f:
        f.write(line)
    print(line.strip())


def ensure_today_session():
    """Run scheduler.py logic to create today's session if it doesn't exist."""
    # Import and run the scheduling logic directly
    conn = sqlite3.connect(DB_PATH)
    today = get_today()

    # Check if session exists
    cur = conn.execute("SELECT word_ids FROM sessions WHERE date = ?", (today,))
    row = cur.fetchone()
    if row:
        log("Today's session already exists")
        conn.close()
        return json.loads(row[0])

    conn.close()

    # Run scheduler.py as subprocess
    log("Running scheduler.py to create today's session")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "scheduler.py")],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        log("scheduler.py completed successfully")
    else:
        log(f"scheduler.py failed: {result.stderr}")
    return None


def get_scheduled_times(conn):
    """Get already scheduled events for today from the database."""
    today = get_today()
    cur = conn.execute(
        "SELECT event_type, scheduled_time FROM scheduled_events WHERE date = ?",
        (today,)
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def save_scheduled_time(conn, event_type, scheduled_time):
    """Save a scheduled event to the database."""
    today = get_today()
    conn.execute(
        "INSERT INTO scheduled_events (date, event_type, scheduled_time) VALUES (?, ?, ?)",
        (today, event_type, scheduled_time)
    )
    conn.commit()


def init_scheduled_events_table(conn):
    """Create scheduled_events table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_events (
            date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            launched INTEGER DEFAULT 0,
            PRIMARY KEY (date, event_type, scheduled_time)
        )
    """)
    conn.commit()


def generate_spread_times(count, min_interval_hours=1.5, start_hour=8, end_hour=22):
    """Generate 'count' random times between start_hour and end_hour, spaced at least min_interval_hours apart."""
    total_minutes = (end_hour - start_hour) * 60
    interval_minutes = min_interval_hours * 60

    # Calculate how many slots we need to ensure spacing
    # We need count times, each at least interval_minutes apart
    # Max times that fit = total_minutes / interval_minutes + 1
    # With 14 hours and 1.5 hour spacing: (14*60)/90 + 1 ≈ 10, so 5 is fine

    times = []
    remaining_slots = list(range(total_minutes))

    for _ in range(count):
        if not remaining_slots:
            break
        idx = random.randint(0, len(remaining_slots) - 1)
        slot = remaining_slots.pop(idx)
        times.append(slot)

    # Sort and adjust to ensure spacing (remove any that violate min interval)
    times.sort()
    adjusted = [times[0]]
    for t in times[1:]:
        if t - adjusted[-1] >= interval_minutes:
            adjusted.append(t)
        else:
            # Try to find a valid slot after adjusting
            new_slot = adjusted[-1] + int(interval_minutes)
            if new_slot < total_minutes and new_slot - adjusted[-1] >= interval_minutes:
                adjusted.append(new_slot)

    # Convert to datetime
    today_date = date.today()
    result = []
    for minutes in adjusted[:count]:
        hour = start_hour + minutes // 60
        minute = minutes % 60
        result.append(datetime(today_date.year, today_date.month, today_date.day, hour, minute))
    return result


def interleave_times(word_times, quiz_times):
    """Interleave word and quiz times so they don't clash."""
    combined = []
    for t in word_times:
        combined.append((t, 'word'))
    for t in quiz_times:
        combined.append((t, 'quiz'))
    combined.sort(key=lambda x: x[0])
    return combined


def schedule_today_events(conn):
    """Schedule today's popup events if not already scheduled."""
    today = get_today()

    # Check if we already have scheduled events
    cur = conn.execute(
        "SELECT COUNT(*) FROM scheduled_events WHERE date = ?",
        (today,)
    )
    count = cur.fetchone()[0]

    if count >= 10:
        log("Events already scheduled for today")
        return

    log("Scheduling today's popup events")

    # Generate times
    word_times = generate_spread_times(5, min_interval_hours=1.5, start_hour=8, end_hour=22)
    quiz_times = generate_spread_times(5, min_interval_hours=1.5, start_hour=8, end_hour=22)

    # Interleave
    scheduled = interleave_times(word_times, quiz_times)

    now = datetime.now()
    scheduled_count = 0

    for dt, event_type in scheduled:
        # Skip if time has passed
        if dt <= now:
            log(f"Skipping past time for {event_type}: {dt.strftime('%H:%M')}")
            continue

        save_scheduled_time(conn, event_type, dt.isoformat())
        scheduled_count += 1
        log(f"Scheduled {event_type} popup at {dt.strftime('%H:%M')}")

    log(f"Scheduled {scheduled_count} future events")


def get_pending_events(conn):
    """Get events that haven't been launched yet."""
    today = get_today()
    now = datetime.now()
    cur = conn.execute(
        "SELECT event_type, scheduled_time FROM scheduled_events WHERE date = ? AND launched = 0 ORDER BY scheduled_time",
        (today,)
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def mark_event_launched(conn, event_type, scheduled_time):
    """Mark an event as launched."""
    conn.execute(
        "UPDATE scheduled_events SET launched = 1 WHERE date = ? AND event_type = ? AND scheduled_time = ?",
        (get_today(), event_type, scheduled_time)
    )
    conn.commit()


def launch_popup(event_type):
    """Launch the appropriate popup script."""
    if event_type == 'word':
        script = SCRIPT_DIR / "new_word_popup.py"
    elif event_type == 'quiz':
        script = SCRIPT_DIR / "quiz_popup.py"
    else:
        return

    log(f"Launching {event_type} popup")
    try:
        subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        log(f"Failed to launch {event_type} popup: {e}")


def cleanup():
    """Cleanup function called on exit."""
    log("Scheduler shutting down")


def main():
    log("=== VocabLock Scheduler started ===")

    # Ensure today's session exists
    ensure_today_session()

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    init_scheduled_events_table(conn)

    # Schedule today's events
    schedule_today_events(conn)
    conn.close()

    # Main loop
    while True:
        conn = sqlite3.connect(DB_PATH)
        pending = get_pending_events(conn)
        now = datetime.now()

        for event_type, scheduled_str in pending:
            scheduled = datetime.fromisoformat(scheduled_str)
            if scheduled <= now:
                log(f"Triggering {event_type} popup (scheduled for {scheduled_str})")
                launch_popup(event_type)
                mark_event_launched(conn, event_type, scheduled_str)

        conn.close()
        time.sleep(60)


if __name__ == "__main__":
    import time
    atexit.register(cleanup)
    main()