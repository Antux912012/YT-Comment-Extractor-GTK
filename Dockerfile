# Production hardened Dockerfile for YouTube Comment Extractor Service
FROM python:3.12-slim

# Install system dependencies (ffmpeg, ca-certificates, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt Flask==3.0.0 werkzeug==3.0.0 zeroconf==0.131.0

# Copy application code
COPY scraper.py web_app.py ./
COPY templates/ ./templates/

# Run as non-privileged user (appuser:1000)
RUN useradd -u 1000 -m -s /bin/bash appuser && \
    mkdir -p /app/data /tmp/yt-extractor && \
    chown -R appuser:appuser /app /tmp/yt-extractor

USER appuser

EXPOSE 5000

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:5000/api/status || exit 1

ENTRYPOINT ["python", "web_app.py", "--lan"]
