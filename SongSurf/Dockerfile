# ── Stage 1: Build SvelteKit frontend ────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --frozen-lockfile
COPY frontend/ .
RUN npm run build

# ── Stage 2: Python server ────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="SongSurf"
LABEL description="YouTube Music downloader — yt-dlp + FFmpeg + Flask"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/home/songsurf/.local/bin:$PATH" \
    FRONTEND_BUILD_PATH=/app/frontend/build

# System deps: FFmpeg (audio conversion) + curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user + data directories in one layer
RUN useradd -m -u 1000 songsurf && \
    mkdir -p /app/logs /app/frontend/build /data/temp /data/music /data/plex_music && \
    chown -R songsurf:songsurf /app /data

WORKDIR /app

# Python deps (cached separately from app code)
COPY --chown=songsurf:songsurf server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY --chown=songsurf:songsurf server/ .

# SvelteKit build output
COPY --from=frontend-builder --chown=songsurf:songsurf /frontend/build /app/frontend/build

# Entrypoint (fix CRLF → LF in case of Windows checkout)
COPY --chown=songsurf:songsurf docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

USER songsurf

EXPOSE 8081

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${FLASK_PORT:-8081}/ping || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "app.py"]
