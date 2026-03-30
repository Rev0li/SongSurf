# Dockerfile — SongSurf Watcher
# Portail d'authentification léger, toujours actif
# Accès au Docker socket pour démarrer/arrêter SongSurf

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dépendances Python
COPY watcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code du Watcher
COPY watcher/watcher.py .

# Templates : propres au watcher + login partagé avec SongSurf
# # Code du Watcher
COPY watcher/watcher.py .

# Templates (TOUT)
COPY templates/ templates/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping')" || exit 1

CMD ["python", "watcher.py"]
