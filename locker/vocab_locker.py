#!/usr/bin/env python3
"""Fullscreen GTK3 lock screen that displays vocabulary words."""

import json
import os
from datetime import date

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "vocab.db"


def get_today():
    return date.today().isoformat()


def get_today_word():
    """Get the current word for today based on session and pointer."""
    conn = sqlite3.connect(DB_PATH)
    today = get_today()

    # Get session word IDs
    cur = conn.execute("SELECT word_ids FROM sessions WHERE date = ?", (today,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    word_ids = json.loads(row[0])

    # Get current pointer
    cur = conn.execute("SELECT pointer FROM current_pointer WHERE date = ?", (today,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    pointer = row[0]

    # Get current word ID
    current_word_id = word_ids[pointer % len(word_ids)]

    # Get word data
    cur = conn.execute("SELECT word, meaning FROM words WHERE id = ?", (current_word_id,))
    word_row = cur.fetchone()
    if not word_row:
        conn.close()
        return None

    word, meaning = word_row

    # Get AI cache data
    cur = conn.execute("SELECT ipa, hint, sentence FROM ai_cache WHERE word_id = ?", (current_word_id,))
    cache_row = cur.fetchone()
    ipa = cache_row[0] if cache_row else ""
    hint = cache_row[1] if cache_row else ""
    sentence = cache_row[2] if cache_row else ""

    conn.close()

    return {
        "word_id": current_word_id,
        "word": word,
        "meaning": meaning,
        "ipa": ipa,
        "hint": hint,
        "sentence": sentence,
        "pointer": pointer,
        "word_ids": word_ids
    }


def update_progress(word_id, known):
    """Update progress table after unlock attempt."""
    conn = sqlite3.connect(DB_PATH)
    today = get_today()

    if known:
        conn.execute("""
            UPDATE progress
            SET times_shown = times_shown + 1,
                times_confirmed = times_confirmed + 1,
                last_shown = ?
            WHERE word_id = ?
        """, (today, word_id))
    else:
        conn.execute("""
            UPDATE progress
            SET times_shown = times_shown + 1,
                last_shown = ?
            WHERE word_id = ?
        """, (today, word_id))

    conn.commit()
    conn.close()


def advance_pointer():
    """Advance the pointer for today."""
    conn = sqlite3.connect(DB_PATH)
    today = get_today()

    conn.execute("""
        UPDATE current_pointer
        SET pointer = pointer + 1
        WHERE date = ?
    """, (today,))

    conn.commit()
    conn.close()


def authenticate(password):
    """Authenticate using PAM with fallback services."""
    import pam
    import pwd

    username = pwd.getpwuid(os.getuid()).pw_name
    p = pam.pam()

    # Try services in sequence
    services = ['login', 'system-auth', 'passwd']
    for service in services:
        if p.authenticate(username, password, service=service):
            return True

    return False


class VocabLocker(Gtk.Window):
    def __init__(self):
        super().__init__()

        self.word_data = get_today_word()
        if not self.word_data:
            print("No session found for today. Run scheduler.py first.")
            Gtk.main_quit()
            return

        self.setup_css()
        self.setup_window()
        self.create_ui()

    def setup_css(self):
        """Set up CSS provider for styling."""
        css = """
            window {
                background-color: #000000;
            }
            .white-text {
                color: #ffffff;
            }
            .grey-text {
                color: #666666;
            }
            .light-text {
                color: #dddddd;
            }
            .dim-text {
                color: #888888;
            }
            .error-text {
                color: #ff3333;
            }
        """
        self.css_provider = Gtk.CssProvider()
        self.css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def setup_window(self):
        self.set_title("VocabLock")
        self.set_default_size(1920, 1080)
        self.fullscreen()
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)

    def create_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        vbox.set_halign(Gtk.Align.CENTER)
        vbox.set_valign(Gtk.Align.CENTER)
        vbox.set_margin_top(100)
        vbox.set_margin_bottom(100)

        # Word
        word_label = Gtk.Label(label=self.word_data["word"])
        word_label.set_name("word")
        word_label.get_style_context().add_class("white-text")
        word_label.set_markup(f"<span size='48000' weight='bold'>{self.word_data['word']}</span>")

        # IPA and hint
        ipa_hint = f"{self.word_data['ipa']}  ·  {self.word_data['hint']}"
        ipa_label = Gtk.Label(label=ipa_hint)
        ipa_label.get_style_context().add_class("grey-text")
        ipa_label.set_markup(f"<span size='18000'>{ipa_hint}</span>")

        # Meaning
        meaning_label = Gtk.Label(label=self.word_data["meaning"])
        meaning_label.get_style_context().add_class("light-text")
        meaning_label.set_markup(f"<span size='20000'>{self.word_data['meaning']}</span>")
        meaning_label.set_max_width_chars(60)
        meaning_label.set_line_wrap(True)
        meaning_label.set_justify(Gtk.Justification.CENTER)

        # Sentence
        sentence_label = Gtk.Label(label=self.word_data["sentence"])
        sentence_label.get_style_context().add_class("dim-text")
        sentence_label.set_markup(f"<i><span size='16000'>{self.word_data['sentence']}</span></i>")
        sentence_label.set_max_width_chars(60)
        sentence_label.set_line_wrap(True)
        sentence_label.set_justify(Gtk.Justification.CENTER)

        # Checkbox
        self.checkbox = Gtk.CheckButton(label="I know this word")
        self.checkbox.set_halign(Gtk.Align.CENTER)
        self.checkbox.get_style_context().add_class("grey-text")

        # Password entry
        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.set_placeholder_text("Password")
        self.password_entry.set_width_chars(30)
        self.password_entry.set_halign(Gtk.Align.CENTER)

        # Unlock button
        unlock_btn = Gtk.Button(label="Unlock")
        unlock_btn.set_size_request(200, 50)
        unlock_btn.connect("clicked", self.on_unlock)

        # Error label
        self.error_label = Gtk.Label(label="")
        self.error_label.get_style_context().add_class("error-text")

        vbox.pack_start(word_label, False, False, 20)
        vbox.pack_start(ipa_label, False, False, 10)
        vbox.pack_start(meaning_label, False, False, 20)
        vbox.pack_start(sentence_label, False, False, 20)
        vbox.pack_start(self.checkbox, False, False, 30)
        vbox.pack_start(self.password_entry, False, False, 10)
        vbox.pack_start(unlock_btn, False, False, 10)
        vbox.pack_start(self.error_label, False, False, 10)

        self.add(vbox)

    def on_unlock(self, widget):
        known = self.checkbox.get_active()
        password = self.password_entry.get_text()

        # Update progress
        update_progress(self.word_data["word_id"], known)

        # Advance pointer
        advance_pointer()

        # Authenticate
        if authenticate(password):
            self.destroy()
            Gtk.main_quit()
        else:
            self.error_label.set_label("Wrong password")
            self.password_entry.set_text("")
            self.password_entry.grab_focus()


def focus_window(win):
    win.present()
    win.grab_focus()
    return False


def on_key_press(widget, event):
    # REMOVE THIS IN PRODUCTION
    if event.keyval == Gdk.KEY_Escape:
        widget.destroy()
        Gtk.main_quit()
        return True
    return False


def main():
    win = VocabLocker()
    win.connect("destroy", Gtk.main_quit)
    win.connect("key-press-event", on_key_press)

    win.show_all()
    GLib.idle_add(focus_window, win)
    Gtk.main()


if __name__ == "__main__":
    main()