import sys
import threading
import random
import csv
import io
from datetime import datetime
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio
from scraper import get_comments_scraper_gen

class YouTubeCommentExtractorApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.github.antux912012.YTCommentExtractor',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect('activate', self.on_activate)
        self.extracted_comments = []

    def on_activate(self, app):
        self.win = Adw.ApplicationWindow(application=app, title="YouTube Comment Extractor")
        self.win.set_default_size(800, 600)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.win.set_content(main_box)

        # Header Bar
        header = Adw.HeaderBar()
        main_box.append(header)

        # Content Box
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)
        main_box.append(content)

        # Preferences Group for Inputs
        input_group = Adw.PreferencesGroup(title="Extraction Settings")
        content.append(input_group)

        # URL Input
        self.url_entry = Adw.EntryRow(title="Video URL")
        input_group.add(self.url_entry)

        # Sort Mode
        self.sort_combo = Adw.ComboRow(title="Sort Mode")
        self.sort_model = Gtk.StringList.new(["popular", "recent"])
        self.sort_combo.set_model(self.sort_model)
        input_group.add(self.sort_combo)

        # Selection Mode
        self.selection_combo = Adw.ComboRow(title="Selection Mode")
        self.selection_model = Gtk.StringList.new(["random", "ordered"])
        self.selection_combo.set_model(self.selection_model)
        input_group.add(self.selection_combo)

        # Number of Comments
        self.num_entry = Adw.EntryRow(title="Number of Comments")
        self.num_entry.set_text("100")
        input_group.add(self.num_entry)

        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        content.append(button_box)

        self.extract_btn = Gtk.Button(label="Extract Comments")
        self.extract_btn.add_css_class("suggested-action")
        self.extract_btn.connect("clicked", self.on_extract_clicked)
        button_box.append(self.extract_btn)

        self.download_btn = Gtk.Button(label="Download CSV")
        self.download_btn.set_sensitive(False)
        self.download_btn.connect("clicked", self.on_download_clicked)
        button_box.append(self.download_btn)

        # Terminal / Log Output
        log_frame = Gtk.Frame()
        log_frame.set_vexpand(True)
        content.append(log_frame)

        scrolled = Gtk.ScrolledWindow()
        log_frame.set_child(scrolled)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        self.log_view.add_css_class("card")
        scrolled.set_child(self.log_view)

        self.win.present()

    def append_log(self, text):
        buf = self.log_view.get_buffer()
        iter_end = buf.get_end_iter()
        buf.insert(iter_end, text + "\n")
        # Scroll to bottom
        mark = buf.create_mark(None, buf.get_end_iter(), False)
        self.log_view.scroll_to_mark(mark, 0.0, False, 0.0, 0.0)

    def on_extract_clicked(self, button):
        url = self.url_entry.get_text()
        if not url:
            self.append_log("[ERROR] Please enter a URL.")
            return

        self.extract_btn.set_sensitive(False)
        self.download_btn.set_sensitive(False)
        self.log_view.get_buffer().set_text("")
        self.extracted_comments = []

        sort_mode = self.sort_model.get_string(self.sort_combo.get_selected())
        selection_mode = self.selection_model.get_string(self.selection_combo.get_selected())
        num_str = self.num_entry.get_text()
        
        try:
            num_comments = None if num_str.lower() == 'all' else max(1, min(int(num_str), 10000))
        except ValueError:
            num_comments = 100
        
        pool_size = 5000 if selection_mode == 'random' else num_comments

        threading.Thread(target=self.extraction_thread, args=(url, sort_mode, selection_mode, num_comments, pool_size), daemon=True).start()

    def extraction_thread(self, url, sort_mode, selection_mode, num_comments, pool_size):
        GLib.idle_add(self.append_log, f"[SYSTEM] Booting extraction task for URL: {url}")
        
        all_comments = []
        for chunk in get_comments_scraper_gen(url, max_comments=pool_size, sort_mode=sort_mode):
            if 'log' in chunk:
                GLib.idle_add(self.append_log, chunk['log'])
            if 'error' in chunk:
                GLib.idle_add(self.append_log, f"[ERROR] {chunk['error']}")
                GLib.idle_add(self.finish_extraction, False)
                return
            if 'result' in chunk:
                all_comments = chunk['result']
        
        if not all_comments:
            GLib.idle_add(self.append_log, "[ERROR] No comments found.")
            GLib.idle_add(self.finish_extraction, False)
            return

        GLib.idle_add(self.append_log, "[SYSTEM] Filtering and sanitizing dataset...")

        if selection_mode == 'ordered':
            selected = all_comments[:num_comments] if num_comments else all_comments
        else:
            if num_comments and len(all_comments) > num_comments:
                selected = random.sample(all_comments, num_comments)
                GLib.idle_add(self.append_log, f"[INFO] Sampled {num_comments} true random comments.")
            else:
                random.shuffle(all_comments)
                selected = all_comments

        self.extracted_comments = selected
        GLib.idle_add(self.append_log, "[SUCCESS] Extraction Pipeline Complete.")
        GLib.idle_add(self.finish_extraction, True)

    def finish_extraction(self, success):
        self.extract_btn.set_sensitive(True)
        if success:
            self.download_btn.set_sensitive(True)

    def on_download_clicked(self, button):
        if not self.extracted_comments: return
        
        dialog = Gtk.FileChooserNative(title="Save CSV", action=Gtk.FileChooserAction.SAVE)
        dialog.set_current_name(f"yt_comments_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv")
        dialog.connect("response", self.on_file_chooser_response)
        dialog.show()

    def on_file_chooser_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            path = file.get_path()
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter='|', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow(['Nickname', 'Date', 'Comment'])
                for c in self.extracted_comments:
                    writer.writerow([c.get('nickname', ''), c.get('date', ''), c.get('comment', '')])
            self.append_log(f"[INFO] Saved {len(self.extracted_comments)} comments to {path}")

app = YouTubeCommentExtractorApp()
app.run(sys.argv)
