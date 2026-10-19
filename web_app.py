import os
import sys
import threading
import socket
import random
import csv
import tempfile
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

try:
    from zeroconf import ServiceInfo, Zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

from scraper import get_comments_scraper_gen, extract_video_id

APP_VERSION = "0.3"


def get_base_dir():
    """Returns the base directory whether running as script or PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


app = Flask(__name__, template_folder=os.path.join(get_base_dir(), 'templates'))
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Global state for extraction tracking
extraction_state = {
    "status": "idle",
    "comments": [],
    "logs": [],
    "progress": 0,
    "total_target": 0
}
stop_event = threading.Event()
extraction_lock = threading.Lock()


def safe_int(val, default):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def get_local_ip():
    """Discover the routable local network IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def run_extraction(url, sort_mode_str, strategy_idx, sample_size, pool_size, include_replies, cookies_path):
    with extraction_lock:
        extraction_state["status"] = "running"
        extraction_state["comments"] = []
        extraction_state["logs"] = []
        extraction_state["progress"] = 0
        extraction_state["total_target"] = sample_size if strategy_idx != 0 else "All"
        stop_event.clear()

    extraction_state["logs"].append(f"[SYSTEM] Starting yt-dlp extraction for URL: {url}")

    try:
        # Determine extraction pool size
        # Strategy 0: Full scan (All comments)
        # Strategy 1: Unbiased Random Sample (Full pool)
        # Strategy 2: Fast Random Sample (Bounded pool)
        # Strategy 3: Sequential (First N)
        if strategy_idx in (0, 1):
            max_pool = None
        elif strategy_idx == 2:
            bounded_pool = pool_size if (pool_size and pool_size > 0) else 2000
            max_pool = max(bounded_pool, sample_size)
        else:
            max_pool = sample_size

        gen = get_comments_scraper_gen(
            video_url=url,
            max_comments=max_pool,
            sort_mode=sort_mode_str,
            include_replies=include_replies,
            cookies_file=cookies_path,
            stop_event=stop_event
        )

        all_comments = []
        aborted = False

        for chunk in gen:
            if 'log' in chunk:
                extraction_state["logs"].append(chunk['log'])
            if 'stats' in chunk:
                extraction_state["progress"] = chunk['stats']['total']
            if 'error' in chunk:
                extraction_state["status"] = "error"
                extraction_state["logs"].append(f"[ERROR] {chunk['error']}")
                return
            if 'result' in chunk:
                all_comments = chunk['result']
                aborted = chunk.get('aborted', False)

        if not all_comments:
            if aborted:
                extraction_state["status"] = "idle"
                extraction_state["logs"].append("[ABORT] Extraction cancelled before any comments were collected.")
            else:
                extraction_state["status"] = "error"
                extraction_state["logs"].append("[ERROR] No comments were retrieved from YouTube.")
            return

        # Apply sampling strategy
        if strategy_idx in (1, 2) and sample_size > 0:
            if len(all_comments) > sample_size:
                extraction_state["logs"].append(
                    f"[SAMPLE] Applying uniform random sampling: selecting {sample_size} from {len(all_comments)} comments."
                )
                final_comments = random.sample(all_comments, sample_size)
            else:
                final_comments = all_comments
        elif strategy_idx == 3 and sample_size > 0:
            final_comments = all_comments[:sample_size]
        else:
            final_comments = all_comments

        extraction_state["comments"] = final_comments
        extraction_state["progress"] = len(final_comments)
        extraction_state["status"] = "done"
        if aborted:
            extraction_state["logs"].append(
                f"[COMPLETE] Extraction finalized (stopped early). Ready with {len(final_comments)} comments."
            )
        else:
            extraction_state["logs"].append(
                f"[COMPLETE] Extraction finished successfully with {len(final_comments)} comments."
            )

    except Exception as e:
        extraction_state["logs"].append(f"[FATAL] Unexpected error: {str(e)}")
        extraction_state["status"] = "error"
    finally:
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.remove(cookies_path)
            except Exception:
                pass


@app.route('/')
def index():
    return render_template('index.html', local_ip=get_local_ip(), version=APP_VERSION)


@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.form
    url = data.get('url', '').strip()
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL or Video ID."}), 400

    raw_sort = data.get('sort_mode', '0')
    sort_mode_str = "recent" if str(raw_sort) == '1' else "popular"
    strategy_idx = safe_int(data.get('strategy_idx', 0), 0)
    sample_size = max(1, safe_int(data.get('sample_size', 100), 100))
    pool_size = max(50, safe_int(data.get('pool_size', 2000), 2000))
    include_replies = data.get('include_replies', 'false').lower() == 'true'

    if extraction_state["status"] == "running":
        return jsonify({"error": "An extraction is already running. Please cancel it or wait."}), 400

    cookies_path = None
    if 'cookies' in request.files:
        f = request.files['cookies']
        if f and f.filename:
            safe_name = secure_filename(f.filename) or 'cookies.txt'
            cookies_path = os.path.join(app.config['UPLOAD_FOLDER'], f"yt_cookies_{os.getpid()}_{safe_name}")
            f.save(cookies_path)

    t = threading.Thread(
        target=run_extraction,
        args=(url, sort_mode_str, strategy_idx, sample_size, pool_size, include_replies, cookies_path),
        daemon=True
    )
    t.start()
    return jsonify({"success": True})


@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    if extraction_state["status"] == "running":
        stop_event.set()
        extraction_state["logs"].append("[USER] Cancel requested. Finalizing collected comments...")
        return jsonify({"success": True, "message": "Cancellation requested."})
    return jsonify({"error": "No extraction currently running."}), 400


@app.route('/api/status')
def api_status():
    return jsonify({
        "status": extraction_state["status"],
        "progress": extraction_state["progress"],
        "total_target": extraction_state["total_target"],
        "logs": extraction_state["logs"][-200:],
        "total_comments": len(extraction_state["comments"])
    })


@app.route('/api/download')
def api_download():
    if extraction_state["status"] != "done" or not extraction_state["comments"]:
        return "Extraction not finished or no comments available.", 400

    out_path = os.path.join(app.config['UPLOAD_FOLDER'], 'comments_export.csv')
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
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
        for c in extraction_state["comments"]:
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

    return send_file(out_path, as_attachment=True, download_name="comments_export.csv")


def register_mdns():
    """Registers mDNS with the actual routable LAN IP address."""
    if not ZEROCONF_AVAILABLE:
        return None
    try:
        zc = Zeroconf()
        desc = {'path': '/', 'version': APP_VERSION}
        local_ip = get_local_ip()
        info = ServiceInfo(
            "_http._tcp.local.",
            "YT Comment Extractor Web._http._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=5000,
            properties=desc,
            server="yt-extractor.local.",
        )
        zc.register_service(info, allow_name_change=True)
        return zc
    except Exception as e:
        print(f"[mDNS Warning] Could not register mDNS service: {e}")
        return None


if __name__ == '__main__':
    zc = register_mdns()
    local_ip = get_local_ip()
    print(f"mDNS active as yt-extractor.local ({local_ip}:5000). Server starting on 0.0.0.0:5000")
    try:
        app.run(host='0.0.0.0', port=5000)
    finally:
        if zc:
            try:
                zc.unregister_all_services()
                zc.close()
            except Exception:
                pass
