# YouTube Comment Extractor

A native GTK4/Libadwaita application for Linux that allows users to extract comments from YouTube videos. The application leverages `yt-dlp` to bypass YouTube API restrictions and provides various sampling strategies for efficient data extraction.

## Features

- **GTK4/Libadwaita UI**: Seamless integration with modern Linux desktops.
- **`yt-dlp` Integration**: Directly parses comments, avoiding YouTube Data API quotas or keys.
- **Advanced Sampling**: Support for uniform sampling, head-and-tail limits, and probabilistic sampling.
- **Cookies Support**: Pass `cookies.txt` to access restricted content.
- **CSV Export**: Extract results into a cleanly formatted CSV file.

## Installation

### Flatpak (Recommended)

1. Ensure Flatpak and `flatpak-builder` are installed on your system.
2. Build and install the application locally using the provided manifest:

```bash
flatpak-builder --user --install --force-clean build-dir io.github.antux912012.YTCommentExtractor.yml
```

3. Run the app:
```bash
flatpak run io.github.antux912012.YTCommentExtractor
```

### Web Service & System Tray Edition

The application also includes a dedicated local web server and system tray service styled with the Nord Palette.

#### 1. Flatpak Web Service
```bash
flatpak-builder --user --install --force-clean build-dir-service io.github.antux912012.YTCommentExtractor.Service.yml
flatpak run io.github.antux912012.YTCommentExtractor.Service
```

#### 2. Universal AppImage (Portable)
Download `YT-Comment-Extractor-Service.AppImage` from GitHub Releases and run:
```bash
chmod +x YT-Comment-Extractor-Service.AppImage
./YT-Comment-Extractor-Service.AppImage
```

Once launched, the service sits in your system tray and is accessible from any device on your local Wi-Fi:
- **mDNS Network Address**: `http://yt-extractor.local:5000`
- **Local Machine**: `http://127.0.0.1:5000`

### Local Development


To run the application locally without Flatpak:
1. Ensure **Python 3.10 or higher** is installed (Recommended: Python 3.11+), along with `gtk4`, `libadwaita`, and `python3-gi`.
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app using the start script:
   ```bash
   ./start.sh
   ```

## Usage

1. Paste a YouTube Video URL.
2. Select your sorting preference (Top comments or Newest first).
3. Choose a sampling strategy (All comments, Head/Tail limits, Random uniform).
4. Provide a `cookies.txt` if the video is age-restricted or private.
5. Click **Extract Comments**.
6. Review the logs and, once finished, click **Export to CSV**.

## Version

Current version: **0.4**

## Academic Research & PhD Thesis

The core algorithm for comment extraction and randomization implemented in this software constitutes a fundamental part of an ongoing PhD Thesis. 
Unlike standard API-based approaches, this tool utilizes a custom `yt-dlp` extraction pipeline designed to mitigate data truncation and API biases. 
Furthermore, the advanced randomization and sampling strategies were specifically engineered to provide statistically rigorous and unbiased datasets for academic research in social sciences and data analysis.

### Algorithmic Methodology: Unbiased Extraction

To ensure that the dataset is not subject to arbitrary truncation by external APIs, the extraction engine utilizes a streaming generator pattern built directly on `yt-dlp`. This design allows for continuous stream-processing of comments with full control over sorting (`top` vs `new`) and reply inclusion.

Crucially, the algorithm implements a strict de-biasing filter to separate top-level comments from nested discussion threads (replies). This prevents highly active, localized sub-conversations from skewing the overall dataset.

**Extraction Engine Code (`scraper.py`):**
```python
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
    # ... yt-dlp configuration and comment stream initialization ...

    for c in comment_stream:
        # 1. Stop Event Hook for controlled interruption
        if stop_event and stop_event.is_set():
            # ... abort logic ...
            return

        text = (c.get('text') or '').strip()
        if not text:
            continue

        cid = str(c.get('id') or c.get('cid') or '')
        parent = c.get('parent')
        # 2. De-biasing filter: Identify if the comment is a nested reply
        is_reply = (parent != 'root') if parent is not None else ('.' in cid)

        # 3. Exclude replies if requested to maintain a strict top-level pool
        if is_reply and not include_replies:
            continue

        # ... Accumulation and Metrics Tracking ...
```

### Algorithmic Methodology: Statistically Rigorous Sampling

Once the baseline pool of comments is extracted, the system applies predefined sampling strategies. These strategies determine how a representative subset is constructed from massive comment sections (often containing tens of thousands of comments).

The implementation relies on Python's cryptographically secure pseudo-random number generator (through `random.sample`) for uniform sampling, guaranteeing that every comment in the extracted pool has an equal probability of being selected.

**Randomization & Sampling Logic (`web_app.py` / `main_gtk.py`):**
```python
# Strategy 0: Full scan (All comments)
# Strategy 1: Unbiased Random Sample (Full pool)
# Strategy 2: Fast Random Sample (2,000 pool)
# Strategy 3: Sequential (First N)

# Apply sampling strategy
if strategy_idx in (1, 2) and sample_size > 0:
    if len(all_comments) > sample_size:
        extraction_state["logs"].append(
            f"[SAMPLE] Applying uniform random sampling: selecting {sample_size} from {len(all_comments)} comments."
        )
        # Uses random.sample for statistically rigorous, unbiased uniform sampling without replacement
        final_comments = random.sample(all_comments, sample_size)
    else:
        final_comments = all_comments
elif strategy_idx == 3 and sample_size > 0:
    # Sequential ordering for temporal analysis
    final_comments = all_comments[:sample_size]
else:
    # Exhaustive collection
    final_comments = all_comments
```

These methodological choices guarantee that datasets generated by this tool meet the stringent data provenance and bias-mitigation requirements expected in peer-reviewed scientific literature.

## License

This tool was born as a University Research Tool and is distributed under the GNU Affero General Public License (AGPL).
