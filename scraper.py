import os
import re
import random
import http.cookiejar
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

try:
    from youtube_comment_downloader import YoutubeCommentDownloader
    YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE = True
except ImportError:
    YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE = False

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False


def extract_video_id(url_or_id):
    """
    Extracts an 11-character YouTube video ID from various URL patterns
    or direct ID strings.
    """
    if not url_or_id:
        return None
    clean = url_or_id.strip()

    # Raw 11-character YouTube video ID
    if re.match(r'^[a-zA-Z0-9_-]{11}$', clean):
        return clean

    # Regex patterns for various YouTube URL structures
    patterns = [
        r'(?:v=|\/v\/|\/embed\/|\/shorts\/|\/live\/)([a-zA-Z0-9_-]{11})',
        r'youtu\.be\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        m = re.search(pattern, clean)
        if m:
            return m.group(1)

    try:
        parsed = urlparse(clean)
        if 'youtube.com' in parsed.netloc:
            qs = parse_qs(parsed.query)
            if 'v' in qs and qs['v']:
                return qs['v'][0]
            path_parts = [p for p in parsed.path.split('/') if p]
            if path_parts and path_parts[0] in ('shorts', 'live', 'embed', 'v'):
                return path_parts[1] if len(path_parts) > 1 else path_parts[0]
    except Exception:
        pass
    return None


def parse_relative_date_text(text):
    if not text:
        return None
    value = text.strip().lower()
    now = datetime.now(timezone.utc)
    if value == 'today':
        return now
    if value == 'yesterday':
        return now - timedelta(days=1)
    match = re.search(r'(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago', value)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        multipliers = {
            'second': 1, 'minute': 60, 'hour': 3600,
            'day': 86400, 'week': 604800, 'month': 2592000, 'year': 31536000
        }
        return now - timedelta(seconds=amount * multipliers.get(unit.rstrip('s'), multipliers.get(unit, 0)))
    for fmt in ['%b %d, %Y', '%B %d, %Y', '%d %b %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_comment_date_value(value):
    if not value:
        return ''
    if isinstance(value, dict):
        extracted = value.get('simpleText') or ''.join([r.get('text', '') for r in value.get('runs', [])])
        return parse_comment_date_value(extracted) if extracted else ''
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            ts = int(value)
            if ts > 10**12:
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d-%m-%Y']:
        try:
            return datetime.strptime(str(value), fmt).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    relative = parse_relative_date_text(str(value))
    return relative.strftime('%Y-%m-%d %H:%M:%S') if relative else str(value)


def get_comment_date(comment):
    if 'time_parsed' in comment and comment['time_parsed']:
        try:
            return datetime.fromtimestamp(comment['time_parsed'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    if 'timestamp' in comment and comment['timestamp']:
        try:
            return datetime.fromtimestamp(comment['timestamp'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    if 'time_text' in comment:
        return parse_comment_date_value(comment['time_text'])
    if 'time' in comment:
        return parse_comment_date_value(comment['time'])
    return None


def get_comments_scraper_gen(
    video_url,
    max_comments=None,
    sort_mode='popular',
    include_replies=True,
    cookies_file=None,
    stop_event=None
):
    """
    Generator yielding live progress logs and returning extracted comments.
    Guarantees no arbitrary text truncation and supports reply filtering to eliminate bias.
    """
    video_id = extract_video_id(video_url)
    if not video_id:
        yield {'error': 'Invalid YouTube URL or Video ID. Please check your input.'}
        return

    normalized_url = f"https://www.youtube.com/watch?v={video_id}"
    all_comments = []
    top_level_count = 0
    reply_count = 0

    downloader_failed = False
    downloader_error = None

    if YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE:
        try:
            yield {'log': f'[SYSTEM] Initializing extraction for Video ID: {video_id}'}
            downloader = YoutubeCommentDownloader()

            if cookies_file and os.path.exists(cookies_file):
                try:
                    yield {'log': f'[AUTH] Loading cookies from {os.path.basename(cookies_file)}...'}
                    cj = http.cookiejar.MozillaCookieJar(cookies_file)
                    cj.load(ignore_discard=True, ignore_expires=True)
                    downloader.session.cookies.update(cj)
                    yield {'log': f'[AUTH] Successfully injected {len(cj)} cookies.'}
                except Exception as ce:
                    yield {'log': f'[WARNING] Failed to load cookies file: {ce}. Proceeding anonymously.'}

            yt_sort_by = 1 if sort_mode == 'recent' else 0
            order_name = "Newest First" if sort_mode == 'recent' else "Top Comments / Relevant"
            yield {'log': f'[NETWORK] Connecting to YouTube API ({order_name})...'}

            gen = downloader.get_comments_from_url(normalized_url, sort_by=yt_sort_by)

            for comment in gen:
                if stop_event and stop_event.is_set():
                    yield {'log': '[ABORT] Extraction stopped by user request.'}
                    yield {
                        'result': all_comments,
                        'aborted': True,
                        'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
                    }
                    return

                text = comment.get('text', '').strip()
                if not text:
                    continue

                cid = comment.get('cid', '')
                is_reply = comment.get('reply', False) or ('.' in cid)

                # De-biasing filter: Exclude replies if requested
                if is_reply and not include_replies:
                    continue

                if is_reply:
                    reply_count += 1
                else:
                    top_level_count += 1

                all_comments.append({
                    'cid': cid,
                    'nickname': comment.get('author', 'Anonymous'),
                    'channel_id': comment.get('channel', ''),
                    'date': get_comment_date(comment) or 'Unknown',
                    'votes': comment.get('votes', '0'),
                    'reply_count': comment.get('replies', 0),
                    'is_reply': is_reply,
                    'comment': text  # Full unabridged text (no truncation)
                })

                if len(all_comments) % 50 == 0:
                    yield {
                        'log': f'[PROGRESS] Collected {len(all_comments)} comments ({top_level_count} top-level, {reply_count} replies)...',
                        'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
                    }

                if max_comments and len(all_comments) >= max_comments:
                    break

            yield {'log': f'[SUCCESS] Extraction complete. Total comments fetched: {len(all_comments)}.'}
            yield {
                'result': all_comments,
                'aborted': False,
                'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
            }
            return

        except Exception as e:
            downloader_failed = True
            downloader_error = str(e)
            yield {'log': f'[WARNING] Primary engine encountered an issue: {e}'}

    # Fallback to yt-dlp only if downloader was unavailable or encountered an error without comments
    if (not YOUTUBE_COMMENT_DOWNLOADER_AVAILABLE or downloader_failed) and not all_comments:
        if YTDLP_AVAILABLE:
            try:
                yield {'log': '[SYSTEM] Falling back to robust yt-dlp engine...'}
                opts = {
                    'skip_download': True,
                    'quiet': True,
                    'getcomments': True,
                    'extractor_args': {'youtube': {'max_comments': ['all', 'all', 'all', 'all']}}
                }
                if cookies_file and os.path.exists(cookies_file):
                    opts['cookiefile'] = cookies_file

                with yt_dlp.YoutubeDL(opts) as ydl:
                    yield {'log': '[NETWORK] Extracting video metadata and comments via yt-dlp...'}
                    info = ydl.extract_info(normalized_url, download=False)
                    if info and 'comments' in info:
                        for c in info['comments']:
                            if stop_event and stop_event.is_set():
                                yield {'log': '[ABORT] Extraction stopped by user request.'}
                                yield {
                                    'result': all_comments,
                                    'aborted': True,
                                    'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
                                }
                                return

                            text = c.get('text', '').strip()
                            if not text:
                                continue

                            is_reply = c.get('parent') != 'root' if 'parent' in c else False
                            if is_reply and not include_replies:
                                continue

                            if is_reply:
                                reply_count += 1
                            else:
                                top_level_count += 1

                            all_comments.append({
                                'cid': c.get('id', ''),
                                'nickname': c.get('author', 'Anonymous'),
                                'channel_id': c.get('author_id', ''),
                                'date': get_comment_date(c) or 'Unknown',
                                'votes': str(c.get('like_count', '0')),
                                'reply_count': 0,
                                'is_reply': is_reply,
                                'comment': text  # Full unabridged text
                            })

                            if len(all_comments) % 50 == 0:
                                yield {
                                    'log': f'[PROGRESS] Fetched {len(all_comments)} comments via yt-dlp...',
                                    'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
                                }

                            if max_comments and len(all_comments) >= max_comments:
                                break

                yield {'log': f'[SUCCESS] yt-dlp extraction finished with {len(all_comments)} comments.'}
            except Exception as e:
                yield {'log': f'[ERROR] yt-dlp fallback also failed: {e}'}
        else:
            yield {'error': f'Extraction failed: {downloader_error or "Unknown error"}'}

    if not all_comments:
        yield {
            'error': 'No comments found. The video may have comments disabled, be age-restricted, or require a cookies.txt file.'
        }
        return

    yield {
        'result': all_comments,
        'aborted': False,
        'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
    }
