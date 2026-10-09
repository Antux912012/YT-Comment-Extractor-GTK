from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
import yt_dlp
import csv
import io
import random
import os
import re
from urllib.parse import urlparse, parse_qs, urlencode
import requests
from datetime import datetime, timedelta
import http.cookiejar

try:
    from youtube_comment_downloader import YoutubeCommentDownloader
    YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE = True
except ImportError:
    YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE = False
    print("Warning: youtube_comment_downloader not available, will use fallback methods")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
COOKIES_FILE = os.path.join(DATA_DIR, 'cookies.txt')

# Google OAuth Constants
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
    except Exception as e: print(f"Error extracting video ID: {e}")
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

def get_comments_scraper(video_url, max_comments=None):
    video_id = extract_video_id(video_url)
    if not video_id: return []
    all_comments = []
    
    if YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE:
        try:
            downloader = YoutubeCommentDownloader()
            if os.path.exists(COOKIES_FILE) and hasattr(downloader, 'session'):
                cj = http.cookiejar.MozillaCookieJar(COOKIES_FILE)
                cj.load(ignore_discard=True, ignore_expires=True)
                downloader.session.cookies.update(cj)
            
            gen = downloader.get_comments_from_url(f"https://www.youtube.com/watch?v={video_id}")
            for comment in gen:
                text = comment.get('text', '').strip()
                if not text: continue
                all_comments.append({
                    'nickname': comment.get('author', 'Anonymous'),
                    'date': get_comment_date(comment) or parse_comment_date_value(comment.get('time', '')) or 'Unknown',
                    'comment': text[:1000]
                })
                if max_comments and len(all_comments) >= max_comments: return all_comments
        except Exception as e: print(f"Scraper Method 1 failed: {e}")

    if not all_comments or len(all_comments) < 10:
        try:
            opts = {'skip_download': True, 'quiet': True, 'getcomments': True, 'extractor_args': {'youtube': {'max_comments': ['all','all','all','all']}}}
            if os.path.exists(COOKIES_FILE): opts['cookiefile'] = COOKIES_FILE
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if info and 'comments' in info:
                    for c in info['comments']:
                        text = c.get('text', '').strip()
                        if not text: continue
                        all_comments.append({
                            'nickname': c.get('author', 'Anonymous'),
                            'date': get_comment_date(c) or (parse_comment_date_value(c['timestamp']) if 'timestamp' in c else 'Unknown'),
                            'comment': text[:1000]
                        })
                        if max_comments and len(all_comments) >= max_comments: break
        except Exception as e: print(f"Scraper Method 2 failed: {e}")
    return all_comments

def get_comments_api(video_id, max_comments, access_token):
    url = 'https://www.googleapis.com/youtube/v3/commentThreads'
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'part': 'snippet,replies', 'videoId': video_id, 'maxResults': 100, 'textFormat': 'plainText'}
    comments = []
    
    while True:
        res = requests.get(url, headers=headers, params=params)
        if not res.ok:
            if res.status_code == 401: raise Exception("UNAUTHORIZED")
            if res.status_code == 403: raise Exception(f"API Quota Exceeded or Forbidden: {res.json().get('error', {}).get('message', res.text)}")
            raise Exception(f"YouTube API Error: {res.text}")
        
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
            if max_comments and len(comments) >= max_comments: return comments[:max_comments]
            
        if 'nextPageToken' in data: params['pageToken'] = data['nextPageToken']
        else: break
    return comments

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
    try:
        data = request.get_json()
        video_url, method = data.get('url', '').strip(), data.get('method', 'scraper')
        num_comments, selection_mode = data.get('num_comments', 100), data.get('selection_mode', 'random')
        
        if not video_url: return jsonify({'error': 'Provide a valid URL'}), 400
        video_id = extract_video_id(video_url)
        if not video_id: return jsonify({'error': 'Invalid YouTube URL'}), 400

        num_comments = None if str(num_comments).lower() == 'all' else max(1, min(int(num_comments), 10000))
        pool_size = num_comments if selection_mode == 'ordered' and num_comments else (1000 if num_comments is None else min(num_comments * 3, 10000))

        if method == 'api':
            if 'google_token' not in session: return jsonify({'error': 'Not logged in with Google.'}), 401
            try:
                all_comments = get_comments_api(video_id, max_comments=pool_size, access_token=session['google_token'])
            except Exception as e:
                if "UNAUTHORIZED" in str(e):
                    session.pop('google_token', None)
                    return jsonify({'error': 'Session expired. Please sign in again.'}), 401
                raise e
        else:
            all_comments = get_comments_scraper(video_url, max_comments=pool_size)

        if not all_comments:
            return jsonify({'error': 'No comments found. Try using the other method or check permissions.'}), 404

        if selection_mode == 'ordered':
            selected = all_comments[:num_comments] if num_comments else all_comments
        else:
            if num_comments and len(all_comments) > num_comments: selected = random.sample(all_comments, num_comments)
            else:
                random.shuffle(all_comments)
                selected = all_comments

        return jsonify({'success': True, 'comments': selected, 'count': len(selected), 'total_available': len(all_comments)})
    except Exception as e: return jsonify({'error': f'Server error: {str(e)}'}), 500

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
