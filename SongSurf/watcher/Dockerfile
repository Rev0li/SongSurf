# Dockerfile — SongSurf Watcher
# Lightweight auth proxy, always running.
# Needs Docker socket access to start/stop the songsurf container.
# Runs as root intentionally (docker.sock requires it).

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY watcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watcher/watcher.py .
COPY templates/ templates/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping')" || exit 1

CMD ["python", "watcher.py"]
