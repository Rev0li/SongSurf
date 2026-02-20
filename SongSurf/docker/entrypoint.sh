#!/bin/bash
# entrypoint.sh - Point d'entrée du conteneur SongSurf
# Met à jour yt-dlp avant chaque démarrage pour garantir la compatibilité YouTube

echo "=============================================="
echo "🎵 SongSurf - Démarrage du conteneur"
echo "=============================================="

echo "📦 Python: $(python --version)"
echo "🎬 FFmpeg: $(ffmpeg -version 2>&1 | head -n1)"

# Ajoute ça juste avant le pip install pour voir ce qui bloque
echo "🔍 Diagnostic réseau..."
curl -v https://pypi.org/simple/ 2>&1 | head -30
nslookup pypi.org 2>&1 || echo "nslookup non dispo"

echo "🔄 Mise à jour de yt-dlp..."
if pip install \
    --no-cache-dir \
    --upgrade \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org \
    yt-dlp 2>&1; then
    echo "✅ yt-dlp mis à jour: $(yt-dlp --version)"
else
    echo "⚠️  Mise à jour échouée - version existante: $(yt-dlp --version)"
fi

# Vérifier les dossiers
mkdir -p /data/temp /data/music 2>/dev/null || true

echo ""
echo "=============================================="
echo "🚀 Démarrage de l'application..."
echo "=============================================="
echo ""

exec "$@"
