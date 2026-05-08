#!/bin/bash
# entrypoint.sh — SongSurf container startup
# Updates yt-dlp before launch to stay compatible with YouTube changes.
set -euo pipefail

echo "=============================================="
echo "SongSurf - starting container"
echo "=============================================="
echo "Python : $(python --version)"
echo "FFmpeg : $(ffmpeg -version 2>&1 | head -n1)"

# yt-dlp is installed as the songsurf user (--user), so it lands in
# ~/.local/lib/... which is writable. PATH already includes ~/.local/bin.
echo "Updating yt-dlp..."
if pip install --user --no-cache-dir --upgrade yt-dlp 2>&1; then
    echo "yt-dlp $(yt-dlp --version)"
else
    echo "WARNING: yt-dlp update failed — running existing version: $(yt-dlp --version 2>/dev/null || echo 'unknown')"
fi

# Ensure data directories exist (bind-mount might not pre-create them)
mkdir -p /data/temp /data/music /data/plex_music

echo "=============================================="
echo "Starting application..."
echo "=============================================="

exec "$@"
