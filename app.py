from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, Response, stream_with_context
import yt_dlp
import csv
import io
import random
import os
import re
import json
from urllib.parse import urlparse, parse_qs, urlencode
import requests
from datetime import datetime, timedelta
import http.cookiejar

try:
    from youtube_comment_downloader import YoutubeCommentDownloader
    YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE = True
except ImportError:
    YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE = False
    print("Warning: youtube_comment_downloader not available")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
COOKIES_FILE = os.path.join(DATA_DIR, 'cookies.txt')

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/api/auth/callback")

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

def get_comment_date(comment):
    if not isinstance(comment, dict): return ''
    for key in ['timestamp', 'time_parsed', 'publishedAt', 'published_at', 'date', 'time', 'created_at', 'publishedTime', 'publishedTimeText']:
        if comment.get(key):
            parsed = parse_comment_date_value(comment[key])
            if parsed: return parsed
    return ''

def get_comments_scraper_gen(video_url, max_comments=None, sort_mode='popular'):
    video_id = extract_video_id(video_url)
    if not video_id: 
        yield {'error': 'Invalid YouTube URL'}
        return
    
    all_comments = []
    
    if YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE:
        try:
            yield {'log': '[SYSTEM] Initializing scraper engine...'}
            downloader = YoutubeCommentDownloader()
            if os.path.exists(COOKIES_FILE):
                yield {'log': '[INFO] Injecting cookies for restricted video bypass...'}
                cj = http.cookiejar.MozillaCookieJar(COOKIES_FILE)
                cj.load(ignore_discard=True, ignore_expires=True)
                downloader.session.cookies.update(cj)
            
            yt_sort_by = 1 if sort_mode == 'recent' else 0
            yield {'log': f'[NETWORK] Fetching {sort_mode} comments directly from YouTube...'}
            gen = downloader.get_comments_from_url(f"https://www.youtube.com/watch?v={video_id}", sort_by=yt_sort_by)
            
            count = 0
            for comment in gen:
                text = comment.get('text', '').strip()
                if not text: continue
                all_comments.append({
                    'nickname': comment.get('author', 'Anonymous'),
                    'date': get_comment_date(comment) or parse_comment_date_value(comment.get('time', '')) or 'Unknown',
                    'comment': text[:1000]
                })
                count += 1
                if count % 200 == 0: yield {'log': f'[NETWORK] Downloaded {count} comments...'}
                if max_comments and count >= max_comments: break
            
            yield {'log': f'[SUCCESS] Fetched {len(all_comments)} comments.'}
            yield {'result': all_comments}
            return
        except Exception as e: 
            yield {'log': f'[ERROR] Downloader failed: {e}'}

    if not all_comments or len(all_comments) < 10:
        try:
            yield {'log': '[SYSTEM] Falling back to robust yt-dlp extraction...'}
            opts = {'skip_download': True, 'quiet': True, 'getcomments': True, 'extractor_args': {'youtube': {'max_comments': ['all','all','all','all']}}}
            if os.path.exists(COOKIES_FILE): opts['cookiefile'] = COOKIES_FILE
            with yt_dlp.YoutubeDL(opts) as ydl:
                yield {'log': '[NETWORK] Extracting video metadata and executing JS logic...'}
                info = ydl.extract_info(video_url, download=False)
                if info and 'comments' in info:
                    for i, c in enumerate(info['comments']):
                        text = c.get('text', '').strip()
                        if not text: continue
                        all_comments.append({
                            'nickname': c.get('author', 'Anonymous'),
                            'date': get_comment_date(c) or (parse_comment_date_value(c['timestamp']) if 'timestamp' in c else 'Unknown'),
                            'comment': text[:1000]
                        })
                        if (i+1) % 200 == 0: yield {'log': f'[NETWORK] Downloaded {i+1} comments...'}
                        if max_comments and len(all_comments) >= max_comments: break
            yield {'log': f'[SUCCESS] Fetched {len(all_comments)} comments via yt-dlp.'}
        except Exception as e: 
            yield {'log': f'[ERROR] Fallback failed: {e}'}
            
    yield {'result': all_comments}

def get_comments_api_gen(video_id, max_comments, access_token, sort_mode='popular'):
    yield {'log': '[SYSTEM] Initializing Official YouTube Data API v3...'}
    url = 'https://www.googleapis.com/youtube/v3/commentThreads'
    headers = {'Authorization': f'Bearer {access_token}'}
    api_order = 'time' if sort_mode == 'recent' else 'relevance'
    
    params = {'part': 'snippet,replies', 'videoId': video_id, 'maxResults': 100, 'textFormat': 'plainText', 'order': api_order}
    comments = []
    
    yield {'log': '[INFO] Authenticated with Google successfully.'}
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
def index(): return render_template('index.html')

@app.route('/api/auth/status')
def auth_status():
    return jsonify({
        'logged_in': 'google_token' in session,
        'configured': bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    })

@app.route('/api/auth/login')
def login():
    if not GOOGLE_CLIENT_ID: return "Google Client ID not configured.", 500
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'https://www.googleapis.com/auth/youtube.force-ssl',
        'access_type': 'offline',
        'prompt': 'consent'
    }
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")

@app.route('/api/auth/callback')
def auth_callback():
    code = request.args.get('code')
    if not code: return "No code provided", 400
    res = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
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

@app.route('/api/settings/cookies', methods=['POST', 'GET', 'DELETE'])
def handle_cookies():
    if request.method == 'POST':
        try:
            cookies = request.get_json().get('cookies', '')
            if not cookies.startswith('# Netscape HTTP Cookie File'): return jsonify({'error': 'Invalid format.'}), 400
            with open(COOKIES_FILE, 'w', encoding='utf-8') as f: f.write(cookies)
            return jsonify({'success': True, 'message': 'Cookies saved!'})
        except Exception as e: return jsonify({'error': str(e)}), 500
    elif request.method == 'GET':
        return jsonify({'has_cookies': os.path.exists(COOKIES_FILE)})
    elif request.method == 'DELETE':
        if os.path.exists(COOKIES_FILE): os.remove(COOKIES_FILE)
        return jsonify({'success': True})

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.get_json()
    
    def generate():
        try:
            video_url = data.get('url', '').strip()
            method = data.get('method', 'scraper')
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

            yield json.dumps({'log': f'[SYSTEM] Booting extraction task for Video ID: {video_id}'}) + '\n'

            num_comments = None if str(num_comments).lower() == 'all' else max(1, min(int(num_comments), 10000))
            
            if selection_mode == 'random':
                pool_size = 5000
                yield json.dumps({'log': '[INFO] Deep Scan Mode engaged. Fetching massive pool for true randomness...'}) + '\n'
            else:
                pool_size = num_comments if num_comments else None

            all_comments = []
            if method == 'api':
                if 'google_token' not in session:
                    yield json.dumps({'error': 'You must Sign in with Google (in Settings) to use the API method.'}) + '\n'
                    return
                for chunk in get_comments_api_gen(video_id, max_comments=pool_size, access_token=session['google_token'], sort_mode=sort_mode):
                    if 'log' in chunk: yield json.dumps({'log': chunk['log']}) + '\n'
                    if 'error' in chunk:
                        yield json.dumps({'error': chunk['error']}) + '\n'
                        if chunk['error'] == 'UNAUTHORIZED': session.pop('google_token', None)
                        return
                    if 'result' in chunk: all_comments = chunk['result']
            else:
                for chunk in get_comments_scraper_gen(video_url, max_comments=pool_size, sort_mode=sort_mode):
                    if 'log' in chunk: yield json.dumps({'log': chunk['log']}) + '\n'
                    if 'error' in chunk: 
                        yield json.dumps({'error': chunk['error']}) + '\n'
                        return
                    if 'result' in chunk: all_comments = chunk['result']

            if not all_comments:
                yield json.dumps({'error': 'No comments found. Try using the other method or check permissions.'}) + '\n'
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
