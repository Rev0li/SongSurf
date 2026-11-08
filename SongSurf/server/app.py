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

Phase 3: see docs/CONNECTOR.md
"""

from flask import (Flask, request, jsonify, send_file, send_from_directory, Response, abort,
                   redirect)
from pathlib import Path
from datetime import datetime
import signal
import threading
import os
import secrets
import shutil
import zipfile

from waitress import serve
from auth.provider import auth_required, get_current_user
from core import config, queue
from core.config import logger
from core.storage import _user_key, _user_music_dir, _user_pseudo
from core.worker import _cleanup_temp_leftovers, _on_sigterm, _resume_pending_batch, queue_worker
from routes.download import download_bp
from routes.extension import extension_bp
from routes.library import library_bp
from routes.metadata import metadata_bp
from routes.admin import admin_bp

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


# ── Logout ────────────────────────────────────────────────────────────────────

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """La session est celle du portail (pas de cookie ici) : retour au portail."""
    return redirect(config.REVAUTH_HOME_URL or '/')


# ── SPA ───────────────────────────────────────────────────────────────────────

# In Docker: FRONTEND_BUILD_PATH=/app/frontend/build (set in Dockerfile).
# In local dev: falls back to sibling of server/ directory.
_FRONTEND_BUILD = Path(
    os.environ.get('FRONTEND_BUILD_PATH') or
    str(Path(__file__).parent.parent / 'frontend' / 'build')
).resolve()


def _spa():
    """Serve the SvelteKit SPA index.html (requires auth)."""
    index = _FRONTEND_BUILD / 'index.html'
    if index.exists():
        resp = send_file(index)
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    return 'Frontend not built. Run: make build', 503


@app.route('/')
@auth_required
def dashboard():
    return _spa()


# Pages de l'appli (SSF-13) : un rechargement (ou « tirer pour rafraîchir » sur
# mobile) sur /library doit rendre l'appli, pas un 404. /metadata = ancienne
# adresse, redirigée côté client vers /library.
@app.route('/library')
@app.route('/metadata')
@auth_required
def spa_pages():
    return _spa()


@app.route('/_app/<path:filename>')
def svelte_assets(filename):
    """Serve SvelteKit's generated JS/CSS bundles (no auth needed)."""
    return send_from_directory(_FRONTEND_BUILD / '_app', filename)


@app.route('/<path:filename>')
def static_assets(filename):
    """Serve top-level static files copied from SvelteKit's static/ dir
    (fonts, help/ tutorial images, favicon…). Public assets — no auth.
    Only real files are served; unknown paths 404 (SPA pages have their own
    routes above: /, /library, /metadata). This catch-all is the least specific rule, so explicit API /
    asset routes always win."""
    target = (_FRONTEND_BUILD / filename).resolve()
    if not target.is_relative_to(_FRONTEND_BUILD) or not target.is_file():
        abort(404)
    return send_from_directory(_FRONTEND_BUILD, filename)


# ── User identity ──────────────────────────────────────────────────────────────

@app.route('/api/me')
@auth_required
def api_me():
    user = get_current_user()
    return jsonify({**user, 'pseudo': _user_pseudo(user)})


# ── Health ─────────────────────────────────────────────────────────────────────

@app.route('/ping')
def ping():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


# ── ZIP ────────────────────────────────────────────────────────────────────────
# Export en arrière-plan (SSF-03) : /api/prepare-zip lance la construction et répond
# tout de suite, le frontend suit l'avancement via /api/zip-status puis télécharge
# /api/download-zip. L'état vit dans SQLite : un ZIP prêt survit à un redémarrage,
# un ZIP interrompu est signalé (state_store._recover).

ZIP_DISABLED_MSG = "Export ZIP désactivé pour cette bibliothèque."
_zip_start_lock  = threading.Lock()   # une seule construction à la fois par utilisateur


def _zip_forbidden(user: dict, music_dir: Path) -> bool:
    """Export ZIP refusé pour la bibliothèque admin, qui est permanente (décision SSF-10).

    Vérifié sur le rôle ET sur le dossier : l'export vide la bibliothèque après le
    téléchargement, il ne doit jamais viser la racine musique ni un point de montage
    (la bibliothèque admin est la musique Jellyfin montée dans /data/music/<uid>).
    """
    if user.get('role') == 'admin':
        return True
    target = music_dir.resolve()
    return target == config.BASE_MUSIC_DIR.resolve() or _is_mount_point(target)


def _is_mount_point(path: Path) -> bool:
    """os.path.ismount ne voit pas un bind mount venant du même disque (cas du NAS) :
    on consulte aussi la table des montages du conteneur."""
    if os.path.ismount(path):
        return True
    try:
        with open('/proc/self/mountinfo', encoding='utf-8') as f:
            points = {line.split()[4].encode().decode('unicode_escape') for line in f}
    except OSError:
        return False
    return str(path) in points


def _zip_path(user_key: str) -> Path:
    return config.TEMP_DIR / f"songsurf_{user_key}.zip"


def _zip_public(state: dict | None) -> dict:
    """État ZIP renvoyé au frontend (jamais le chemin sur le serveur)."""
    if not state:
        return {'status': 'idle'}
    out = {
        'status':  state['status'],
        'done':    state['done'],
        'total':   state['total'],
        'count':   state['total'],
        'size_mb': state['size_mb'],
    }
    if state['status'] == 'error':
        out['error'] = state['error']
    if state['status'] == 'ready':
        out['download_url'] = '/api/download-zip'
    return out


def _build_zip(user_key: str, music_dir: Path, files: list, zip_path: Path) -> None:
    """Thread : écrit le ZIP dans un .part puis le renomme, en publiant l'avancement."""
    part = zip_path.with_name(zip_path.name + '.part')
    try:
        with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, f in enumerate(files, 1):
                if f.is_file():  # déplacé/supprimé pendant la construction → ignoré
                    zf.write(f, f.relative_to(music_dir))
                if i % 5 == 0 or i == len(files):
                    queue.store.zip_set(user_key, status='building', done=i)
        part.replace(zip_path)
        size_mb = round(zip_path.stat().st_size / (1024 * 1024), 1)
        queue.store.zip_set(user_key, status='ready', done=len(files), size_mb=size_mb)
        logger.info(f"📦 ZIP prêt: {len(files)} fichiers, {size_mb:.1f} MB [{user_key[:8]}]")
    except Exception as e:
        part.unlink(missing_ok=True)
        queue.store.zip_set(user_key, status='error', error=str(e))
        logger.error(f"❌ Construction ZIP [{user_key[:8]}]: {e}")


@app.route('/api/prepare-zip', methods=['POST'])
@auth_required
def prepare_zip():
    try:
        user      = get_current_user()
        key       = _user_key(user)
        music_dir = _user_music_dir(user)
        if _zip_forbidden(user, music_dir):
            return jsonify({'success': False, 'error': ZIP_DISABLED_MSG, 'code': 'zip_disabled'}), 403
        with _zip_start_lock:
            current = queue.store.zip_get(key)
            if current and current['status'] == 'building':
                return jsonify({'success': True, **_zip_public(current)}), 202
            files = sorted([p for p in music_dir.rglob('*.mp3') if p.is_file()],
                           key=lambda p: p.stat().st_mtime, reverse=True)
            if not files:
                return jsonify({'success': False, 'error': 'Aucune musique disponible'}), 404
            zip_path = _zip_path(key)
            zip_path.unlink(missing_ok=True)
            queue.store.zip_set(key, status='building', zip_path=str(zip_path),
                          done=0, total=len(files), size_mb=0, error='')
        threading.Thread(target=_build_zip, args=(key, music_dir, files, zip_path),
                         daemon=True).start()
        return jsonify({'success': True, **_zip_public(queue.store.zip_get(key))}), 202
    except Exception as e:
        logger.error(f"❌ /api/prepare-zip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/zip-status')
@auth_required
def zip_status():
    """Avancement de l'export ZIP de l'appelant : idle | building | ready | error."""
    key   = _user_key(get_current_user())
    state = queue.store.zip_get(key)
    if state and state['status'] == 'ready' and not Path(state['zip_path']).is_file():
        queue.store.zip_delete(key)   # fichier disparu (config.TEMP_DIR nettoyé) → plus rien à récupérer
        state = None
    return jsonify({'success': True, **_zip_public(state)})


@app.route('/api/download-zip')
@auth_required
def download_zip():
    user      = get_current_user()
    key       = _user_key(user)
    music_dir = _user_music_dir(user)
    if _zip_forbidden(user, music_dir):
        return jsonify({'success': False, 'error': ZIP_DISABLED_MSG, 'code': 'zip_disabled'}), 403
    state = queue.store.zip_get(key)
    if not state or state['status'] != 'ready':
        return jsonify({'success': False, 'error': 'ZIP non prêt, utilisez /api/prepare-zip'}), 404

    zip_path = Path(state['zip_path'])
    if not zip_path.exists():
        return jsonify({'success': False, 'error': 'ZIP introuvable'}), 404

    _pseudo   = _user_pseudo(user)
    _role     = user.get('role', '')
    _zip_meta = {'count': state['total'], 'size_mb': state['size_mb']}
    file_size = zip_path.stat().st_size

    def _after_full_export():
        try:
            zip_path.unlink(missing_ok=True)
            queue.store.zip_delete(key)
            # Bibliothèque membre = temporaire, supprimée après export. Jamais le
            # dossier admin ni la racine : refusés en amont, revérifiés ici (SSF-10).
            purged = not _zip_forbidden(user, music_dir) and music_dir.exists()
            if purged:
                shutil.rmtree(music_dir, ignore_errors=True)
                logger.info(f"🗑️ Bibliothèque supprimée post-ZIP [{key[:8]}]")
            events_client.emit(
                'zip_export',
                pseudo=_pseudo,
                role=_role,
                detail={**_zip_meta, 'library_purged': purged},
            )
        except Exception as e:
            logger.warning(f"⚠️ Post-download cleanup: {e}")

    def _stream_and_cleanup():
        sent = 0
        try:
            with open(zip_path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk
                    sent += len(chunk)
        finally:
            # Appelé par le WSGI quand le stream est terminé OU la connexion coupée
            # (GeneratorExit sur le yield). Interrompu (réseau, écran verrouillé sur
            # mobile…) → on ne touche à rien : bibliothèque intacte, ZIP toujours prêt
            # à être récupéré (SSF-14).
            if sent >= file_size:
                _after_full_export()
            else:
                logger.warning(f"⚠️ Export ZIP interrompu ({sent}/{file_size} octets) — "
                               f"bibliothèque conservée [{key[:8]}]")

    return Response(
        _stream_and_cleanup(),
        mimetype='application/zip',
        headers={
            'Content-Disposition': 'attachment; filename=SongSurf_musiques.zip',
            'Content-Length': file_size,
        },
    )


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
