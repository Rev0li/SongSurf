#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SongSurf — music download server

Auth model (portal gate, see docs/CONNECTOR.md):
  - Caddy asks the portal (forward_auth), then sends X-User-Name (pseudo),
    X-User-Role, X-User-Id (portal UUID, the storage key) + the proof X-Proxy-Token
  - SongSurf trusts these headers only if X-Proxy-Token matches
    SONGSURF_PROXY_SECRET (constant time); empty secret → locked
  - DEV_MODE=true → local admin dev user, no proof (never in production)

Storage: /data/music/<portal UUID>/Artist/Album/ (config.DEV_MODE: same, uid dev-user-local)
Persistent state (queue, quotas, ZIP exports): SQLite in /data/state (state_store.py)

Code layout: auth/ (identity), core/ (config, storage, queue, worker, tags), routes/ (blueprints).
"""

from flask import Flask, Response, jsonify, request
import os
import secrets
import signal
import threading

from waitress import serve
from core import config
from core.config import logger
from core.worker import _cleanup_temp_leftovers, _on_sigterm, _resume_pending_batch, queue_worker
from routes.download import download_bp
from routes.extension import extension_bp
from routes.library import library_bp
from routes.metadata import metadata_bp
from routes.admin import admin_bp
from routes.pages import pages_bp
from routes.zip import zip_bp

import events_client

# ── Configuration ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
# Taille max d'une requête entrante (pochettes, cookies, JSON) — limite technique,
# volontairement non paramétrable. Les téléchargements sortants ne sont pas concernés.
MAX_REQUEST_MB = 20
app.config['MAX_CONTENT_LENGTH'] = MAX_REQUEST_MB * 1024 * 1024

app.register_blueprint(download_bp)
app.register_blueprint(extension_bp)
app.register_blueprint(library_bp)
app.register_blueprint(metadata_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(zip_bp)
app.register_blueprint(pages_bp)


@app.before_request
def reject_oversized_request():
    # Refus avant la route : leurs try/except génériques transformeraient le 413
    # levé par request.get_json() en 500.
    if (request.content_length or 0) > app.config['MAX_CONTENT_LENGTH']:
        return request_too_large(None)


@app.errorhandler(413)
def request_too_large(_e):
    return jsonify({'success': False,
                    'error': f'Requête trop volumineuse (max {MAX_REQUEST_MB} Mo).'}), 413


# ── CORS (extension Chrome) ───────────────────────────────────────────────────

def _cors_headers(origin: str) -> dict:
    """En-têtes CORS, uniquement pour l'origine de l'extension SongSurf Clip."""
    if origin not in config._CORS_ORIGINS:
        return {}
    return {
        'Access-Control-Allow-Origin':      origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods':     'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers':     'Content-Type, Accept',
    }


@app.before_request
def cors_preflight():
    """Préflight CORS de toutes les routes (/api/preview, /api/queue-direct, /ping…) :
    204 pour l'extension, 403 pour toute autre origine."""
    if request.method != 'OPTIONS':
        return None
    hdrs = _cors_headers(request.headers.get('Origin', ''))
    if not hdrs:
        return Response(status=403)
    return Response(status=204, headers=hdrs)


@app.after_request
def add_cors(response):
    for k, v in _cors_headers(request.headers.get('Origin', '')).items():
        response.headers[k] = v
    return response


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    flask_port = int(os.getenv('FLASK_PORT', '8081'))
    if config.DEV_MODE:
        mode = "DEV (sans authentification)"
    elif config.SONGSURF_PROXY_SECRET:
        mode = "PRODUCTION (porte du portail)"
    else:
        mode = "LOCKED (SONGSURF_PROXY_SECRET absent)"

    logger.info(f"🎵 SongSurf démarré — port={flask_port}, mode={mode}, music={config.BASE_MUSIC_DIR}")
    events_client.start_replay_thread()
    # Nettoyage AVANT le worker : un titre repris de la file ne doit pas voir ses
    # fichiers temporaires supprimés en plein téléchargement.
    _cleanup_temp_leftovers()
    _resume_pending_batch()
    threading.Thread(target=queue_worker, daemon=True).start()
    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)
    # waitress : serveur de prod multi-thread, un seul process (l'état est global au process)
    serve(app, host='0.0.0.0', port=flask_port, threads=8)
