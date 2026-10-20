import csv
import html
import io
import json
import re
from datetime import datetime, timezone

CSV_FIELDNAMES = [
    'Comment ID',
    'Author',
    'Channel ID',
    'Published Date',
    'Likes',
    'Is Reply',
    'Reply Count',
    'Comment Text'
]


def _format_comment_row(c):
    return [
        c.get('cid', ''),
        c.get('nickname', ''),
        c.get('channel_id', ''),
        c.get('date', ''),
        str(c.get('votes', '0')),
        'Yes' if c.get('is_reply', False) else 'No',
        c.get('reply_count', 0),
        c.get('comment', '')
    ]


def export_to_csv(comments, filepath=None):
    """
    Exports comments to CSV format.
    Uses 'utf-8-sig' encoding (UTF-8 with BOM) to guarantee that emoji symbols
    and international Unicode characters are rendered properly in Microsoft Excel,
    LibreOffice, and standard spreadsheet software across all platforms.
    """
    if filepath:
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(CSV_FIELDNAMES)
            for c in comments:
                writer.writerow(_format_comment_row(c))
        return None

    output = io.StringIO()
    writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_FIELDNAMES)
    for c in comments:
        writer.writerow(_format_comment_row(c))
    return output.getvalue().encode('utf-8-sig')


def export_to_json(comments, video_info=None, filepath=None):
    """
    Exports comments to JSON format.
    Uses ensure_ascii=False so emoji symbols and international characters are
    preserved directly as UTF-8 Unicode characters without \\uXXXX escapes.
    """
    info = video_info or {}
    data = {
        'metadata': {
            'video_id': info.get('video_id', ''),
            'video_title': info.get('title', ''),
            'video_url': info.get('video_url', ''),
            'channel': info.get('channel', ''),
            'exported_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            'total_comments': len(comments)
        },
        'comments': comments
    }
    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    if filepath:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_str)
        return None

    return json_str.encode('utf-8')


def _avatar_color(name):
    """Generates a deterministic HSL color based on author name, resembling YouTube avatars."""
    if not name:
        return 'hsl(200, 60%, 45%)'
    h = 0
    for char in name:
        h = (h * 31 + ord(char)) & 0xFFFFFFFF
    hue = h % 360
    return f'hsl({hue}, 65%, 42%)'


def _linkify_safe(escaped_text):
    """Safely converts URLs in already-escaped HTML text into clickable hyperlinks."""
    url_pattern = re.compile(r'(https?:\/\/[^\s<]+)')
    return url_pattern.sub(r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', escaped_text)


def export_to_html(comments, video_info=None, filepath=None):
    """
    Exports comments to a standalone HTML file styled authentically like YouTube's
    modern comment section (with dark theme default, light theme toggle, responsive layout,
    threaded replies, full emoji rendering, and real-time client-side search/filter).
    """
    info = video_info or {}
    video_title = info.get('title') or 'YouTube Comments Export'
    video_id = info.get('video_id') or ''
    video_url = info.get('video_url') or (f'https://www.youtube.com/watch?v={video_id}' if video_id else '')
    channel_name = info.get('channel') or ''
    export_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

    total_count = len(comments)
    top_level_count = sum(1 for c in comments if not c.get('is_reply', False))
    replies_count = total_count - top_level_count

    # Build threading map for replies
    top_level_comments = []
    replies_by_parent = {}
    cids = {c.get('cid') for c in comments if c.get('cid')}

    for c in comments:
        is_reply = c.get('is_reply', False)
        parent_id = c.get('parent_id')
        cid = c.get('cid', '')

        if not parent_id and is_reply and '.' in cid:
            parent_id = cid.split('.')[0]

        if is_reply and parent_id and parent_id in cids:
            replies_by_parent.setdefault(parent_id, []).append(c)
        else:
            top_level_comments.append(c)

    def render_single_comment(c, is_reply_view=False):
        cid = html.escape(str(c.get('cid') or ''))
        raw_author = c.get('nickname') or 'Anonymous'
        author = html.escape(raw_author)
        channel_id = html.escape(c.get('channel_id') or '')
        date_str = html.escape(c.get('date') or 'Unknown')
        likes_str = html.escape(str(c.get('votes', '0')))
        try:
            likes_num = int(c.get('votes', 0))
        except (ValueError, TypeError):
            likes_num = 0

        raw_text = c.get('comment') or ''
        escaped_text = html.escape(raw_text)
        formatted_text = _linkify_safe(escaped_text)

        reply_count_val = c.get('reply_count', 0)
        is_reply = c.get('is_reply', False)
        initial_letter = (raw_author.lstrip('@')[:1] or '?').upper()
        avatar_bg = _avatar_color(raw_author)
        avatar_url = c.get('author_thumbnail')

        avatar_img_html = ""
        if avatar_url:
            esc_avatar_url = html.escape(avatar_url)
            avatar_img_html = (
                f'<img class="avatar-img" src="{esc_avatar_url}" alt="{author}" '
                f'onerror="this.style.display=\'none\'; this.nextElementSibling.style.display=\'flex\';">'
            )
            fallback_display = 'style="display:none;"'
        else:
            fallback_display = 'style="display:flex;"'

        reply_badge = '<span class="reply-badge">Reply</span>' if (is_reply and not is_reply_view) else ''
        if channel_id:
            author_link_start = (
                f'<a href="https://www.youtube.com/channel/{channel_id}" '
                f'target="_blank" rel="noopener noreferrer" class="author-name">'
            )
            author_link_end = '</a>'
        else:
            author_link_start = '<span class="author-name">'
            author_link_end = '</span>'

        like_icon_path = (
            "M18.77,11h-4.23l1.52-4.94C16.38,5.03,15.54,4,14.38,4c-0.58,0-1.14,0.24-1.52,0.65L7,11H3v10h4h1h9.43"
            "c1.06,0,1.98-0.67,2.19-1.61l1.34-6C21.23,12.15,20.18,11,18.77,11z M7,20H4v-8h3V20z M19.98,13.17l-1.34,6"
            "C18.54,19.65,18.03,20,17.43,20H8v-8.61l5.6-6.06C13.79,5.12,14.08,5,14.38,5c0.26,0,0.5,0.11,0.63,0.3"
            "c0.07,0.1,0.15,0.26,0.09,0.47l-1.52,4.94L13.18,12h1.35h4.23c0.41,0,0.8,0.17,1.03,0.46"
            "C19.92,12.61,20.05,12.86,19.98,13.17z"
        )
        reply_count_html = (
            f'<span class="reply-count-badge">💬 {reply_count_val} replies</span>'
            if (reply_count_val > 0 and not is_reply_view) else ''
        )

        reply_cls = 'yt-reply-comment' if is_reply_view else ''
        author_lower = author.lower()
        text_lower = escaped_text.lower()
        dislike_icon = (
            f'<svg viewBox="0 0 24 24" class="action-icon">'
            f'<path d="{like_icon_path}" transform="rotate(180 12 12)"/></svg>'
        )
        avatar_fallback_html = (
            f'<div class="avatar-fallback" {fallback_display} style="background-color: {avatar_bg};">'
            f'{initial_letter}</div>'
        )

        return f'''
        <div class="yt-comment {reply_cls}" data-cid="{cid}" data-likes="{likes_num}"
             data-author="{author_lower}" data-text="{text_lower}">
            <div class="avatar-col">
                <div class="avatar-wrap">
                    {avatar_img_html}
                    {avatar_fallback_html}
                </div>
            </div>
            <div class="content-col">
                <div class="comment-header">
                    {author_link_start}{author}{author_link_end}
                    <span class="comment-date">{date_str}</span>
                    {reply_badge}
                </div>
                <div class="comment-body">{formatted_text}</div>
                <div class="comment-actions">
                    <span class="action-btn like-btn" title="Likes">
                        <svg viewBox="0 0 24 24" class="action-icon"><path d="{like_icon_path}"/></svg>
                        <span class="likes-count">{likes_str}</span>
                    </span>
                    <span class="action-btn" title="Dislike">
                        {dislike_icon}
                    </span>
                    {reply_count_html}
                </div>
            </div>
        </div>
        '''

    rendered_threads = []
    for c in top_level_comments:
        parent_cid = c.get('cid', '')
        parent_html = render_single_comment(c, is_reply_view=False)
        child_replies = replies_by_parent.get(parent_cid, [])

        if child_replies:
            replies_html_list = [render_single_comment(rep, is_reply_view=True) for rep in child_replies]
            replies_html = f'''
            <div class="replies-wrapper">
                <button class="toggle-replies-btn" onclick="toggleReplies(this)">
                    <span class="arrow">▼</span> Show {len(child_replies)} replies
                </button>
                <div class="replies-thread open">
                    {''.join(replies_html_list)}
                </div>
            </div>
            '''
        else:
            replies_html = ''

        rendered_threads.append(f'<div class="yt-comment-thread">{parent_html}{replies_html}</div>')

    if rendered_threads:
        threads_content = ''.join(rendered_threads)
    else:
        threads_content = '<div class="no-comments">No comments found in this export dataset.</div>'

    yt_logo_path = (
        "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 "
        "3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 "
        "9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814z"
        "M9.545 15.568V8.432L15.818 12l-6.273 3.568z"
    )
    if video_url:
        video_title_html = (
            f'<a class="yt-video-title" href="{html.escape(video_url)}" '
            f'target="_blank" rel="noopener noreferrer">{html.escape(video_title)}</a>'
        )
    else:
        video_title_html = f'<span class="yt-video-title">{html.escape(video_title)}</span>'

    channel_meta_html = (
        f'<div style="font-size:13px; color:var(--text-secondary); margin-top:2px;">'
        f'Channel: {html.escape(channel_name)}</div>'
        if channel_name else ''
    )

    html_content = f'''<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(video_title)} - Comments</title>
    <style>
        :root {{
            --bg-base: #0f0f0f;
            --bg-surface: #181818;
            --bg-elevated: #222222;
            --text-primary: #f1f1f1;
            --text-secondary: #aaaaaa;
            --text-muted: #717171;
            --accent-blue: #3ea6ff;
            --border-color: #272727;
            --hover-overlay: rgba(255, 255, 255, 0.08);
            --pill-bg: #272727;
            --font-family: "Roboto", "YouTube Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
        }}

        [data-theme="light"] {{
            --bg-base: #f9f9f9;
            --bg-surface: #ffffff;
            --bg-elevated: #f2f2f2;
            --text-primary: #0f0f0f;
            --text-secondary: #606060;
            --text-muted: #909090;
            --accent-blue: #065fd4;
            --border-color: #e5e5e5;
            --hover-overlay: rgba(0, 0, 0, 0.05);
            --pill-bg: #e5e5e5;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-family);
            line-height: 1.5;
            padding: 24px 16px;
            display: flex;
            justify-content: center;
        }}

        .container {{
            width: 100%;
            max-width: 900px;
        }}

        /* Header Card */
        .yt-header {{
            background: var(--bg-surface);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}

        .yt-title-row {{
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 12px;
        }}

        .yt-logo {{
            flex-shrink: 0;
        }}

        .yt-video-title {{
            font-size: 20px;
            font-weight: 600;
            color: var(--text-primary);
            text-decoration: none;
            display: inline-block;
        }}
        .yt-video-title:hover {{
            color: var(--accent-blue);
        }}

        .yt-meta-row {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            color: var(--text-secondary);
            font-size: 13px;
            padding-top: 12px;
            border-top: 1px solid var(--border-color);
        }}

        .stats-badges {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}

        .badge {{
            background: var(--pill-bg);
            color: var(--text-primary);
            padding: 4px 12px;
            border-radius: 16px;
            font-weight: 500;
            font-size: 12px;
        }}

        .theme-toggle-btn {{
            background: var(--pill-bg);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            padding: 6px 14px;
            border-radius: 18px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            transition: background 0.2s;
        }}
        .theme-toggle-btn:hover {{
            background: var(--hover-overlay);
        }}

        /* Search and Controls Bar */
        .controls-bar {{
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}

        .search-box {{
            flex: 1;
            min-width: 240px;
            position: relative;
        }}

        .search-input {{
            width: 100%;
            padding: 10px 14px;
            background: var(--bg-surface);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            border-radius: 20px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }}
        .search-input:focus {{
            border-color: var(--accent-blue);
        }}

        .sort-select {{
            padding: 8px 14px;
            background: var(--bg-surface);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
            outline: none;
            cursor: pointer;
        }}

        /* Comments List */
        .comments-section {{
            display: flex;
            flex-direction: column;
            gap: 18px;
        }}

        .yt-comment-thread {{
            background: var(--bg-surface);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 16px;
            transition: background 0.15s;
        }}

        .yt-comment {{
            display: flex;
            gap: 14px;
        }}

        .avatar-col {{
            flex-shrink: 0;
        }}

        .avatar-wrap {{
            width: 40px;
            height: 40px;
            position: relative;
            border-radius: 50%;
            overflow: hidden;
        }}

        .avatar-img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 50%;
        }}

        .avatar-fallback {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-weight: 700;
            font-size: 16px;
            border-radius: 50%;
            user-select: none;
        }}

        .content-col {{
            flex: 1;
            min-width: 0;
        }}

        .comment-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
            flex-wrap: wrap;
        }}

        .author-name {{
            font-weight: 500;
            font-size: 13px;
            color: var(--text-primary);
            text-decoration: none;
        }}
        a.author-name:hover {{
            color: var(--accent-blue);
        }}

        .comment-date {{
            color: var(--text-muted);
            font-size: 12px;
        }}

        .reply-badge {{
            background: rgba(62, 166, 255, 0.15);
            color: var(--accent-blue);
            padding: 1px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        }}

        .comment-body {{
            font-size: 14px;
            color: var(--text-primary);
            white-space: pre-wrap;
            word-break: break-word;
            margin-bottom: 8px;
            line-height: 1.45;
        }}

        .comment-body a {{
            color: var(--accent-blue);
            text-decoration: none;
        }}
        .comment-body a:hover {{
            text-decoration: underline;
        }}

        .comment-actions {{
            display: flex;
            align-items: center;
            gap: 16px;
            font-size: 12px;
            color: var(--text-secondary);
        }}

        .action-btn {{
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            padding: 4px 6px;
            border-radius: 12px;
            user-select: none;
        }}
        .action-btn:hover {{
            background: var(--hover-overlay);
        }}

        .action-icon {{
            width: 15px;
            height: 15px;
            fill: currentColor;
        }}

        .reply-count-badge {{
            color: var(--text-muted);
            font-size: 12px;
        }}

        /* Replies Section */
        .replies-wrapper {{
            margin-top: 12px;
            margin-left: 48px;
            border-left: 2px solid var(--border-color);
            padding-left: 14px;
        }}

        .toggle-replies-btn {{
            background: transparent;
            border: none;
            color: var(--accent-blue);
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 4px 8px;
            border-radius: 16px;
            margin-bottom: 10px;
        }}
        .toggle-replies-btn:hover {{
            background: var(--hover-overlay);
        }}

        .replies-thread {{
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .replies-thread.collapsed {{
            display: none;
        }}

        .yt-reply-comment .avatar-wrap {{
            width: 28px;
            height: 28px;
        }}
        .yt-reply-comment .avatar-fallback {{
            font-size: 13px;
        }}
        .yt-reply-comment .comment-body {{
            font-size: 13px;
        }}

        .no-comments {{
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
            font-size: 16px;
        }}

        @media (max-width: 600px) {{
            .replies-wrapper {{
                margin-left: 18px;
                padding-left: 10px;
            }}
            .yt-video-title {{
                font-size: 16px;
            }}
        }}
    </style>
</head>
<body>

<div class="container">
    <div class="yt-header">
        <div class="yt-title-row">
            <svg class="yt-logo" viewBox="0 0 24 24" width="32" height="32" fill="#FF0000">
                <path d="{yt_logo_path}"/>
            </svg>
            <div>
                {video_title_html}
                {channel_meta_html}
            </div>
        </div>

        <div class="yt-meta-row">
            <div class="stats-badges">
                <span class="badge">📊 {total_count} Comments</span>
                <span class="badge">💬 {top_level_count} Top-Level</span>
                <span class="badge">↳ {replies_count} Replies</span>
                <span class="badge">📅 {export_time}</span>
            </div>
            <button class="theme-toggle-btn" id="themeToggleBtn" onclick="toggleTheme()">☀️ Light Theme</button>
        </div>
    </div>

    <div class="controls-bar">
        <div class="search-box">
            <input type="text" id="searchInput" class="search-input"
                   placeholder="🔍 Search comments by keyword or author..." oninput="filterComments()">
        </div>
        <select id="sortSelect" class="sort-select" onchange="sortComments()">
            <option value="original">Original Order</option>
            <option value="likes">Most Liked First</option>
        </select>
    </div>

    <div class="comments-section" id="commentsSection">
        {threads_content}
    </div>
</div>

<script>
    function toggleTheme() {{
        const htmlEl = document.documentElement;
        const btn = document.getElementById('themeToggleBtn');
        if (htmlEl.getAttribute('data-theme') === 'dark') {{
            htmlEl.setAttribute('data-theme', 'light');
            btn.textContent = '🌙 Dark Theme';
        }} else {{
            htmlEl.setAttribute('data-theme', 'dark');
            btn.textContent = '☀️ Light Theme';
        }}
    }}

    function toggleReplies(btn) {{
        const thread = btn.nextElementSibling;
        const arrow = btn.querySelector('.arrow');
        if (thread.classList.contains('collapsed')) {{
            thread.classList.remove('collapsed');
            arrow.textContent = '▼';
        }} else {{
            thread.classList.add('collapsed');
            arrow.textContent = '▶';
        }}
    }}

    function filterComments() {{
        const query = document.getElementById('searchInput').value.trim().toLowerCase();
        const threads = document.querySelectorAll('.yt-comment-thread');

        threads.forEach(thread => {{
            const comments = thread.querySelectorAll('.yt-comment');
            let match = false;
            comments.forEach(c => {{
                const author = c.getAttribute('data-author') || '';
                const text = c.getAttribute('data-text') || '';
                if (author.includes(query) || text.includes(query)) {{
                    match = true;
                }}
            }});
            thread.style.display = match ? '' : 'none';
        }});
    }}

    function sortComments() {{
        const sortVal = document.getElementById('sortSelect').value;
        const section = document.getElementById('commentsSection');
        const threads = Array.from(section.querySelectorAll('.yt-comment-thread'));

        if (sortVal === 'likes') {{
            threads.sort((a, b) => {{
                const aLikes = parseInt(a.querySelector('.yt-comment')?.getAttribute('data-likes') || '0', 10);
                const bLikes = parseInt(b.querySelector('.yt-comment')?.getAttribute('data-likes') || '0', 10);
                return bLikes - aLikes;
            }});
        }} else {{
            threads.sort((a, b) => {{
                return (a._origOrder || 0) - (b._origOrder || 0);
            }});
        }}

        threads.forEach(t => section.appendChild(t));
    }}

    document.addEventListener('DOMContentLoaded', () => {{
        const threads = document.querySelectorAll('.yt-comment-thread');
        threads.forEach((t, idx) => {{
            t._origOrder = idx;
        }});
    }});
</script>
</body>
</html>
'''
    if filepath:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return None

    return html_content.encode('utf-8')
