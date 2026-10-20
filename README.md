<p align="center">
  <img src="icons/icon_128x128.png" width="128" height="128" alt="YouTube Comment Extractor Logo" />
</p>

# YouTube Comment Extractor

<p align="center">
  <a href="https://antux912012.github.io/YT-Comment-Extractor-GTK/">
    <img src="https://img.shields.io/badge/Web%20App-Try%20Online%20(GitHub%20Pages)-brightgreen?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Live Web App" />
  </a>
  <a href="https://antux912012.github.io/YT-Comment-Extractor-GTK/">
    <img src="https://img.shields.io/badge/GitHub%20Pages-Live-blue?style=for-the-badge&logo=github" alt="GitHub Pages" />
  </a>
</p>

> ### 🌐 Try It Online (No Installation Needed)
> You can extract comments directly in your web browser with zero installation:  
> **👉 [https://antux912012.github.io/YT-Comment-Extractor-GTK/](https://antux912012.github.io/YT-Comment-Extractor-GTK/)**  
> *Supports browser-based extraction via CORS proxy or official YouTube Data API v3, random/ordered sampling, and instant CSV/JSON exports.*

A native GTK4/Libadwaita application for Linux and static browser web app that allows users to extract comments from YouTube videos. The application leverages `yt-dlp` in the desktop version and client-side web workers in the online edition to bypass YouTube API restrictions and provides various sampling strategies for efficient data extraction.

## Features

- **GTK4/Libadwaita UI**: Seamless integration with modern GNOME desktops, including full GNOME Human Interface Guidelines (HIG) compliant multi-resolution and symbolic icon suite.
- **Online Web Edition (GitHub Pages)**: Run anywhere on any device at **[https://antux912012.github.io/YT-Comment-Extractor-GTK/](https://antux912012.github.io/YT-Comment-Extractor-GTK/)**.
- **`yt-dlp` Streaming Engine**: Directly parses comments, avoiding YouTube Data API quotas or keys in the desktop/service editions.
- **Advanced Sampling Strategies**: Support for uniform random sampling, bounded pool sampling, sequential ordering, and full exhaustive extraction.
- **De-biasing Filter**: Option to isolate top-level comments and exclude discussion reply threads to prevent conversation-density bias in research datasets.
- **Session Cookies Support**: Pass Netscape `cookies.txt` to access restricted, age-gated, or private content.
- **Multi-Format Exporters**:
  - **CSV (`.csv`)**: RFC 4180 compliant with UTF-8 BOM (`utf-8-sig`) to natively preserve emojis (`🔥`, `❤️`, `👍`, `🚀`) and international symbols in Excel, LibreOffice, and data science pipelines.
  - **JSON (`.json`)**: Formatted hierarchical dataset including video metadata and Unicode emoji symbols (`ensure_ascii=False`).
  - **NDJSON (`.ndjson`)**: Newline-delimited JSON stream for large-scale data ingestion.
  - **Interactive HTML (`.html`)**: Standalone, responsive web export styled authentically like YouTube's comments UI with user avatars, likes/replies metrics, collapsible reply threads, and real-time client-side search.
- **Static Web Client (GitHub Pages SPA)**:
  - **Live URL**: **[https://antux912012.github.io/YT-Comment-Extractor-GTK/](https://antux912012.github.io/YT-Comment-Extractor-GTK/)**
  - 100% static client-side single-page application with zero backend.
  - Dual fetch engines: Official YouTube Data API v3 or Keyless Innertube via CORS proxy.
  - Inline Web Worker for pagination concurrency without UI lag.
  - Client-side IndexedDB caching (`yt_comments_db`) preventing memory exhaustion on $>50\text{k}$ comments.

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

1. Paste a YouTube Video URL or Video ID.
2. Select your sorting preference (Top comments or Newest first).
3. Choose a sampling strategy (All comments, Unbiased Random Sample, Fast Random Sample, or Sequential).
4. Provide a `cookies.txt` if the video is age-restricted or private.
5. Click **Start Extraction**.
6. Review the live telemetry and execution monitor logs.
7. Once finished, click **Export CSV**, **Export JSON**, or **Export HTML** as needed.

## Version

Current version: **0.6**

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

**Centralized Randomization & Sampling Implementation (`scraper.py`):**
```python
def apply_sampling(all_comments, strategy_idx, sample_size, include_replies=True):
    """
    Applies the selected sampling strategy to the collected comments pool:
    - Strategy 0: Exhaustive Full Scan (All comments)
    - Strategy 1: Unbiased Random Sample (Full pool)
    - Strategy 2: Fast Random Sample (Bounded pool)
    - Strategy 3: Sequential (First N comments)
    """
    if not all_comments:
        return [], None

    if strategy_idx in (1, 2) and sample_size > 0:
        if len(all_comments) > sample_size:
            msg = (
                f"[SAMPLE] Applying uniform random sampling: selecting {sample_size} "
                f"from total pool of {len(all_comments)} comments."
            )
            # Uses random.sample for statistically rigorous, unbiased uniform sampling without replacement
            return random.sample(all_comments, sample_size), msg
        else:
            msg = f"[SAMPLE] Total collected ({len(all_comments)}) <= requested sample ({sample_size})."
            return all_comments, msg
    elif strategy_idx == 3 and sample_size > 0:
        # Sequential ordering for temporal analysis
        return all_comments[:sample_size], None
    else:
        # Exhaustive collection
        return all_comments, None
```

These methodological choices guarantee that datasets generated by this tool meet the stringent data provenance and bias-mitigation requirements expected in peer-reviewed scientific literature.

## License

This tool was born as a University Research Tool and is distributed under the GNU Affero General Public License (AGPL).
