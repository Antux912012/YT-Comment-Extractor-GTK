from flask import Flask, render_template, request, jsonify, send_file, session, redirect, Response, stream_with_context
import csv
import io
import random
import os
import re
import json
import threading
from urllib.parse import urlparse, parse_qs, urlencode
import requests
from datetime import datetime, timedelta
import webview

app = Flask(__name__)
app.secret_key = get_secret_key()



import configparser
from pathlib import Path
import os

CONFIG_DIR = Path.home() / '.config' / 'yt-comment-extractor'
CONFIG_FILE = CONFIG_DIR / 'config.ini'

def load_config():
    config = configparser.ConfigParser()
    if CONFIG_FILE.exists():
        config.read(CONFIG_FILE)
    return config

def get_secret_key():
    config = load_config()
    if 'APP' in config and 'secret_key' in config['APP']:
        return bytes.fromhex(config['APP']['secret_key'])
    
    # Generate and save a new one
    new_secret = os.urandom(24).hex()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if 'APP' not in config:
        config['APP'] = {}
    config['APP']['secret_key'] = new_secret
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)
    return bytes.fromhex(new_secret)

def save_config(client_id, client_secret):
    config = load_config()
    if 'OAUTH' not in config:
        config['OAUTH'] = {}
    config['OAUTH']['client_id'] = client_id
    config['OAUTH']['client_secret'] = client_secret
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)

def get_oauth_creds():
    config = load_config()
    if 'OAUTH' in config:
        return config['OAUTH'].get('client_id'), config['OAUTH'].get('client_secret')
    return None, None

GOOGLE_REDIRECT_URI = "http://localhost:5000/api/auth/callback"



def extract_video_id(url):
    try:
        parsed = urlparse(url)
        if 'youtube.com' in parsed.netloc:
            if 'v' in parse_qs(parsed.query): return parse_qs(parsed.query)['v'][0]
            if '/shorts/' in parsed.path or '/live/' in parsed.path: return parsed.path.split('/')[-1]
        elif 'youtu.be' in parsed.netloc:
            return parsed.path.strip('/').split('?')[0]
    except Exception as e: pass
    return None

def parse_relative_date_text(text):
    if not text: return None
    value = text.strip().lower()
    if value == 'today': return datetime.utcnow()
    if value == 'yesterday': return datetime.utcnow() - timedelta(days=1)
    match = re.search(r'(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago', value)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        multipliers = {'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400, 'week': 604800, 'month': 2592000, 'year': 31536000}
        return datetime.utcnow() - timedelta(seconds=amount * multipliers.get(unit.rstrip('s'), multipliers.get(unit, 0)))
    for fmt in ['%b %d, %Y', '%B %d, %Y', '%d %b %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
        try: return datetime.strptime(value, fmt)
        except ValueError: continue
    return None

def parse_comment_date_value(value):
    if not value: return ''
    if isinstance(value, dict):
        extracted = value.get('simpleText') or ''.join([r.get('text', '') for r in value.get('runs', [])])
        return parse_comment_date_value(extracted) if extracted else ''
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            ts = int(value)
            if ts > 10**12: ts /= 1000
            return datetime.utcfromtimestamp(ts).strftime('%d-%m-%Y')
        except: pass
    try: return datetime.fromisoformat(str(value).replace('Z', '+00:00')).strftime('%d-%m-%Y')
    except: pass
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d-%m-%Y']:
        try: return datetime.strptime(str(value), fmt).strftime('%d-%m-%Y')
        except: pass
    relative = parse_relative_date_text(str(value))
    return relative.strftime('%d-%m-%Y') if relative else str(value)

def get_comments_api_gen(video_id, max_comments, access_token, sort_mode='popular'):
    yield {'log': '[SYSTEM] Initializing Official YouTube Data API v3...'}
    url = 'https://www.googleapis.com/youtube/v3/commentThreads'
    headers = {'Authorization': f'Bearer {access_token}'}
    api_order = 'time' if sort_mode == 'recent' else 'relevance'
    
    params = {'part': 'snippet,replies', 'videoId': video_id, 'maxResults': 100, 'textFormat': 'plainText', 'order': api_order}
    comments = []
    
    yield {'log': '[INFO] Authenticated with Google securely.'}
    yield {'log': f'[NETWORK] Fetching {sort_mode} comments using API quotas...'}
    
    while True:
        res = requests.get(url, headers=headers, params=params)
        if not res.ok:
            if res.status_code == 401: yield {'error': 'UNAUTHORIZED', 'log': '[ERROR] Session expired. Please sign in again.'}; return
            if res.status_code == 403: yield {'error': 'QUOTA', 'log': f'[ERROR] API Quota Exceeded or Forbidden: {res.json().get("error", {}).get("message", res.text)}'}; return
            yield {'error': 'API_ERROR', 'log': f'[ERROR] YouTube API Error: {res.text}'}; return
        
        data = res.json()
        for item in data.get('items', []):
            top = item['snippet']['topLevelComment']['snippet']
            comments.append({
                'nickname': top.get('authorDisplayName', 'Anonymous'),
                'date': parse_comment_date_value(top.get('publishedAt')) or 'Unknown',
                'comment': top.get('textDisplay', '')[:1000]
            })
            if 'replies' in item:
                for reply in item['replies'].get('comments', []):
                    r_snip = reply['snippet']
                    comments.append({
                        'nickname': r_snip.get('authorDisplayName', 'Anonymous'),
                        'date': parse_comment_date_value(r_snip.get('publishedAt')) or 'Unknown',
                        'comment': r_snip.get('textDisplay', '')[:1000]
                    })
            if max_comments and len(comments) >= max_comments: break
            
        yield {'log': f'[NETWORK] Fetched {len(comments)} comments via API so far...'}
        
        if max_comments and len(comments) >= max_comments: break
        if 'nextPageToken' in data: params['pageToken'] = data['nextPageToken']
        else: break
        
    yield {'log': f'[SUCCESS] Finished fetching {len(comments)} comments.'}
    yield {'result': comments}

# ================== ROUTES ==================

@app.route('/')
def index(): 
    client_id, client_secret = get_oauth_creds()
    if not client_id or not client_secret:
        return redirect('/setup')
    return render_template('index.html')

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if request.method == 'POST':
        client_id = request.form.get('client_id', '').strip()
        client_secret = request.form.get('client_secret', '').strip()
        if client_id and client_secret:
            save_config(client_id, client_secret)
            return redirect('/')
        return render_template('setup.html', error="Both fields are required.")
    
    client_id, client_secret = get_oauth_creds()
    return render_template('setup.html', client_id=client_id or '', client_secret=client_secret or '')

@app.route('/api/auth/status')
def auth_status():
    client_id, client_secret = get_oauth_creds()
    return jsonify({
        'logged_in': 'google_token' in session,
        'configured': bool(client_id and client_secret)
    })

@app.route('/api/auth/login')
def login():
    client_id, client_secret = get_oauth_creds()
    if not client_id: return "Google Client ID not configured.", 500
    params = {
        'client_id': client_id,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'https://www.googleapis.com/auth/youtube.force-ssl',
        'access_type': 'offline',
        'prompt': 'consent'
    }
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")

@app.route('/api/auth/callback')
def auth_callback():
    client_id, client_secret = get_oauth_creds()
    code = request.args.get('code')
    if not code: return "No code provided", 400
    res = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': GOOGLE_REDIRECT_URI
    })
    if not res.ok: return f"Failed to fetch token: {res.text}", 400
    session['google_token'] = res.json().get('access_token')
    return redirect('/')

@app.route('/api/auth/logout')
def logout():
    session.pop('google_token', None)
    return jsonify({'success': True})

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.get_json()
    
    def generate():
        try:
            video_url = data.get('url', '').strip()
            sort_mode = data.get('sort_mode', 'popular')
            num_comments = data.get('num_comments', 100)
            selection_mode = data.get('selection_mode', 'random')
            
            if not video_url:
                yield json.dumps({'error': 'Provide a valid URL'}) + '\n'
                return
                
            video_id = extract_video_id(video_url)
            if not video_id:
                yield json.dumps({'error': 'Invalid YouTube URL'}) + '\n'
                return

            if 'google_token' not in session:
                yield json.dumps({'error': 'You must Sign in with Google to use the API extraction method.'}) + '\n'
                return

            yield json.dumps({'log': f'[SYSTEM] Booting extraction task for Video ID: {video_id}'}) + '\n'

            num_comments = None if str(num_comments).lower() == 'all' else max(1, min(int(num_comments), 10000))
            
            if selection_mode == 'random':
                pool_size = 5000
                yield json.dumps({'log': '[INFO] Deep Scan Mode engaged. Fetching massive pool for true randomness...'}) + '\n'
            else:
                pool_size = num_comments if num_comments else None

            all_comments = []
            
            for chunk in get_comments_api_gen(video_id, max_comments=pool_size, access_token=session['google_token'], sort_mode=sort_mode):
                if 'log' in chunk: yield json.dumps({'log': chunk['log']}) + '\n'
                if 'error' in chunk:
                    yield json.dumps({'error': chunk['error']}) + '\n'
                    if chunk['error'] == 'UNAUTHORIZED': session.pop('google_token', None)
                    return
                if 'result' in chunk: all_comments = chunk['result']

            if not all_comments:
                yield json.dumps({'error': 'No comments found. The video may have comments disabled or you lack permission.'}) + '\n'
                return

            yield json.dumps({'log': f'[SYSTEM] Filtering and sanitizing dataset...'}) + '\n'

            if selection_mode == 'ordered':
                selected = all_comments[:num_comments] if num_comments else all_comments
            else:
                if num_comments and len(all_comments) > num_comments: 
                    selected = random.sample(all_comments, num_comments)
                    yield json.dumps({'log': f'[INFO] Sampled {num_comments} true random comments from deep pool.'}) + '\n'
                else:
                    random.shuffle(all_comments)
                    selected = all_comments

            yield json.dumps({'log': '[SUCCESS] Extraction Pipeline Complete.'}) + '\n'
            yield json.dumps({
                'success': True, 
                'comments': selected, 
                'count': len(selected), 
                'total_available': len(all_comments), 
                'pool_size_fetched': len(all_comments),
                'selection_mode': selection_mode
            }) + '\n'

        except Exception as e: 
            yield json.dumps({'error': f'Server error: {str(e)}'}) + '\n'

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')

@app.route('/api/download', methods=['POST'])
def download():
    comments = request.get_json().get('comments', [])
    output = io.StringIO()
    writer = csv.writer(output, delimiter='|', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(['Nickname', 'Date', 'Comment'])
    for c in comments: writer.writerow([c.get('nickname', ''), c.get('date', ''), c.get('comment', '')])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name=f'yt_comments_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv')

def start_server():
    # Run the server on port 5000 in a daemon thread so the UI can wrap it
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Boot the local Flask server
    t = threading.Thread(target=start_server)
    t.daemon = True
    t.start()
    
    # Launch the native desktop window using pywebview
    webview.create_window(
        title='YouTube Comments Extractor', 
        url='http://127.0.0.1:5000', 
        width=1200, 
        height=800,
        min_size=(800, 600)
    )
    webview.start()
