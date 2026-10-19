import os
import re
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

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
    if not url_or_id or not isinstance(url_or_id, str):
        return None
    clean = url_or_id.strip()
    if not clean:
        return None

    # Raw 11-character YouTube video ID
    if re.match(r'^[a-zA-Z0-9_-]{11}$', clean):
        return clean

    # Regex patterns for various YouTube URL structures
    patterns = [
        r'(?:v=|\/v\/|\/embed\/|\/shorts\/|\/live\/)([a-zA-Z0-9_-]{11})(?![a-zA-Z0-9_-])',
        r'youtu\.be\/([a-zA-Z0-9_-]{11})(?![a-zA-Z0-9_-])',
    ]
    for pattern in patterns:
        m = re.search(pattern, clean)
        if m:
            return m.group(1)

    try:
        candidate = clean if '://' in clean else f'https://{clean}'
        parsed = urlparse(candidate)
        host = (parsed.netloc or '').lower()
        if 'youtube.com' in host or 'youtu.be' in host:
            qs = parse_qs(parsed.query)
            if 'v' in qs and qs['v']:
                vid = qs['v'][0].strip()
                if re.match(r'^[a-zA-Z0-9_-]{11}$', vid):
                    return vid
            path_parts = [p for p in parsed.path.split('/') if p]
            if 'youtu.be' in host and path_parts:
                vid = path_parts[0].strip()
                if re.match(r'^[a-zA-Z0-9_-]{11}$', vid):
                    return vid
            if path_parts and path_parts[0] in ('shorts', 'live', 'embed', 'v') and len(path_parts) > 1:
                vid = path_parts[1].strip()
                if re.match(r'^[a-zA-Z0-9_-]{11}$', vid):
                    return vid
    except Exception:
        pass
    return None


def parse_relative_date_text(text):
    if not text:
        return None
    value = re.sub(r'\s*\(edited\)\s*$', '', str(text).strip().lower())
    now = datetime.now(timezone.utc)
    if value in ('today', 'just now', 'now'):
        return now
    if value == 'yesterday':
        return now - timedelta(days=1)
    match = re.search(
        r'(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago',
        value
    )
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
    if value is None or value == '':
        return ''
    if isinstance(value, dict):
        extracted = value.get('simpleText') or ''.join([r.get('text', '') for r in value.get('runs', [])])
        return parse_comment_date_value(extracted) if extracted else ''
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            ts = float(value)
            if ts > 10**12:
                ts /= 1000.0
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
    if not isinstance(comment, dict):
        return None
    if comment.get('timestamp') is not None:
        try:
            return datetime.fromtimestamp(float(comment['timestamp']), tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    if comment.get('time_parsed') is not None:
        try:
            return datetime.fromtimestamp(float(comment['time_parsed']), tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    for key in ('_time_text', 'time_text', 'time'):
        if comment.get(key):
            return parse_comment_date_value(comment[key])
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
    Generator yielding live progress logs and returning extracted comments exclusively via yt-dlp.
    Guarantees no arbitrary text truncation and supports reply filtering to eliminate bias.
    """
    video_id = extract_video_id(video_url)
    if not video_id:
        yield {'error': 'Invalid YouTube URL or Video ID. Please check your input.'}
        return

    if not YTDLP_AVAILABLE:
        yield {'error': 'yt-dlp is not installed. Please install yt-dlp to extract comments.'}
        return

    normalized_url = f"https://www.youtube.com/watch?v={video_id}"
    all_comments = []
    comments_by_cid = {}
    pending_reply_counts = {}
    top_level_count = 0
    reply_count = 0

    sort_arg = 'new' if sort_mode == 'recent' else 'top'
    order_name = "Newest First" if sort_mode == 'recent' else "Top Comments / Relevant"
    max_r = 'all' if include_replies else '0'

    opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'getcomments': True,
        'extractor_args': {
            'youtube': {
                'comment_sort': [sort_arg],
                'max_comments': ['all', 'all', max_r, max_r],
            }
        }
    }

    yield {'log': f'[SYSTEM] Initializing yt-dlp extraction for Video ID: {video_id}'}

    if cookies_file:
        if os.path.exists(cookies_file):
            opts['cookiefile'] = cookies_file
            yield {'log': f'[AUTH] Loaded cookies from {os.path.basename(cookies_file)}.'}
        else:
            yield {'log': f'[WARNING] Cookie file not found ({cookies_file}). Proceeding anonymously.'}

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            yield {'log': f'[NETWORK] Fetching video metadata and streaming comments via yt-dlp ({order_name})...'}

            gen_holder = {}
            try:
                yt_ie = ydl.get_info_extractor('Youtube')
                if yt_ie and hasattr(yt_ie, '_get_comments'):
                    orig_get_comments = yt_ie._get_comments

                    def _capture_get_comments(*args, **kwargs):
                        g = orig_get_comments(*args, **kwargs)
                        gen_holder['gen'] = g
                        return g

                    yt_ie._get_comments = _capture_get_comments
            except Exception:
                yt_ie = None

            if stop_event and stop_event.is_set():
                yield {'log': '[ABORT] Extraction stopped by user request.'}
                yield {
                    'result': [],
                    'aborted': True,
                    'stats': {'total': 0, 'top_level': 0, 'replies': 0}
                }
                return

            info = ydl.extract_info(normalized_url, download=False, process=False)
            if not info:
                yield {'error': 'Failed to retrieve video metadata via yt-dlp.'}
                return

            video_title = info.get('title')
            if video_title:
                yield {'log': f'[INFO] Video: "{video_title}"'}

            comment_stream = gen_holder.get('gen')
            if comment_stream is None:
                if 'comments' in info and info['comments'] is not None:
                    comment_stream = iter(info['comments'])
                elif callable(info.get('__post_extractor')):
                    post_data = info['__post_extractor']() or {}
                    comment_stream = iter(post_data.get('comments') or [])
                else:
                    full_info = ydl.process_ie_result(info, download=False)
                    comment_stream = iter((full_info or {}).get('comments') or [])

            try:
                for c in comment_stream:
                    if stop_event and stop_event.is_set():
                        yield {'log': '[ABORT] Extraction stopped by user request.'}
                        yield {
                            'result': all_comments,
                            'aborted': True,
                            'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
                        }
                        return

                    if not isinstance(c, dict):
                        continue

                    text = (c.get('text') or '').strip()
                    if not text:
                        continue

                    cid = str(c.get('id') or c.get('cid') or '')
                    parent = c.get('parent')
                    if parent is not None:
                        is_reply = parent != 'root'
                    else:
                        is_reply = bool(c.get('reply', False) or ('.' in cid))

                    # De-biasing filter: Exclude replies if requested
                    if is_reply and not include_replies:
                        continue

                    if is_reply:
                        reply_count += 1
                        parent_cid = str(parent) if (parent and parent != 'root') else cid.split('.')[0]
                        root_cid = parent_cid.split('.')[0]
                        if root_cid in comments_by_cid:
                            comments_by_cid[root_cid]['reply_count'] += 1
                        else:
                            pending_reply_counts[root_cid] = pending_reply_counts.get(root_cid, 0) + 1
                    else:
                        top_level_count += 1

                    likes = c.get('like_count') if 'like_count' in c else c.get('votes')
                    votes_str = str(likes if likes is not None else 0)
                    initial_replies = c.get('reply_count') or c.get('replies') or pending_reply_counts.pop(cid, 0)
                    try:
                        initial_replies = int(initial_replies)
                    except (ValueError, TypeError):
                        initial_replies = 0

                    entry = {
                        'cid': cid,
                        'nickname': c.get('author') or 'Anonymous',
                        'channel_id': c.get('author_id') or c.get('channel') or '',
                        'date': get_comment_date(c) or 'Unknown',
                        'votes': votes_str,
                        'reply_count': initial_replies,
                        'is_reply': is_reply,
                        'comment': text  # Full unabridged text (no truncation)
                    }
                    all_comments.append(entry)
                    if cid and not is_reply:
                        comments_by_cid[cid] = entry

                    if len(all_comments) == 1 or len(all_comments) % 25 == 0:
                        yield {
                            'log': f'[PROGRESS] Collected {len(all_comments)} comments ({top_level_count} top-level, {reply_count} replies)...',
                            'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
                        }

                    if max_comments and len(all_comments) >= max_comments:
                        break
            except Exception as stream_err:
                if stream_err.__class__.__name__ == 'CommentsDisabled':
                    yield {'error': 'Comments are disabled on this video.'}
                    return
                raise

        yield {
            'log': f'[SUCCESS] yt-dlp extraction complete. Total comments fetched: {len(all_comments)} ({top_level_count} top-level, {reply_count} replies).',
            'stats': {'total': len(all_comments), 'top_level': top_level_count, 'replies': reply_count}
        }
    except Exception as e:
        if all_comments:
            yield {'log': f'[WARNING] yt-dlp stream interrupted after {len(all_comments)} comments: {e}'}
        else:
            yield {'error': f'yt-dlp extraction failed: {e}'}
            return

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
