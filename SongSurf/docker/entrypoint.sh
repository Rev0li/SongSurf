#!/bin/bash
# entrypoint.sh - Point d'entrée du conteneur SongSurf
# Met à jour yt-dlp avant chaque démarrage pour garantir la compatibilité YouTube

echo "=============================================="
echo "🎵 SongSurf - Démarrage du conteneur"
echo "=============================================="

echo "📦 Python: $(python --version)"
echo "🎬 FFmpeg: $(ffmpeg -version 2>&1 | head -n1)"

# Mise à jour de yt-dlp (non-bloquante si pas d'internet)
echo ""
echo "🔄 Mise à jour de yt-dlp..."
if pip install --no-cache-dir --upgrade yt-dlp 2>&1; then
    echo "✅ yt-dlp mis à jour: $(yt-dlp --version)"
else
    echo "⚠️  Mise à jour échouée (pas d'accès internet ?)"
    echo "   → Utilisation de la version existante: $(yt-dlp --version)"
fi

# Vérifier les dossiers
mkdir -p /data/temp /data/music 2>/dev/null || true

echo ""
echo "=============================================="
echo "🚀 Démarrage de l'application..."
echo "=============================================="
echo ""

exec "$@"
