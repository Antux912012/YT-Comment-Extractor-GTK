from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import csv
import io
import random
import json
import re
import os
from urllib.parse import urlparse, parse_qs
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

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
COOKIES_FILE = os.path.join(DATA_DIR, 'cookies.txt')

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    try:
        parsed = urlparse(url)
        if 'youtube.com' in parsed.netloc:
            if 'v' in parse_qs(parsed.query):
                return parse_qs(parsed.query)['v'][0]
            if '/shorts/' in parsed.path or '/live/' in parsed.path:
                return parsed.path.split('/')[-1]
        elif 'youtu.be' in parsed.netloc:
            return parsed.path.strip('/').split('?')[0]
    except Exception as e:
        print(f"Error extracting video ID: {e}")
    return None

def parse_relative_date_text(text):
    if not text: return None
    value = text.strip().lower()
    if value == 'today': return datetime.utcnow()
    if value == 'yesterday': return datetime.utcnow() - timedelta(days=1)
    match = re.search(r'(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago', value)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        multipliers = {
            'second': 1, 'seconds': 1, 'minute': 60, 'minutes': 60, 'hour': 3600, 'hours': 3600,
            'day': 86400, 'days': 86400, 'week': 604800, 'weeks': 604800,
            'month': 2592000, 'months': 2592000, 'year': 31536000, 'years': 31536000,
        }
        return datetime.utcnow() - timedelta(seconds=amount * multipliers.get(unit, 0))
    try:
        for fmt in ['%b %d, %Y', '%B %d, %Y', '%d %b %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
            try: return datetime.strptime(value, fmt)
            except ValueError: continue
    except: pass
    return None

def parse_comment_date_value(value):
    if value is None or value == '': return ''
    if isinstance(value, dict):
        extracted = value.get('simpleText')
        if not extracted and 'runs' in value:
            extracted = ''.join([run.get('text', '') for run in value.get('runs', [])])
        return parse_comment_date_value(extracted) if extracted else ''
    if isinstance(value, (int, float)):
        try:
            ts = int(value)
            if ts > 10**12: ts = ts / 1000
            return datetime.utcfromtimestamp(ts).strftime('%d-%m-%Y')
        except: return ''
    value = str(value).strip()
    if not value: return ''
    if value.isdigit():
        try:
            ts = int(value)
            if ts > 10**12: ts = ts / 1000
            return datetime.utcfromtimestamp(ts).strftime('%d-%m-%Y')
        except: pass
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%d-%m-%Y')
    except: pass
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d-%m-%Y']:
        try: return datetime.strptime(value, fmt).strftime('%d-%m-%Y')
        except: pass
    relative = parse_relative_date_text(value)
    if relative: return relative.strftime('%d-%m-%Y')
    return str(value)

def get_comment_date(comment):
    if not isinstance(comment, dict): return ''
    date_keys = ['timestamp', 'time_parsed', 'publishedAt', 'published_at', 'date', 'time', 'created_at', 'publishedTime', 'publishedTimeText', 'createdTime']
    for key in date_keys:
        if key in comment and comment[key] is not None:
            parsed = parse_comment_date_value(comment[key])
            if parsed: return parsed
    return ''

def extract_total_comments(video_url):
    try:
        ydl_opts = {'skip_download': True, 'quiet': True, 'no_warnings': True}
        if os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if info and 'comment_count' in info:
                return info['comment_count']
    except Exception as e:
        print(f"Could not extract total comment count: {e}")
    return 0

def get_comments(video_url, max_comments=None):
    video_id = extract_video_id(video_url)
    if not video_id: return []
    all_comments = []
    
    if YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE:
        try:
            print("[Attempting Method 1] youtube-comment-downloader...")
            comments = extract_with_downloader(video_id, max_comments)
            if comments:
                all_comments.extend(comments)
                if max_comments and len(all_comments) >= max_comments:
                    return all_comments[:max_comments]
        except Exception as e:
            print(f"Method 1 failed: {e}")
            
    if not all_comments or len(all_comments) < 10:
        try:
            print("[Attempting Method 2] yt-dlp extraction...")
            comments = extract_with_ytdlp(video_url, max_comments)
            if comments:
                all_comments.extend(comments)
        except Exception as e:
            print(f"Method 2 failed: {e}")
    return all_comments

def load_cookies_to_session(session):
    if os.path.exists(COOKIES_FILE):
        try:
            cj = http.cookiejar.MozillaCookieJar(COOKIES_FILE)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies.update(cj)
            print("Loaded cookies into session.")
        except Exception as e:
            print(f"Failed to load cookies: {e}")

def extract_with_downloader(video_id, max_comments=None):
    comments = []
    downloader = YoutubeCommentDownloader()
    
    # Attempt to inject cookies into session if available
    if hasattr(downloader, 'session'):
        load_cookies_to_session(downloader.session)

    comments_gen = downloader.get_comments_from_url(f"https://www.youtube.com/watch?v={video_id}")
    count = 0
    for comment in comments_gen:
        text = comment.get('text', '').strip()
        if not text or len(text) <= 2: continue
        comment_date = get_comment_date(comment)
        if not comment_date:
            comment_date = parse_comment_date_value(comment.get('time', ''))
        comments.append({
            'nickname': comment.get('author', 'Anonymous'),
            'date': comment_date or 'Unknown',
            'comment': text[:1000]
        })
        count += 1
        if max_comments and count >= max_comments: break
    return comments

def extract_with_ytdlp(video_url, max_comments=None):
    comments = []
    ydl_opts = {
        'skip_download': True, 'quiet': True, 'no_warnings': True, 'getcomments': True,
        'extractor_args': {'youtube': {'max_comments': ['all', 'all', 'all', 'all']}}
    }
    if os.path.exists(COOKIES_FILE):
        ydl_opts['cookiefile'] = COOKIES_FILE

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        if info and 'comments' in info:
            for comment in info['comments']:
                text = comment.get('text', '').strip()
                if not text: continue
                comment_date = get_comment_date(comment)
                if not comment_date and 'timestamp' in comment:
                    comment_date = parse_comment_date_value(comment['timestamp'])
                comments.append({
                    'nickname': comment.get('author', 'Anonymous'),
                    'date': comment_date or 'Unknown',
                    'comment': text[:1000]
                })
                if max_comments and len(comments) >= max_comments: break
    return comments

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/extract', methods=['POST'])
def extract():
    try:
        data = request.get_json()
        if not data: return jsonify({'error': 'No data provided'}), 400
        video_url = data.get('url', '').strip()
        num_comments = data.get('num_comments', 100)
        selection_mode = data.get('selection_mode', 'random')
        if not video_url: return jsonify({'error': 'Please provide a valid YouTube URL'}), 400
        
        if str(num_comments).lower() == 'all': num_comments = None
        else:
            try: num_comments = max(1, min(int(num_comments), 10000))
            except: num_comments = 100

        selection_mode = 'ordered' if selection_mode == 'ordered' else 'random'
        total_available = extract_total_comments(video_url)
        
        pool_size = num_comments if selection_mode == 'ordered' and num_comments else (1000 if num_comments is None else min(num_comments * 3, 10000))
        all_comments = get_comments(video_url, max_comments=pool_size)

        if not all_comments:
            return jsonify({'error': 'No comments found. The video might be private, restricted, or have comments disabled. Try providing cookies in settings.'}), 404

        if selection_mode == 'ordered':
            selected = all_comments[:num_comments] if num_comments else all_comments
        else:
            if num_comments and len(all_comments) > num_comments:
                selected = random.sample(all_comments, num_comments)
            else:
                random.shuffle(all_comments)
                selected = all_comments

        return jsonify({
            'success': True,
            'selection_mode': selection_mode,
            'comments': selected,
            'count': len(selected),
            'total_available': total_available or len(all_comments)
        })
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/download', methods=['POST'])
def download():
    try:
        data = request.get_json()
        comments = data.get('comments', [])
        if not comments: return jsonify({'error': 'No comments to download'}), 400
        output = io.StringIO()
        writer = csv.writer(output, delimiter='|', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['Nickname', 'Date', 'Comment'])
        for comment in comments:
            writer.writerow([comment.get('nickname', 'Anonymous'), comment.get('date', 'Unknown'), comment.get('comment', '')])
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name=f'youtube_comments_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
    except Exception as e:
        return jsonify({'error': f'Error creating CSV: {str(e)}'}), 500

@app.route('/api/settings/cookies', methods=['POST', 'GET', 'DELETE'])
def handle_cookies():
    if request.method == 'POST':
        try:
            data = request.get_json()
            cookies_content = data.get('cookies', '')
            if not cookies_content.startswith('# Netscape HTTP Cookie File'):
                return jsonify({'error': 'Invalid cookie format. Must be Netscape format.'}), 400
            with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
                f.write(cookies_content)
            return jsonify({'success': True, 'message': 'Cookies saved successfully!'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    elif request.method == 'GET':
        has_cookies = os.path.exists(COOKIES_FILE)
        return jsonify({'has_cookies': has_cookies})
    elif request.method == 'DELETE':
        if os.path.exists(COOKIES_FILE):
            os.remove(COOKIES_FILE)
        return jsonify({'success': True, 'message': 'Cookies deleted.'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
