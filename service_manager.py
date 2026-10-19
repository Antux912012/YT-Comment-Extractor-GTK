import os
import sys
import time
import threading
import subprocess
import webbrowser
from werkzeug.serving import make_server

import web_app


def _configure_pystray_backend():
    """
    Prevent pystray from crashing with unhandled ValueError when gi is installed
    without AppIndicator3 / AyatanaAppIndicator3 typelibs.
    """
    if os.environ.get('PYSTRAY_BACKEND'):
        return
    try:
        import gi
        has_appindicator = False
        for ns in ('AppIndicator3', 'AyatanaAppIndicator3'):
            try:
                gi.require_version(ns, '0.1')
                has_appindicator = True
                break
            except ValueError:
                continue
        if not has_appindicator:
            try:
                gi.require_version('Gtk', '3.0')
                os.environ['PYSTRAY_BACKEND'] = 'gtk'
            except ValueError:
                os.environ['PYSTRAY_BACKEND'] = 'xorg'
    except ImportError:
        pass


_configure_pystray_backend()

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pystray
    PYSTRAY_AVAILABLE = True
except Exception as e:
    print(f"[Tray Warning] pystray unavailable ({e}); falling back to headless mode.")
    pystray = None
    PYSTRAY_AVAILABLE = False

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


LAN_MODE = False


def show_info_dialog():
    local_ip = get_local_ip()
    if LAN_MODE:
        msg = (
            "YouTube Comment Extractor Web Service v0.5 is running (LAN mode)!\n\n"
            "• Local Machine:   http://127.0.0.1:5000\n"
            "• Local Network:   http://yt-extractor.local:5000\n"
            f"• Direct LAN IP:   http://{local_ip}:5000\n\n"
            "You can manage the service anytime via the system tray icon."
        )
    else:
        msg = (
            "YouTube Comment Extractor Web Service v0.5 is running (Loopback mode)!\n\n"
            "• Local Machine:   http://127.0.0.1:5000\n\n"
            "Service bound to 127.0.0.1 for local security. Pass --lan to expose on LAN.\n"
            "You can manage the service anytime via the system tray icon."
        )
    try:
        subprocess.Popen([
            'zenity', '--info',
            '--title=YouTube Comment Extractor Service v0.5',
            f'--text={msg}'
        ])
    except Exception:
        try:
            subprocess.Popen([
                'notify-send',
                'YouTube Comment Extractor Service v0.5',
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
                show_message_dialog("YT Extractor Service v0.5", "The service is already running.")
            return

        bind_host = '0.0.0.0' if LAN_MODE else '127.0.0.1'
        try:
            server_instance = make_server(bind_host, 5000, web_app.app, threaded=True)
        except OSError as e:
            server_instance = None
            err_msg = f"Could not bind to port 5000 ({e}). Another instance may already be running."
            print(f"[Server Error] {err_msg}")
            if notify:
                show_message_dialog("YT Extractor Service v0.5", err_msg)
            return

        if LAN_MODE:
            try:
                zeroconf_instance = web_app.register_mdns()
            except Exception as e:
                print(f"[mDNS Error] {e}")
                zeroconf_instance = None
        else:
            zeroconf_instance = None

        server_thread = threading.Thread(target=server_instance.serve_forever, daemon=True)
        server_thread.start()

    if notify:
        show_info_dialog()


def stop_server(notify=True):
    global server_instance, server_thread, zeroconf_instance
    with state_lock:
        if server_instance is None:
            if notify:
                show_message_dialog("YT Extractor Service v0.5", "The service is already stopped.")
            return

        if zeroconf_instance:
            try:
                zeroconf_instance.unregister_all_services()
                zeroconf_instance.close()
            except Exception:
                pass
            zeroconf_instance = None

        srv = server_instance
        thr = server_thread
        server_instance = None
        server_thread = None

        try:
            srv.shutdown()
        except Exception:
            pass
        try:
            srv.server_close()
        except Exception:
            pass
        if thr and thr.is_alive():
            thr.join(timeout=2.0)

    if notify:
        show_message_dialog("YT Extractor Service v0.5", "Service has been stopped.")


def restart_server():
    stop_server(notify=False)
    time.sleep(0.3)
    start_server(notify=False)
    if server_instance is not None:
        show_message_dialog("YT Extractor Service v0.5", "Service restarted successfully!")


def on_open_browser(icon, item):
    webbrowser.open("http://127.0.0.1:5000")


def on_show_info(icon, item):
    show_info_dialog()


def on_start(icon, item):
    threading.Thread(target=start_server, kwargs={'notify': True}, daemon=True).start()


def on_stop(icon, item):
    threading.Thread(target=stop_server, kwargs={'notify': True}, daemon=True).start()


def on_restart(icon, item):
    threading.Thread(target=restart_server, daemon=True).start()


def on_quit(icon, item):
    stop_server(notify=False)
    icon.stop()


def get_icon():
    if Image is None:
        return None
    base = get_base_dir()
    for candidate in [
        os.path.join(base, "icon.png"),
        os.path.join(base, "YTCommentExtractor.png"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png"),
        "/usr/share/yt-extractor-service/icon.png",
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
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Comment Extractor Service Manager")
    parser.add_argument("--lan", action="store_true", help="Expose server on 0.0.0.0 (LAN) and advertise via mDNS")
    args, _ = parser.parse_known_args()
    if args.lan:
        LAN_MODE = True

    # Start server and show startup notification window
    start_server(notify=True)

    if PYSTRAY_AVAILABLE and Image is not None:
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
        tray_icon = pystray.Icon("YTCommentExtractorService", icon_img, "YT Comment Extractor Web Service v0.5", menu)
        try:
            tray_icon.run()
        except Exception as e:
            print(f"[Tray Error] Tray loop failed ({e}); keeping service alive in background.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                stop_server(notify=False)
    else:
        bind_host = "0.0.0.0" if LAN_MODE else "127.0.0.1"
        print(f"Running YT Comment Extractor Web Service v0.5 in headless mode on {bind_host}:5000")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_server(notify=False)
