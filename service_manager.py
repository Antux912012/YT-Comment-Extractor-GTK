import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser
from PIL import Image
import pystray
from werkzeug.serving import make_server

import web_app

server_instance = None
server_thread = None
zeroconf_instance = None
state_lock = threading.Lock()

def get_base_dir():
    """Returns the base directory whether running as script or PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def get_local_ip():
    return web_app.get_local_ip()

def show_info_dialog():
    local_ip = get_local_ip()
    msg = (
        "YouTube Comment Extractor Web Service is running!\n\n"
        f"• Local Machine:   http://127.0.0.1:5000\n"
        f"• Local Network:   http://yt-extractor.local:5000\n"
        f"• Direct LAN IP:   http://{local_ip}:5000\n\n"
        "You can manage the service anytime via the system tray icon."
    )
    # Try zenity first
    try:
        subprocess.Popen([
            'zenity', '--info',
            '--title=YouTube Comment Extractor Service',
            f'--text={msg}'
        ])
    except (FileNotFoundError, Exception):
        # Fallback to notify-send
        try:
            subprocess.Popen([
                'notify-send',
                'YouTube Comment Extractor Service',
                msg
            ])
        except Exception:
            pass

def show_message_dialog(title, text):
    try:
        subprocess.Popen(['zenity', '--info', f'--title={title}', f'--text={text}'])
    except Exception:
        try:
            subprocess.Popen(['notify-send', title, text])
        except Exception:
            pass

def start_server(notify=True):
    global server_instance, server_thread, zeroconf_instance
    with state_lock:
        if server_instance is not None:
            if notify:
                show_message_dialog("YT Extractor Service", "The service is already running.")
            return

        try:
            zeroconf_instance = web_app.register_mdns()
        except Exception as e:
            print(f"[mDNS Error] {e}")

        server_instance = make_server('0.0.0.0', 5000, web_app.app, threaded=True)
        server_thread = threading.Thread(target=server_instance.serve_forever, daemon=True)
        server_thread.start()

    if notify:
        show_info_dialog()

def stop_server(notify=True):
    global server_instance, server_thread, zeroconf_instance
    with state_lock:
        if server_instance is None:
            if notify:
                show_message_dialog("YT Extractor Service", "The service is already stopped.")
            return

        if zeroconf_instance:
            try:
                zeroconf_instance.unregister_all_services()
                zeroconf_instance.close()
            except Exception:
                pass
            zeroconf_instance = None

        server_instance.shutdown()
        server_instance = None
        server_thread = None

    if notify:
        show_message_dialog("YT Extractor Service", "Service has been stopped.")

def restart_server():
    stop_server(notify=False)
    time.sleep(0.5)
    start_server(notify=False)
    show_message_dialog("YT Extractor Service", "Service restarted successfully!")

def on_open_browser(icon, item):
    webbrowser.open("http://127.0.0.1:5000")

def on_show_info(icon, item):
    show_info_dialog()

def on_start(icon, item):
    start_server(notify=True)

def on_stop(icon, item):
    stop_server(notify=True)

def on_restart(icon, item):
    restart_server()

def on_quit(icon, item):
    stop_server(notify=False)
    icon.stop()

def get_icon():
    base = get_base_dir()
    for candidate in [
        os.path.join(base, "icon.png"),
        os.path.join(base, "YTCommentExtractor.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png"),
        "/app/share/yt-extractor/icon.png"
    ]:
        if os.path.exists(candidate):
            try:
                return Image.open(candidate)
            except Exception:
                pass
    # Fallback colored square icon if missing
    return Image.new('RGB', (64, 64), color=(94, 129, 172))

if __name__ == '__main__':
    # Start server and show startup notification window
    start_server(notify=True)

    icon_img = get_icon()

    menu = pystray.Menu(
        pystray.MenuItem("Open Web Interface", on_open_browser, default=True),
        pystray.MenuItem("Show Server Address", on_show_info),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start Service", on_start),
        pystray.MenuItem("Stop Service", on_stop),
        pystray.MenuItem("Restart Service", on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit)
    )

    tray_icon = pystray.Icon("YTCommentExtractorService", icon_img, "YT Comment Extractor Web Service", menu)
    tray_icon.run()
