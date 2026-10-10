import pystray
from PIL import Image
import subprocess
import threading
import sys
import os
import time
import web_app

server_thread = None
server_process = None

def _run_server():
    # We must suppress Flask's automatic reloader in a thread
    zc = web_app.register_mdns()
    try:
        web_app.app.run(host='0.0.0.0', port=5000, use_reloader=False)
    finally:
        zc.unregister_all_services()
        zc.close()

def start_server():
    global server_thread
    if server_thread is None or not server_thread.is_alive():
        server_thread = threading.Thread(target=_run_server, daemon=True)
        server_thread.start()
        # Show Zenity info window
        subprocess.Popen([
            'zenity', '--info', '--title=YT Comment Extractor',
            '--text=YT Comment Extractor Web Service is now running!\n\nAccess it at:\nLocal: http://127.0.0.1:5000\nNetwork: http://yt-extractor.local:5000'
        ])

def stop_server():
    # Flask doesn't have a simple thread stop, but daemon threads die on exit
    # For a real stop, we'd need a werkzeug shutdown endpoint.
    # For now we will just show the dialog.
    subprocess.Popen([
        'zenity', '--info', '--title=YT Comment Extractor',
        '--text=Service will be stopped when you quit the application.'
    ])

def restart_server():
    subprocess.Popen([
        'zenity', '--info', '--title=YT Comment Extractor',
        '--text=Please quit and relaunch the application to restart the server.'
    ])

def on_start(icon, item):
    start_server()

def on_stop(icon, item):
    stop_server()

def on_restart(icon, item):
    restart_server()

def on_quit(icon, item):
    icon.stop()


if __name__ == '__main__':
    # Initial start
    start_server()

    # Load icon
    icon_image = Image.open("icon.png")

    menu = pystray.Menu(
        pystray.MenuItem("Start Service", on_start),
        pystray.MenuItem("Stop Service", on_stop),
        pystray.MenuItem("Restart Service", on_restart),
        pystray.MenuItem("Quit", on_quit)
    )

    icon = pystray.Icon("YTCommentExtractor", icon_image, "YT Comment Extractor Web", menu)
    icon.run()
