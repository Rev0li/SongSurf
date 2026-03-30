FROM python:3.11-slim

LABEL maintainer="SongSurf"
LABEL description="Bot de téléchargement de musique YouTube avec yt-dlp"
LABEL version="1.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Créer un utilisateur non-root pour la sécurité
RUN useradd -m -u 1000 songsurf && \
    mkdir -p /app /data/temp /data/music /data/music_guest /data/temp_guest /data/plex_music && \
    chown -R songsurf:songsurf /app /data

# ✅ CORRECTION : Créer le dossier logs avec les bonnes permissions
RUN mkdir -p /app/logs && chown -R songsurf:songsurf /app/logs

# Installer les dépendances système (FFmpeg + outils)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Copier le requirements.txt en premier (pour cache Docker)
COPY --chown=songsurf:songsurf server/requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY --chown=songsurf:songsurf server/ .

# Copier le script entrypoint (sed corrige les fins de ligne CRLF → LF au cas où)
COPY --chown=songsurf:songsurf docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

# Changer vers l'utilisateur non-root
USER songsurf

# Exposer le port du serveur Flask
EXPOSE 8080

# Volumes pour persistance des données
VOLUME ["/data/temp", "/data/music"]

# Healthcheck pour vérifier que le serveur répond
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${FLASK_PORT:-8080}/ping || exit 1

# Point d'entrée qui met à jour yt-dlp avant de démarrer
ENTRYPOINT ["/entrypoint.sh"]

# Commande par défaut
CMD ["python", "app.py"]
