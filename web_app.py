import io
import os
import socket
import sys
import tempfile
import threading

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

try:
    from zeroconf import ServiceInfo, Zeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

from exporters import export_to_csv, export_to_html, export_to_json
from scraper import apply_sampling, calculate_pool_size, extract_video_id, get_comments_scraper_gen

APP_VERSION = "0.5"


def get_base_dir():
    """Returns the base directory whether running as script or PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


app = Flask(__name__, template_folder=os.path.join(get_base_dir(), 'templates'))
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    if (
        origin.startswith(('http://localhost', 'http://127.0.0.1'))
        or origin.endswith('.github.io')
    ):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '86400'
    return response


@app.route('/api/<path:subpath>', methods=['OPTIONS'])
def options_preflight(subpath):
    return ('', 204)


# Global state for extraction tracking
extraction_state = {
    "status": "idle",
    "comments": [],
    "logs": [],
    "progress": 0,
    "total_target": 0,
    "video_info": {}
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
        extraction_state["video_info"] = {}
        stop_event.clear()

    extraction_state["logs"].append(f"[SYSTEM] Starting yt-dlp extraction for URL: {url}")

    try:
        max_pool = calculate_pool_size(strategy_idx, sample_size, pool_size)

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
            if 'video_info' in chunk:
                extraction_state["video_info"] = chunk['video_info']
            if 'error' in chunk:
                extraction_state["status"] = "error"
                extraction_state["logs"].append(f"[ERROR] {chunk['error']}")
                return
            if 'result' in chunk:
                all_comments = chunk['result']
                aborted = chunk.get('aborted', False)
                if 'video_info' in chunk:
                    extraction_state["video_info"] = chunk['video_info']

        if not all_comments:
            if aborted:
                extraction_state["status"] = "idle"
                extraction_state["logs"].append("[ABORT] Extraction cancelled before any comments were collected.")
            else:
                extraction_state["status"] = "error"
                extraction_state["logs"].append("[ERROR] No comments were retrieved from YouTube.")
            return

        final_comments, sample_log = apply_sampling(all_comments, strategy_idx, sample_size, include_replies)
        if sample_log:
            extraction_state["logs"].append(sample_log)

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
        extraction_state["logs"].append(f"[FATAL] Unexpected error: {e}")
        extraction_state["status"] = "error"
    finally:
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.remove(cookies_path)
            except OSError:
                pass
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
            try:
                os.chmod(cookies_path, 0o600)
            except Exception:
                pass

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


@app.route('/api/download', methods=['GET'])
@app.route('/api/download/<string:fmt>', methods=['GET'])
def api_download(fmt=None):
    if extraction_state["status"] != "done" or not extraction_state["comments"]:
        return jsonify({"error": "Extraction not finished or no comments available."}), 400

    export_format = (fmt or request.args.get('format', 'csv')).lower().strip()
    video_info = extraction_state.get("video_info") or {}
    vid = video_info.get("video_id") or "export"

    if export_format == 'json':
        data = export_to_json(extraction_state["comments"], video_info)
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=f"yt_comments_{vid}.json",
            mimetype="application/json; charset=utf-8"
        )
    elif export_format == 'html':
        data = export_to_html(extraction_state["comments"], video_info)
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=f"yt_comments_{vid}.html",
            mimetype="text/html; charset=utf-8"
        )
    else:  # csv (keeps emoji symbols via utf-8-sig)
        data = export_to_csv(extraction_state["comments"])
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=f"yt_comments_{vid}.csv",
            mimetype="text/csv; charset=utf-8"
        )


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
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Comment Extractor Web Service")
    parser.add_argument("--lan", action="store_true", help="Expose server on 0.0.0.0 (LAN) and advertise via mDNS")
    parser.add_argument("--host", default=None, help="Host to bind (defaults to 0.0.0.0 if --lan, else 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    args = parser.parse_args()

    host = args.host if args.host else ("0.0.0.0" if args.lan else "127.0.0.1")
    zc = None
    if args.lan or host == "0.0.0.0":
        zc = register_mdns()
        local_ip = get_local_ip()
        print(f"mDNS active as yt-extractor.local ({local_ip}:{args.port}). Server starting on {host}:{args.port}")
    else:
        print(f"Server starting on loopback only ({host}:{args.port}). Use --lan to expose on local network.")

    try:
        app.run(host=host, port=args.port)
    finally:
        if zc:
            try:
                zc.unregister_all_services()
                zc.close()
            except Exception:
                pass
