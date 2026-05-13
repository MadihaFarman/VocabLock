#!/usr/bin/env python3
"""Watches data/Crime_Punishment.md for changes and re-runs parser.py."""

import sys
import time
import subprocess
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


BASE_DIR = Path(__file__).parent.parent
TARGET_FILE = BASE_DIR / "data" / "Crime_Punishment.md"
PARSER_SCRIPT = BASE_DIR / "scripts" / "parser.py"


class MarkdownChangeHandler(FileSystemEventHandler):
    """Handler that triggers parser.py when the target markdown file is modified."""

    def __init__(self):
        super().__init__()
        self.processing = False

    def on_modified(self, event):
        if event.is_directory:
            return

        event_path = Path(event.src_path).resolve()
        if event_path == TARGET_FILE.resolve():
            self.run_parser()

    def on_modified(self, event):
        if event.is_directory:
            return

        event_path = Path(event.src_path).resolve()
        if event_path == TARGET_FILE.resolve():
            self.run_parser()

    def run_parser(self):
        if self.processing:
            return
        self.processing = True
        print(f"[watcher] Detected change in {TARGET_FILE.name}, running parser...")
        try:
            subprocess.run([sys.executable, str(PARSER_SCRIPT)], check=True)
            print("[watcher] Parser completed successfully")
        except subprocess.CalledProcessError as e:
            print(f"[watcher] Parser failed with exit code {e.returncode}")
        finally:
            self.processing = False


def main():
    target_dir = TARGET_FILE.parent

    if not TARGET_FILE.exists():
        print(f"[watcher] Warning: {TARGET_FILE} does not exist yet")

    print(f"[watcher] Watching {TARGET_FILE} for changes...")
    print(f"[watcher] Press Ctrl+C to stop")

    event_handler = MarkdownChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, str(target_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[watcher] Stopping watcher...")
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()