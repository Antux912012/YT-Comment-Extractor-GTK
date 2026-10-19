import sys
import os
import json
import threading
import random
import csv
from pathlib import Path
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Gdk

from scraper import get_comments_scraper_gen, extract_video_id

CONFIG_DIR = Path.home() / '.config' / 'yt-comment-extractor'
CONFIG_FILE = CONFIG_DIR / 'settings.json'


def load_settings():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(data):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


class YouTubeCommentExtractorApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id='io.github.antux912012.YTCommentExtractor',
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )
        self.connect('activate', self.on_activate)

        self.extracted_comments = []
        self.extraction_thread = None
        self.stop_event = threading.Event()
        self.cookies_path = None
        self.settings = load_settings()

    def on_activate(self, app):
        self.win = Adw.ApplicationWindow(application=app, title="YouTube Comment Extractor v0.4")
        self.win.set_default_size(840, 720)

        # Main Toast Overlay for GNOME-style notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.win.set_content(self.toast_overlay)

        # Root box
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(root_box)

        # Header Bar
        header = Adw.HeaderBar()
        root_box.append(header)

        # Scrolled Window wrapping the clamped content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        root_box.append(scrolled)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_margin_top(18)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(16)
        clamp.set_margin_end(16)
        scrolled.set_child(clamp)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(content_box)

        # -------------------------------------------------------------
        # Group 1: Target Video
        # -------------------------------------------------------------
        video_group = Adw.PreferencesGroup(title="Target Video")
        content_box.append(video_group)

        self.url_entry = Adw.EntryRow(title="Video URL or ID")
        self.url_entry.set_show_apply_button(False)

        # Paste Button Suffix
        paste_btn = Gtk.Button(icon_name="edit-paste-symbolic")
        paste_btn.set_valign(Gtk.Align.CENTER)
        paste_btn.set_tooltip_text("Paste from Clipboard")
        paste_btn.add_css_class("flat")
        paste_btn.connect("clicked", self.on_paste_clicked)
        self.url_entry.add_suffix(paste_btn)

        video_group.add(self.url_entry)

        # -------------------------------------------------------------
        # Group 2: Extraction & Sampling Configuration
        # -------------------------------------------------------------
        settings_group = Adw.PreferencesGroup(
            title="Extraction &amp; Sampling Strategy",
            description="Control comment ordering and prevent algorithmic bias using yt-dlp."
        )
        content_box.append(settings_group)

        # Sort Mode
        self.sort_combo = Adw.ComboRow(title="Order on YouTube")
        self.sort_combo.set_subtitle("Sort order used when retrieving comments via yt-dlp")
        self.sort_model = Gtk.StringList.new(["Top Comments / Relevant", "Newest First"])
        self.sort_combo.set_model(self.sort_model)
        self.sort_combo.set_selected(self.settings.get("sort_order", 0))
        settings_group.add(self.sort_combo)

        # Sampling Strategy
        self.sampling_combo = Adw.ComboRow(title="Sampling Strategy")
        self.sampling_combo.set_subtitle("Select how comments are collected and sampled")
        self.sampling_model = Gtk.StringList.new([
            "Extract All Comments (Exhaustive Full Scan)",
            "Unbiased Random Sample (Full Video Pool)",
            "Fast Random Sample (Bounded Pool)",
            "Sequential (First N Comments as Ordered)"
        ])
        self.sampling_combo.set_model(self.sampling_model)
        self.sampling_combo.set_selected(self.settings.get("sampling_strategy", 1))
        self.sampling_combo.connect("notify::selected", self.on_sampling_strategy_changed)
        settings_group.add(self.sampling_combo)

        # Sample Size (N)
        self.sample_size_row = Adw.SpinRow.new_with_range(1, 100000, 1)
        self.sample_size_row.set_digits(0)
        self.sample_size_row.set_title("Sample Size (N)")
        self.sample_size_row.set_subtitle("Number of comments to include in the final dataset")
        self.sample_size_row.set_value(float(self.settings.get("sample_size", 100)))
        settings_group.add(self.sample_size_row)

        # Custom Pool Size (for Fast Random Sample)
        self.pool_size_row = Adw.SpinRow.new_with_range(50, 500000, 100)
        self.pool_size_row.set_digits(0)
        self.pool_size_row.set_title("Pool Scan Limit")
        self.pool_size_row.set_subtitle("Maximum comments to scan before random sampling")
        self.pool_size_row.set_value(float(self.settings.get("pool_size", 2000)))
        settings_group.add(self.pool_size_row)

        # Include Replies Switch
        self.replies_row = Adw.SwitchRow()
        self.replies_row.set_title("Include Replies")
        self.replies_row.set_subtitle("When disabled, excludes reply threads to prevent discussion thread bias")
        self.replies_row.set_active(self.settings.get("include_replies", True))
        settings_group.add(self.replies_row)

        # Initialize sensitivity of sample/pool size based on strategy
        self.on_sampling_strategy_changed(self.sampling_combo, None)

        # -------------------------------------------------------------
        # Group 3: Authentication & Cookies (Optional)
        # -------------------------------------------------------------
        auth_group = Adw.PreferencesGroup(
            title="Authentication &amp; Cookies (Optional)",
            description="Netscape cookies.txt is required for age-restricted or private videos."
        )
        content_box.append(auth_group)

        self.cookie_row = Adw.ActionRow()
        self.cookie_row.set_title("Cookie File")
        saved_cookies = self.settings.get("cookies_path")
        if saved_cookies and os.path.exists(saved_cookies):
            self.cookies_path = saved_cookies
            self.cookie_row.set_subtitle(f"Loaded: {os.path.basename(saved_cookies)}")
        else:
            self.cookie_row.set_subtitle("None (public comments only)")

        cookie_browse_btn = Gtk.Button(label="Browse...")
        cookie_browse_btn.set_valign(Gtk.Align.CENTER)
        cookie_browse_btn.connect("clicked", self.on_browse_cookies)
        self.cookie_row.add_suffix(cookie_browse_btn)

        self.cookie_clear_btn = Gtk.Button(label="Clear")
        self.cookie_clear_btn.set_valign(Gtk.Align.CENTER)
        self.cookie_clear_btn.add_css_class("flat")
        self.cookie_clear_btn.connect("clicked", self.on_clear_cookies)
        self.cookie_clear_btn.set_visible(bool(self.cookies_path))
        self.cookie_row.add_suffix(self.cookie_clear_btn)

        auth_group.add(self.cookie_row)

        # -------------------------------------------------------------
        # Action Buttons Box
        # -------------------------------------------------------------
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        action_box.set_halign(Gtk.Align.CENTER)
        action_box.set_margin_top(6)
        action_box.set_margin_bottom(6)
        content_box.append(action_box)

        self.extract_btn = Gtk.Button(label="Start Extraction")
        self.extract_btn.add_css_class("suggested-action")
        self.extract_btn.add_css_class("pill")
        self.extract_btn.connect("clicked", self.on_extract_clicked)
        action_box.append(self.extract_btn)

        self.cancel_btn = Gtk.Button(label="Stop Extraction")
        self.cancel_btn.add_css_class("destructive-action")
        self.cancel_btn.add_css_class("pill")
        self.cancel_btn.set_visible(False)
        self.cancel_btn.connect("clicked", self.on_cancel_clicked)
        action_box.append(self.cancel_btn)

        self.export_btn = Gtk.Button(label="Export CSV...")
        self.export_btn.add_css_class("accent")
        self.export_btn.add_css_class("pill")
        self.export_btn.set_sensitive(False)
        self.export_btn.connect("clicked", self.on_export_clicked)
        action_box.append(self.export_btn)

        # -------------------------------------------------------------
        # Group 4: Live Execution Monitor & Stats
        # -------------------------------------------------------------
        monitor_group = Adw.PreferencesGroup(title="Execution Monitor")
        content_box.append(monitor_group)

        # Status & Stats Banner
        self.stats_label = Gtk.Label(label="Status: Ready to extract.")
        self.stats_label.set_halign(Gtk.Align.START)
        self.stats_label.add_css_class("dim-label")
        monitor_group.add(self.stats_label)

        # Terminal Log Box
        log_frame = Gtk.Frame()
        log_frame.set_margin_top(8)
        monitor_group.add(log_frame)

        scrolled_log = Gtk.ScrolledWindow()
        scrolled_log.set_min_content_height(220)
        scrolled_log.set_max_content_height(350)
        log_frame.set_child(scrolled_log)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_monospace(True)
        self.log_view.set_left_margin(12)
        self.log_view.set_right_margin(12)
        self.log_view.set_top_margin(10)
        self.log_view.set_bottom_margin(10)
        scrolled_log.set_child(self.log_view)

        self.win.present()

    def show_toast(self, text):
        toast = Adw.Toast.new(text)
        self.toast_overlay.add_toast(toast)

    def on_paste_clicked(self, button):
        clipboard = self.win.get_clipboard()
        clipboard.read_text_async(None, self.on_paste_finished)

    def on_paste_finished(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self.url_entry.set_text(text.strip())
        except Exception:
            pass

    def on_sampling_strategy_changed(self, combo, pspec):
        idx = combo.get_selected()
        # 0 is "Extract All Comments (Exhaustive Full Scan)"
        self.sample_size_row.set_sensitive(idx != 0)
        self.pool_size_row.set_visible(idx == 2)

    def on_browse_cookies(self, button):
        if hasattr(Gtk, 'FileDialog'):
            dialog = Gtk.FileDialog()
            dialog.set_title("Select Netscape cookies.txt")
            filter_txt = Gtk.FileFilter()
            filter_txt.set_name("Cookie text files (*.txt)")
            filter_txt.add_pattern("*.txt")
            filter_all = Gtk.FileFilter()
            filter_all.set_name("All files (*)")
            filter_all.add_pattern("*")
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(filter_txt)
            filters.append(filter_all)
            dialog.set_filters(filters)
            dialog.open(self.win, None, self.on_cookies_dialog_finish)
        else:
            dialog = Gtk.FileChooserNative.new(
                "Select Netscape cookies.txt",
                self.win,
                Gtk.FileChooserAction.OPEN,
                "_Open",
                "_Cancel"
            )
            dialog.connect("response", self.on_cookies_native_finish)
            dialog.show()

    def on_cookies_dialog_finish(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
            if gfile:
                path = gfile.get_path()
                if path:
                    self.set_cookies_path(path)
        except Exception:
            pass

    def on_cookies_native_finish(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = dialog.get_file()
            if gfile:
                path = gfile.get_path()
                if path:
                    self.set_cookies_path(path)

    def set_cookies_path(self, path):
        self.cookies_path = path
        self.cookie_row.set_subtitle(f"Loaded: {os.path.basename(path)}")
        self.cookie_clear_btn.set_visible(True)
        self.settings["cookies_path"] = path
        save_settings(self.settings)
        self.show_toast(f"Cookies loaded from {os.path.basename(path)}")

    def on_clear_cookies(self, button):
        self.cookies_path = None
        self.cookie_row.set_subtitle("None (public comments only)")
        self.cookie_clear_btn.set_visible(False)
        self.settings.pop("cookies_path", None)
        save_settings(self.settings)
        self.show_toast("Cookies cleared.")

    def append_log(self, text):
        buf = self.log_view.get_buffer()
        iter_end = buf.get_end_iter()
        buf.insert(iter_end, text + "\n")
        mark = buf.create_mark(None, buf.get_end_iter(), False)
        self.log_view.scroll_to_mark(mark, 0.0, False, 0.0, 0.0)

    def on_extract_clicked(self, button):
        raw_url = self.url_entry.get_text()
        video_id = extract_video_id(raw_url)
        if not video_id:
            self.show_toast("Please provide a valid YouTube URL or video ID.")
            self.append_log("[ERROR] Invalid YouTube URL or video ID format.")
            return

        # Read configurations
        sort_mode = "recent" if self.sort_combo.get_selected() == 1 else "popular"
        strategy_idx = self.sampling_combo.get_selected()
        sample_size = max(1, int(self.sample_size_row.get_value()))
        custom_pool = max(1, int(self.pool_size_row.get_value()))
        include_replies = self.replies_row.get_active()

        # Save settings for next launch
        self.settings["sort_order"] = self.sort_combo.get_selected()
        self.settings["sampling_strategy"] = strategy_idx
        self.settings["sample_size"] = sample_size
        self.settings["pool_size"] = custom_pool
        self.settings["include_replies"] = include_replies
        save_settings(self.settings)

        # Determine extraction pool size
        # Strategy 0: All Comments (Exhaustive Scan)
        # Strategy 1: Unbiased Random Sample (Full Video Pool)
        # Strategy 2: Fast Random Sample (Bounded Pool)
        # Strategy 3: Sequential (First N as Ordered)
        if strategy_idx in (0, 1):
            pool_size = None  # Full scan
        elif strategy_idx == 2:
            pool_size = max(custom_pool, sample_size)
        else:
            pool_size = sample_size

        # Reset state & UI
        self.extracted_comments = []
        self.stop_event.clear()
        self.log_view.get_buffer().set_text("")
        self.extract_btn.set_visible(False)
        self.cancel_btn.set_visible(True)
        self.export_btn.set_sensitive(False)
        self.stats_label.set_text("Status: Initializing yt-dlp extraction task...")

        # Spawn background extraction thread
        self.extraction_thread = threading.Thread(
            target=self.run_extraction_worker,
            args=(raw_url, sort_mode, strategy_idx, sample_size, pool_size, include_replies),
            daemon=True
        )
        self.extraction_thread.start()

    def on_cancel_clicked(self, button):
        self.stop_event.set()
        self.append_log("[USER] Stop requested. Finalizing collected comments...")
        self.cancel_btn.set_sensitive(False)

    def run_extraction_worker(self, url, sort_mode, strategy_idx, sample_size, pool_size, include_replies):
        try:
            GLib.idle_add(self.append_log, f"[TASK] Starting yt-dlp extraction for URL: {url}")
            strategy_names = [
                "Full Scan (All Comments)",
                f"Unbiased Random Sample (Target: {sample_size})",
                f"Fast Random Sample (Pool: {pool_size}, Target: {sample_size})",
                f"Sequential Ordered (Target: {sample_size})"
            ]
            GLib.idle_add(self.append_log, f"[CONFIG] Strategy: {strategy_names[strategy_idx]} | Include Replies: {include_replies}")

            all_comments = []
            aborted = False

            generator = get_comments_scraper_gen(
                video_url=url,
                max_comments=pool_size,
                sort_mode=sort_mode,
                include_replies=include_replies,
                cookies_file=self.cookies_path,
                stop_event=self.stop_event
            )

            for chunk in generator:
                if 'log' in chunk:
                    GLib.idle_add(self.append_log, chunk['log'])
                if 'stats' in chunk:
                    stats = chunk['stats']
                    msg = f"Status: Extracted {stats['total']} comments ({stats['top_level']} top-level, {stats['replies']} replies)"
                    GLib.idle_add(self.stats_label.set_text, msg)
                if 'error' in chunk:
                    GLib.idle_add(self.append_log, f"[ERROR] {chunk['error']}")
                    GLib.idle_add(self.show_toast, chunk['error'])
                    GLib.idle_add(self.stats_label.set_text, "Status: Extraction failed.")
                    GLib.idle_add(self.on_worker_finished, False, [])
                    return
                if 'result' in chunk:
                    all_comments = chunk['result']
                    aborted = chunk.get('aborted', False)

            if not all_comments:
                if aborted:
                    GLib.idle_add(self.append_log, "[ABORT] Extraction stopped before any comments were collected.")
                    GLib.idle_add(self.stats_label.set_text, "Status: Extraction cancelled.")
                    GLib.idle_add(self.show_toast, "Extraction cancelled.")
                else:
                    GLib.idle_add(self.append_log, "[ERROR] No comments were retrieved.")
                    GLib.idle_add(self.stats_label.set_text, "Status: No comments found.")
                    GLib.idle_add(self.show_toast, "No comments found.")
                GLib.idle_add(self.on_worker_finished, False, [])
                return

            # Apply sampling de-biasing
            if strategy_idx in (1, 2):
                if len(all_comments) > sample_size:
                    GLib.idle_add(
                        self.append_log,
                        f"[SAMPLE] Performing uniform random sampling: selecting {sample_size} from total pool of {len(all_comments)} comments."
                    )
                    selected_comments = random.sample(all_comments, sample_size)
                else:
                    note = f"[SAMPLE] Total collected ({len(all_comments)}) <= requested sample ({sample_size}). Keeping all {len(all_comments)} available comments."
                    if not include_replies:
                        note += " (Replies excluded per settings; all available top-level comments retrieved)."
                    GLib.idle_add(self.append_log, note)
                    selected_comments = all_comments
            elif strategy_idx == 3:
                selected_comments = all_comments[:sample_size]
            else:
                selected_comments = all_comments

            GLib.idle_add(self.append_log, f"[COMPLETE] Ready with {len(selected_comments)} processed comments.")
            status_text = f"Status: Finished. {len(selected_comments)} comments ready for export."
            if aborted:
                status_text += " (Stopped early)"
            GLib.idle_add(self.stats_label.set_text, status_text)
            GLib.idle_add(self.on_worker_finished, True, selected_comments)

        except Exception as e:
            GLib.idle_add(self.append_log, f"[FATAL] Extraction thread error: {e}")
            GLib.idle_add(self.stats_label.set_text, "Status: Error occurred.")
            GLib.idle_add(self.on_worker_finished, False, [])

    def on_worker_finished(self, success, comments):
        self.extract_btn.set_visible(True)
        self.cancel_btn.set_visible(False)
        self.cancel_btn.set_sensitive(True)

        if success and comments:
            self.extracted_comments = comments
            self.export_btn.set_sensitive(True)
            self.show_toast(f"Extraction complete: {len(comments)} comments ready.")
        else:
            self.export_btn.set_sensitive(False)

    def on_export_clicked(self, button):
        if not self.extracted_comments:
            return

        default_name = f"yt_comments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        if hasattr(Gtk, 'FileDialog'):
            dialog = Gtk.FileDialog()
            dialog.set_title("Export Comments to CSV")
            dialog.set_initial_name(default_name)
            filter_csv = Gtk.FileFilter()
            filter_csv.set_name("CSV Spreadsheets (*.csv)")
            filter_csv.add_pattern("*.csv")
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(filter_csv)
            dialog.set_filters(filters)
            dialog.save(self.win, None, self.on_export_dialog_finish)
        else:
            dialog = Gtk.FileChooserNative.new(
                "Export Comments to CSV",
                self.win,
                Gtk.FileChooserAction.SAVE,
                "_Save",
                "_Cancel"
            )
            dialog.set_current_name(default_name)
            dialog.connect("response", self.on_export_native_finish)
            dialog.show()

    def on_export_dialog_finish(self, dialog, result):
        try:
            gfile = dialog.save_finish(result)
            if gfile:
                path = gfile.get_path()
                if path:
                    self.write_csv_file(path)
        except Exception:
            pass

    def on_export_native_finish(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = dialog.get_file()
            if gfile:
                path = gfile.get_path()
                if path:
                    self.write_csv_file(path)

    def write_csv_file(self, filepath):
        try:
            if not filepath.lower().endswith('.csv'):
                filepath += '.csv'
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                writer.writerow([
                    'Comment ID',
                    'Author',
                    'Channel ID',
                    'Published Date',
                    'Likes',
                    'Is Reply',
                    'Reply Count',
                    'Comment Text'
                ])
                for c in self.extracted_comments:
                    writer.writerow([
                        c.get('cid', ''),
                        c.get('nickname', ''),
                        c.get('channel_id', ''),
                        c.get('date', ''),
                        c.get('votes', '0'),
                        'Yes' if c.get('is_reply', False) else 'No',
                        c.get('reply_count', 0),
                        c.get('comment', '')
                    ])
            self.append_log(f"[EXPORT] Successfully saved {len(self.extracted_comments)} comments to {filepath}")
            self.show_toast(f"Exported {len(self.extracted_comments)} comments to CSV!")
        except Exception as e:
            self.append_log(f"[ERROR] Failed to save CSV file: {e}")
            self.show_toast(f"Failed to save CSV: {e}")


if __name__ == '__main__':
    app = YouTubeCommentExtractorApp()
    app.run(sys.argv)
