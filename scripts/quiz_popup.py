#!/usr/bin/env python3
"""
Fullscreen GTK3 quiz popup for vocabulary revision.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import sqlite3
import random
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / 'data' / 'vocab.db'


def load_quiz_data():
    """Pick a word to quiz and generate options."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get a random confirmed word
    cursor.execute("""
        SELECT w.id, w.word, w.meaning
        FROM words w
        JOIN progress p ON w.id = p.word_id
        WHERE p.times_confirmed > 0
        ORDER BY RANDOM()
        LIMIT 1
    """)
    word_row = cursor.fetchone()

    if not word_row:
        conn.close()
        return None

    word_id = word_row['id']
    word = word_row['word']
    correct_meaning = word_row['meaning']

    # Get 3 wrong options
    cursor.execute("""
        SELECT meaning FROM words
        WHERE id != ?
        ORDER BY RANDOM()
        LIMIT 3
    """, (word_id,))
    wrong_meanings = [row['meaning'] for row in cursor.fetchall()]

    conn.close()

    # Build and shuffle options
    options = [{'meaning': correct_meaning, 'correct': True}]
    for wrong in wrong_meanings:
        options.append({'meaning': wrong, 'correct': False})

    random.shuffle(options)

    return {
        'word_id': word_id,
        'word': word,
        'options': options
    }


def update_progress(word_id, is_correct):
    """Update quiz progress in database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Increment quiz_total
    cursor.execute("""
        INSERT INTO progress (word_id, quiz_total, last_quizzed)
        VALUES (?, 1, date('now'))
        ON CONFLICT(word_id) DO UPDATE SET
            quiz_total = quiz_total + 1,
            last_quizzed = date('now')
    """, (word_id,))

    # Increment quiz_correct if correct
    if is_correct:
        cursor.execute("""
            INSERT INTO progress (word_id, quiz_correct)
            VALUES (?, 1)
            ON CONFLICT(word_id) DO UPDATE SET
                quiz_correct = quiz_correct + 1
        """, (word_id,))

    conn.commit()
    conn.close()


class QuizWindow(Gtk.Window):
    def __init__(self):
        super().__init__(
            type=Gtk.WindowType.TOPLEVEL,
            title="VocabLock Quiz"
        )

        self.quiz_data = None
        self.option_buttons = []
        self.correct_button = None
        self.feedback_label = None

        self.set_keep_above(True)
        self.fullscreen()
        self.set_decorated(False)

        # Background color
        self.modify_bg(Gtk.StateType.NORMAL, Gdk.Color.parse('#0a0a0a')[1])

        self.build_ui()
        self.setup_css()
        self.show_all()
        GLib.idle_add(self.load_data)

    def setup_css(self):
        """Apply global CSS to the screen."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            window {
                background-color: #0a0a0a;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def build_ui(self):
        """Build the quiz UI."""
        # Main vertical box, centered
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
        main_box.set_halign(Gtk.Align.CENTER)
        main_box.set_valign(Gtk.Align.CENTER)
        self.add(main_box)

        # Content width constrained to 600px
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=25)
        content_box.set_size_request(600, -1)
        main_box.pack_start(content_box, True, True, 0)

        # Widget 1: Top label 'Quick Revision'
        title_label = Gtk.Label(label="Quick Revision")
        title_label.set_alignment(0.5, 0.5)
        title_label.set_name("title")
        content_box.pack_start(title_label, False, False, 0)

        # Widget 2: Question label
        question_label = Gtk.Label(label="What does this word mean?")
        question_label.set_alignment(0.5, 0.5)
        question_label.set_name("question")
        content_box.pack_start(question_label, False, False, 0)

        # Widget 3: Word label
        self.word_label = Gtk.Label(label="Loading...")
        self.word_label.set_alignment(0.5, 0.5)
        self.word_label.set_name("word")
        self.word_label.set_margin_bottom(20)
        content_box.pack_start(self.word_label, False, False, 0)

        # Widget 4: Options box
        self.options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.options_box.set_halign(Gtk.Align.CENTER)
        content_box.pack_start(self.options_box, False, False, 0)

        # Widget 5: Feedback label (hidden initially)
        self.feedback_label = Gtk.Label(label="")
        self.feedback_label.set_alignment(0.5, 0.5)
        self.feedback_label.set_visible(False)
        self.feedback_label.set_name("feedback")
        content_box.pack_start(self.feedback_label, False, False, 0)

        # Apply label styles via CSS
        self.apply_label_css()

    def apply_label_css(self):
        """Apply CSS to all labels."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            #title {
                font-size: 14px;
                color: #888888;
            }
            #question {
                font-size: 18px;
                color: #cccccc;
            }
            #word {
                font-size: 54px;
                font-weight: bold;
                color: #ffffff;
            }
            #feedback {
                font-size: 18px;
            }
            button {
                font-size: 16px;
                color: #ffffff;
                background-color: #2a2a2a;
                background-image: none;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 10px 20px;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def load_data(self):
        """Load quiz data."""
        self.quiz_data = load_quiz_data()

        if not self.quiz_data:
            self.show_no_words_message()
            return False

        self.word_label.set_label(self.quiz_data['word'])

        # Create 4 option buttons
        for opt in self.quiz_data['options']:
            btn = Gtk.Button(label=opt['meaning'])
            btn.set_size_request(560, 60)
            btn.set_halign(Gtk.Align.CENTER)
            btn.connect("clicked", self.on_option_clicked, opt['meaning'], opt['correct'])
            self.options_box.pack_start(btn, False, False, 0)
            self.option_buttons.append(btn)
            if opt['correct']:
                self.correct_button = btn

        self.show_all()
        return False

    def show_no_words_message(self):
        """Show message when no confirmed words exist."""
        # Clear the main content
        for child in self.options_box.get_parent().get_children():
            if child != self.options_box:
                child.hide()

        self.options_box.hide()

        content = self.options_box.get_parent()

        msg1 = Gtk.Label(label="No words to revise yet")
        msg1.set_alignment(0.5, 0.5)
        msg1.set_name("no-words-title")

        msg2 = Gtk.Label(label="Confirm some new words first using the word popups!")
        msg2.set_alignment(0.5, 0.5)
        msg2.set_name("no-words-sub")

        close_btn = Gtk.Button(label="Close")
        close_btn.set_size_request(560, 60)
        close_btn.set_halign(Gtk.Align.CENTER)
        close_btn.connect("clicked", lambda b: self.close_window())

        content.pack_start(msg1, False, False, 0)
        content.pack_start(msg2, False, False, 10)
        content.pack_start(close_btn, False, False, 20)

        # CSS for no words screen
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            #no-words-title {
                font-size: 28px;
                font-weight: bold;
                color: #ffffff;
            }
            #no-words-sub {
                font-size: 16px;
                color: #888888;
            }
            button {
                font-size: 16px;
                color: #ffffff;
                background-color: #2a2a2a;
                background-image: none;
                border: 1px solid #555555;
                border-radius: 8px;
                padding: 10px 20px;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.show_all()
        return False

    def apply_button_color(self, button, bg, border):
        """Apply button color via per-button CSS provider."""
        provider = Gtk.CssProvider()
        css = f'''
            button {{
                background-color: {bg};
                background-image: none;
                border-color: {border};
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
            }}
        '''
        provider.load_from_data(css.encode())
        button.get_style_context().add_provider(
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER
        )

    def on_option_clicked(self, button, meaning, is_correct):
        """Handle option click."""
        # Step 1: disable ALL 4 buttons immediately
        for btn in self.option_buttons:
            btn.set_sensitive(False)

        # Step 2: color the clicked button
        if is_correct:
            self.apply_button_color(button, '#1e7e1e', '#28a428')
            self.feedback_label.set_markup('<span foreground="#4cff4c" font="18" weight="bold">✓ Correct!</span>')
        else:
            self.apply_button_color(button, '#7e1e1e', '#a42828')
            # Also highlight the correct button green
            self.apply_button_color(self.correct_button, '#1e7e1e', '#28a428')
            self.feedback_label.set_markup('<span foreground="#ff6b6b" font="18">✗ Wrong — the correct answer is highlighted in green</span>')

        # Step 3: show feedback label
        self.feedback_label.set_visible(True)

        # Step 4: update progress in DB
        update_progress(self.quiz_data['word_id'], is_correct)

        # Step 5: close window after 2500ms
        GLib.timeout_add(2500, self.close_window)

    def close_window(self):
        self.destroy()
        Gtk.main_quit()
        return False


def main():
    win = QuizWindow()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()