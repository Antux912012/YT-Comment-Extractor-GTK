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

Current version: **0.2ac**

## Academic Research & PhD Thesis

The core algorithm for comment extraction and randomization implemented in this software constitutes a fundamental part of an ongoing PhD Thesis. 
Unlike standard API-based approaches, this tool utilizes a custom extraction pipeline designed to mitigate data truncation and API biases by parsing comments directly via `yt-dlp`. 
Furthermore, the advanced randomization and sampling strategies (such as probabilistic uniform sampling and deep-scan head-and-tail limits) were specifically engineered to provide statistically rigorous and unbiased datasets for academic research in social sciences and data analysis.

## License

This tool was born as a University Research Tool and is distributed under the GNU Affero General Public License (AGPL).
