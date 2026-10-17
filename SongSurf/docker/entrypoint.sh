#!/bin/bash
# entrypoint.sh — SongSurf container startup
# yt-dlp est épinglé dans requirements.txt (plus de mise à jour au boot) :
# pour monter de version → `make bump-ytdlp` puis redéployer.
set -euo pipefail

echo "=============================================="
echo "SongSurf - starting container"
echo "=============================================="
echo "Python : $(python --version)"
echo "FFmpeg : $(ffmpeg -version 2>&1 | head -n1)"

echo "yt-dlp : $(yt-dlp --version 2>/dev/null || echo 'unknown')"

# Ensure data directories exist (bind-mount might not pre-create them)
mkdir -p /data/temp /data/music

echo "=============================================="
echo "Starting application..."
echo "=============================================="

exec "$@"
