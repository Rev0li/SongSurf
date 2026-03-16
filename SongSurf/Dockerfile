# Dockerfile - SongSurf Bot Music
# Basé sur Python 3.11 slim pour un conteneur léger

FROM python:3.11-slim

# Métadonnées
LABEL maintainer="SongSurf"
LABEL description="Bot de téléchargement de musique YouTube avec yt-dlp"
LABEL version="1.0"

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Créer un utilisateur non-root pour la sécurité
RUN useradd -m -u 1000 songsurf && \
    mkdir -p /app /data/temp /data/music /data/music_guest /data/temp_guest /data/plex_music && \
    chown -R songsurf:songsurf /app /data

# Installer les dépendances système (FFmpeg + outils)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Définir le répertoire de travail
WORKDIR /app

# Copier le requirements.txt en premier (pour cache Docker)
COPY --chown=songsurf:songsurf python-server/requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY --chown=songsurf:songsurf python-server/ .

# Copier le script entrypoint
COPY --chown=songsurf:songsurf docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Changer vers l'utilisateur non-root
USER songsurf

# Exposer le port du serveur Flask
EXPOSE 8080

# Volumes pour persistance des données
VOLUME ["/data/temp", "/data/music"]

# Healthcheck pour vérifier que le serveur répond
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# Point d'entrée qui met à jour yt-dlp avant de démarrer
ENTRYPOINT ["/entrypoint.sh"]

# Commande par défaut
CMD ["python", "app.py"]
