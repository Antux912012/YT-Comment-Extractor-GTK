import pystray
from PIL import Image
import subprocess
import threading
import sys
import os
import time

server_process = None

def start_server():
    global server_process
    if server_process is None or server_process.poll() is not None:
        server_process = subprocess.Popen([sys.executable, 'web_app.py'])
        # Show Zenity info window
        subprocess.Popen([
            'zenity', '--info', '--title=YT Comment Extractor',
            '--text=YT Comment Extractor Web Service is now running!\n\nAccess it at:\nLocal: http://127.0.0.1:5000\nNetwork: http://yt-extractor.local:5000'
        ])

def stop_server():
    global server_process
    if server_process and server_process.poll() is None:
        server_process.terminate()
        server_process.wait()
        server_process = None
        subprocess.Popen([
            'zenity', '--info', '--title=YT Comment Extractor',
            '--text=Service has been stopped.'
        ])

def restart_server():
    stop_server()
    time.sleep(1)
    start_server()

def on_start(icon, item):
    start_server()

def on_stop(icon, item):
    stop_server()

def on_restart(icon, item):
    restart_server()

def on_quit(icon, item):
    stop_server()
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
