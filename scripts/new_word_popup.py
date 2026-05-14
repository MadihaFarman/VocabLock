#!/usr/bin/env python3
"""
Fullscreen GTK3 popup showing today's vocabulary word.
Blocks until user confirms, then updates database and exits.
"""
import sqlite3
import json
import sys
from datetime import date

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib


DB_PATH = "/home/madiha/vocablock/data/vocab.db"


def get_today():
    return date.today().isoformat()


def load_word_data():
    """Load today's session, pointer, and current word data."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    today = get_today()

    # Get today's session
    cursor.execute("SELECT word_ids FROM sessions WHERE date = ?", (today,))
    row = cursor.fetchone()
    if not row or not row['word_ids']:
        conn.close()
        return None

    word_ids = json.loads(row['word_ids'])
    total_words = len(word_ids)

    # Get current pointer
    cursor.execute("SELECT pointer FROM current_pointer WHERE date = ?", (today,))
    ptr_row = cursor.fetchone()
    pointer = ptr_row['pointer'] if ptr_row else 0

    # Get current word id
    current_word_id = word_ids[pointer % total_words]

    # Get word data
    cursor.execute("""
        SELECT w.word, w.meaning, a.ipa, a.hint, a.sentence
        FROM words w
        LEFT JOIN ai_cache a ON w.id = a.word_id
        WHERE w.id = ?
    """, (current_word_id,))
    word_row = cursor.fetchone()

    conn.close()

    if not word_row:
        return None

    return {
        'word': word_row['word'],
        'meaning': word_row['meaning'],
        'ipa': word_row['ipa'] or '',
        'hint': word_row['hint'] or '',
        'sentence': word_row['sentence'] or '',
        'word_id': current_word_id,
        'current': pointer + 1,
        'total': total_words
    }


def update_progress(word_id):
    """Update progress table after confirmation."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = get_today()

    # Increment times_shown and set last_shown
    cursor.execute("""
        INSERT INTO progress (word_id, times_shown, last_shown)
        VALUES (?, 1, ?)
        ON CONFLICT(word_id) DO UPDATE SET
            times_shown = times_shown + 1,
            last_shown = excluded.last_shown
    """, (word_id, today))

    # Increment times_confirmed
    cursor.execute("""
        INSERT INTO progress (word_id, times_confirmed)
        VALUES (?, 1)
        ON CONFLICT(word_id) DO UPDATE SET
            times_confirmed = times_confirmed + 1
    """, (word_id,))

    # Increment pointer
    cursor.execute("""
        INSERT INTO current_pointer (date, pointer)
        VALUES (?, 1)
        ON CONFLICT(date) DO UPDATE SET
            pointer = pointer + 1
    """, (today,))

    conn.commit()
    conn.close()


class WordPopup(Gtk.Window):
    def __init__(self):
        super().__init__(
            type=Gtk.WindowType.TOPLEVEL,
            title="VocabLock"
        )

        self.word_data = None

        # Fullscreen, no decoration, keep above
        self.set_keep_above(True)
        self.fullscreen()
        self.set_decorated(False)

        # Black background
        self.set_background_color("#000000")

        # Build UI
        self.build_ui()

        # Show loading, then load data
        self.show_all()
        GLib.idle_add(self.load_data)

    def set_background_color(self, color):
        """Set window background via CSS."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(f"""
            window {{
                background-color: {color};
            }}
        """)
        self.get_style_context().add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def build_ui(self):
        """Build the popup UI."""
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_box.set_halign(Gtk.Align.CENTER)
        main_box.set_valign(Gtk.Align.CENTER)
        main_box.set_hexpand(True)
        main_box.set_vexpand(True)
        self.add(main_box)

        # Main content area
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_halign(Gtk.Align.CENTER)
        content_box.set_valign(Gtk.Align.CENTER)
        content_box.set_margin_top(60)

        # The word
        self.word_label = Gtk.Label(label="Loading...")
        self.word_label.set_name("word")
        content_box.pack_start(self.word_label, False, False, 0)

        # IPA and hint
        self.ipa_hint_label = Gtk.Label(label="")
        self.ipa_hint_label.set_name("ipa_hint")
        content_box.pack_start(self.ipa_hint_label, False, False, 0)

        # Meaning
        self.meaning_label = Gtk.Label(label="")
        self.meaning_label.set_name("meaning")
        content_box.pack_start(self.meaning_label, False, False, 0)

        # Example sentence
        self.sentence_label = Gtk.Label(label="")
        self.sentence_label.set_name("sentence")
        content_box.pack_start(self.sentence_label, False, False, 0)

        # Divider
        self.divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.divider.set_name("divider")
        content_box.pack_start(self.divider, False, False, 15)

        # Checkbox
        self.checkbox = Gtk.CheckButton(label="I have learned this word")
        self.checkbox.set_name("checkbox")
        self.checkbox.connect("toggled", self.on_checkbox_toggled)
        content_box.pack_start(self.checkbox, False, False, 10)

        # Got it button
        self.gotit_btn = Gtk.Button(label="Got it")
        self.gotit_btn.set_name("gotit")
        self.gotit_btn.set_sensitive(False)
        self.gotit_btn.connect("clicked", self.on_gotit_clicked)
        content_box.pack_start(self.gotit_btn, False, False, 0)

        main_box.pack_start(content_box, True, True, 0)

        # Apply CSS styling
        self.apply_css()

    def apply_css(self):
        """Apply CSS styling to all widgets."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data("""
            window {
                background-color: #000000;
            }
            #word {
                font: bold 52px sans-serif;
                color: #ffffff;
            }
            #ipa_hint {
                font: 18px sans-serif;
                color: #888888;
            }
            #meaning {
                font: 22px sans-serif;
                color: #66b3ff;
            }
            #sentence {
                font: italic 16px sans-serif;
                color: #ffffff;
            }
            #divider {
                background-color: #333333;
                min-height: 1px;
                color: #333333;
            }
            #checkbox {
                font: 16px sans-serif;
                color: #cccccc;
            }
            #gotit {
                font: bold 18px sans-serif;
                color: #000000;
                background-color: #333333;
                padding: 12px 40px;
                border-radius: 6px;
                border: none;
                box-shadow: none;
            }
            #gotit:hover {
                background-color: #444444;
            }
        """)
        style_ctx = self.get_style_context()
        style_ctx.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        for widget in [self.word_label, self.ipa_hint_label, self.meaning_label,
                      self.sentence_label, self.checkbox, self.gotit_btn]:
            ctx = widget.get_style_context()
            ctx.add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def load_data(self):
        """Load word data and populate UI."""
        self.word_data = load_word_data()

        if not self.word_data:
            self.word_label.set_label("No words available")
            return False

        # Update UI
        self.word_label.set_label(self.word_data['word'])

        ipa_hint = ""
        if self.word_data['ipa']:
            ipa_hint = f"[{self.word_data['ipa']}]"
        if self.word_data['hint']:
            ipa_hint += f"  {self.word_data['hint']}"
        self.ipa_hint_label.set_label(ipa_hint)

        self.meaning_label.set_label(self.word_data['meaning'])
        self.sentence_label.set_label(self.word_data['sentence'])

        return False

    def on_checkbox_toggled(self, checkbox):
        """Enable Got it button when checkbox is ticked."""
        self.gotit_btn.set_sensitive(checkbox.get_active())

    def on_gotit_clicked(self, button):
        """Save progress and exit."""
        if self.word_data:
            update_progress(self.word_data['word_id'])
        Gtk.main_quit()


def main():
    win = WordPopup()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()