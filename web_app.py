import os
import threading
import time
import socket
import json
from flask import Flask, render_template, request, Response, jsonify, send_file
from werkzeug.utils import secure_filename
from zeroconf import ServiceInfo, Zeroconf
import tempfile
import csv

# Assuming scraper.py is in the same directory
from scraper import get_comments_scraper_gen, extract_video_id

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# Global state for simple progress tracking (in-memory for single user)
extraction_state = {
    "status": "idle",
    "comments": [],
    "logs": [],
    "progress": 0,
    "total_target": 0
}

class DummyLogger:
    def info(self, msg):
        extraction_state["logs"].append(f"[INFO] {msg}")
    def error(self, msg):
        extraction_state["logs"].append(f"[ERROR] {msg}")
    def debug(self, msg):
        extraction_state["logs"].append(f"[DEBUG] {msg}")

def run_extraction(url, sort_mode, strategy_idx, sample_size, pool_size, include_replies, cookies_path):
    extraction_state["status"] = "running"
    extraction_state["comments"] = []
    extraction_state["logs"] = []
    extraction_state["progress"] = 0
    extraction_state["total_target"] = sample_size if strategy_idx != 0 else "All"
    
    logger = DummyLogger()
    logger.info(f"Starting extraction for {url}...")
    
    try:
        max_comments = None
        if strategy_idx in (1, 2) and pool_size > 0:
            max_comments = pool_size
            
        gen = get_comments_scraper_gen(url, sort_mode, cookies_path, logger, max_comments, include_replies)
        
        all_comments = []
        for c in gen:
            all_comments.append(c)
            extraction_state["progress"] = len(all_comments)
            
        # Apply sampling
        logger.info(f"Total extracted: {len(all_comments)} comments.")
        
        if strategy_idx == 1 and sample_size > 0: # Head and Tail
            half = sample_size // 2
            if len(all_comments) > sample_size:
                final_comments = all_comments[:half] + all_comments[-half:]
            else:
                final_comments = all_comments
        elif strategy_idx == 2 and sample_size > 0: # Random
            import random
            if len(all_comments) > sample_size:
                final_comments = random.sample(all_comments, sample_size)
            else:
                final_comments = all_comments
        else:
            final_comments = all_comments
            
        extraction_state["comments"] = final_comments
        extraction_state["status"] = "done"
        logger.info("Extraction finished successfully.")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        extraction_state["status"] = "error"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.form
    url = data.get('url', '')
    sort_mode = int(data.get('sort_mode', 0))
    strategy_idx = int(data.get('strategy_idx', 0))
    sample_size = int(data.get('sample_size', 0))
    pool_size = int(data.get('pool_size', 0))
    include_replies = data.get('include_replies', 'false').lower() == 'true'
    
    cookies_path = None
    if 'cookies' in request.files:
        f = request.files['cookies']
        if f.filename != '':
            cookies_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(f.filename))
            f.save(cookies_path)

    if extraction_state["status"] == "running":
        return jsonify({"error": "An extraction is already running."}), 400

    t = threading.Thread(target=run_extraction, args=(url, sort_mode, strategy_idx, sample_size, pool_size, include_replies, cookies_path))
    t.start()
    
    return jsonify({"success": True})

@app.route('/api/status')
def api_status():
    return jsonify({
        "status": extraction_state["status"],
        "progress": extraction_state["progress"],
        "total_target": extraction_state["total_target"],
        "logs": extraction_state["logs"][-20:], # Send last 20 logs
        "total_comments": len(extraction_state["comments"])
    })

@app.route('/api/download')
def api_download():
    if extraction_state["status"] != "done":
        return "Not finished yet", 400
        
    out_path = os.path.join(app.config['UPLOAD_FOLDER'], 'comments_export.csv')
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Author", "Text", "Like Count", "Is Favorited", "Date", "Parent ID"])
        for c in extraction_state["comments"]:
            writer.writerow([
                c.get("id", ""),
                c.get("author", ""),
                c.get("text", ""),
                c.get("like_count", 0),
                c.get("is_favorited", False),
                c.get("time_text", ""),
                c.get("parent", "")
            ])
            
    return send_file(out_path, as_attachment=True, download_name="comments_export.csv")

def register_mdns():
    zeroconf = Zeroconf()
    desc = {'path': '/'}
    # Standard mDNS uses .local
    info = ServiceInfo(
        "_http._tcp.local.",
        "YT Comment Extractor Web._http._tcp.local.",
        addresses=[socket.inet_aton("0.0.0.0")],
        port=5000,
        properties=desc,
        server="web.yt-comment.extractor.local.",
    )
    zeroconf.register_service(info)
    return zeroconf

if __name__ == '__main__':
    zc = register_mdns()
    print("mDNS broadcasted. Server starting on 0.0.0.0:5000")
    try:
        app.run(host='0.0.0.0', port=5000)
    finally:
        zc.unregister_all_services()
        zc.close()
