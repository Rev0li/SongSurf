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

Storage: /data/music/<portal UUID>/Artist/Album/ (DEV_MODE: same, uid dev-user-local)
Persistent state (queue, quotas, ZIP exports): SQLite in /data/state (state_store.py)

Phase 3: see docs/CONNECTOR.md
"""

from flask import (Flask, request, jsonify, send_file, send_from_directory, Response, abort,
                   redirect, render_template)
from pathlib import Path
from datetime import datetime
from functools import wraps
from mutagen.mp3 import MP3
from mutagen.id3 import APIC
import hmac
import signal
import threading
import time
import os
import secrets
import shutil
import zipfile
import re
import io

from waitress import serve
from organizer import MusicOrganizer
from core import config, queue
from core.config import logger
from core.progress import _song_clock, _song_percent
from core.queue import (downloader, download_status, queue_lock, QUEUE_FULL_MSG,
                        _last_completed_by_user, _last_error_by_user,
                        _daily_limit_for, _daily_limit_response, _duration, _enqueue_job,
                        _is_valid_youtube_url, _job_owner, _queue_full, _today)
from core.storage import (_UID_RE, _cookies_missing_response, _user_cookies_file,
                          _user_key, _user_music_dir, _user_pseudo)
from core.worker import _cleanup_temp_leftovers, _on_sigterm, _resume_pending_batch, queue_worker

import events_client

# ── Configuration ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
# Taille max d'une requête entrante (pochettes, cookies, JSON) — limite technique,
# volontairement non paramétrable. Les téléchargements sortants ne sont pas concernés.
MAX_REQUEST_MB = 20
app.config['MAX_CONTENT_LENGTH'] = MAX_REQUEST_MB * 1024 * 1024

DEV_MODE              = os.getenv('DEV_MODE', 'false').lower() == 'true'
# Preuve envoyée par Caddy dans X-Proxy-Token (porte du portail). Vide = verrouillé.
SONGSURF_PROXY_SECRET = os.getenv('SONGSURF_PROXY_SECRET', '')
# Espace membre du portail : redirection après /logout, lien de la page « passe par le portail »
REVAUTH_HOME_URL      = os.getenv('REVAUTH_HOME_URL', '')

# CORS : seule l'extension SongSurf Clip est autorisée (requêtes avec credentials).
# ID fixe, dérivé de la clé "key" de chrome-extension/manifest.json — il ne change
# pas selon le dossier de chargement. Jamais "null" ni chrome-extension://* (S1).
SONGSURF_EXTENSION_ID = 'ojhafabhkjjlganipbadmpifkikhnadf'
_CORS_ORIGINS = {f'chrome-extension://{SONGSURF_EXTENSION_ID}'}

_DEV_USER = {'sub': 'dev', 'uid': 'dev-user-local', 'role': 'admin'}

def _retarget_artists(artists: list[str], old_artist: str | None, new_artist: str) -> list[str]:
    """TPE1 après un déplacement : seul l'artiste principal change, les featurings restent.

    Même artiste (déplacement entre ses albums) → TPE1 inchangé. Sinon l'ancien
    artiste est remplacé là où il apparaît, à défaut le premier de la liste.
    """
    if not artists:
        return [new_artist]
    if not old_artist or old_artist == new_artist:
        return list(artists)
    if old_artist in artists:
        out = [new_artist if a == old_artist else a for a in artists]
    else:
        out = [new_artist, *artists[1:]]
    return list(dict.fromkeys(out))  # dédoublonne en gardant l'ordre


def _sync_mp3_tags(file_path: Path, music_dir: Path, old_artist: str | None = None) -> None:
    """Met les tags d'un MP3 déplacé en accord avec son nouveau dossier (SSF-13).

    Structure assumed:
      Artist/Album/song.mp3  →  TALB = Album, TPE2 = Artist, TPE1 : artiste
                                principal remplacé (featurings gardés)
      Album/song.mp3         →  TALB = Album  (playlist mode)
    `old_artist` = dossier artiste d'origine (None si inconnu).
    """
    if file_path.suffix.lower() != '.mp3':
        return
    try:
        rel   = file_path.relative_to(music_dir)
        parts = rel.parts  # ('Artist','Album','song.mp3') or ('Album','song.mp3')
        if len(parts) == 3:
            artist, album = parts[0], parts[1]
        elif len(parts) == 2:
            artist, album = None, parts[0]
        else:
            return
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TPE1, TPE2, TALB
        audio = MP3(file_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        if artist:
            current = [str(a).strip() for a in (audio.tags['TPE1'].text if 'TPE1' in audio.tags else [])
                       if str(a).strip()]
            audio.tags['TPE1'] = TPE1(encoding=3, text=_retarget_artists(current, old_artist, artist))
            audio.tags['TPE2'] = TPE2(encoding=3, text=artist)
        audio.tags['TALB'] = TALB(encoding=3, text=album)
        audio.save()
    except Exception as e:
        logger.warning(f"⚠️ sync_mp3_tags({file_path.name}): {e}")


def _is_admin(user: dict | None) -> bool:
    return bool(user) and user.get('role') == 'admin'


def _admin_only_response():
    """Outils experts (SSF-13) : réservés à l'admin, 403 pour un membre."""
    return jsonify({'success': False, 'error': 'Réservé à l\'administrateur', 'code': 'admin_only'}), 403


# ── Authentication ─────────────────────────────────────────────────────────────

def _user_from_portal_headers() -> dict | None:
    """Identité posée par Caddy après vérification de la session par le portail.

    Fiable uniquement si X-Proxy-Token prouve que la requête vient de Caddy :
    SongSurf écoute sur le réseau local, n'importe quel appareil pourrait sinon
    se déclarer admin. Caddy retire les X-User-* envoyés par le client.
    """
    if not SONGSURF_PROXY_SECRET:
        return None
    proof = request.headers.get('X-Proxy-Token', '')
    if not proof:
        return None
    if not hmac.compare_digest(proof.encode(), SONGSURF_PROXY_SECRET.encode()):
        # Preuve présente mais fausse : secret désynchronisé avec Caddy, ou forge
        logger.warning("⚠️  X-Proxy-Token invalide — en-têtes d'identité ignorés")
        return None
    name = request.headers.get('X-User-Name', '').strip()
    role = request.headers.get('X-User-Role', '').strip().lower()
    if not name or not role:
        return None
    return {
        'sub':   name,                                          # pseudo : affichage, logs, .owner
        'uid':   request.headers.get('X-User-Id', '').strip(),  # UUID du portail : clé de stockage
        'role':  role,
    }


def _get_current_user() -> dict | None:
    """Seule source d'identité : DEV_MODE (utilisateur dev local) ou la porte du portail."""
    if DEV_MODE:
        return _DEV_USER.copy()
    return _user_from_portal_headers()


def _is_identified(user: dict | None) -> bool:
    """Pseudo présent ET UUID du portail valide : sans UUID, pas de clé de stockage,
    donc refus — jamais de repli sur le pseudo (SSF-03)."""
    return bool(user and user.get('sub') and _UID_RE.match(user.get('uid') or ''))


def _unauthenticated_response():
    """Requête arrivée sans passer par Caddy (accès direct au NAS, ou porte mal
    configurée). Pas de redirection vers la connexion, c'est le rôle de Caddy :
    API / extension → 401 JSON, navigateur → page « passe par le portail »."""
    if (request.headers.get('Origin', '') in _CORS_ORIGINS or request.is_json
            or 'application/json' in request.headers.get('Accept', '')):
        return jsonify({'success': False, 'error': 'Non authentifié'}), 401
    return render_template('use_portal.html', portal_url=REVAUTH_HOME_URL), 401


def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_identified(_get_current_user()):
            return _unauthenticated_response()
        return f(*args, **kwargs)
    return decorated


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
    if origin not in _CORS_ORIGINS:
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
    return redirect(REVAUTH_HOME_URL or '/')


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
    user = _get_current_user()
    return jsonify({**user, 'pseudo': _user_pseudo(user)})


# ── Health ─────────────────────────────────────────────────────────────────────

@app.route('/ping')
def ping():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


# ── Download status ────────────────────────────────────────────────────────────

@app.route('/api/status')
def get_status():
    current_user = _get_current_user()
    if not _is_identified(current_user):
        return _unauthenticated_response()
    my_key = _user_key(current_user)

    queue_size = queue.store.pending_count()
    my_pending = queue.store.pending_for(my_key)
    songs_before = queue.store.songs_before(my_key) if my_pending else None
    with queue_lock:
        status = download_status.copy()
        status['queue_size'] = queue_size
        current_pct = 0.0
        if status['in_progress']:
            status['progress'] = downloader.get_progress()
            started = _song_clock['started']
            current_pct = _song_percent(
                status['progress'].get('phase', ''),
                float(status['progress'].get('percent', 0) or 0),
                time.monotonic() - started if started is not None else 0.0,
                _song_clock['expected'],
            )
        status['current_percent'] = current_pct
        if status.get('batch_active'):
            total    = max(1, int(status.get('batch_total', 0) or 0))
            done     = max(0, min(total, int(status.get('batch_done', 0) or 0)))
            composed = ((done + (current_pct / 100.0 if status['in_progress'] else 0.0)) / total) * 100.0
            status['batch_percent'] = round(max(0.0, min(100.0, composed)), 1)
        else:
            status['batch_percent'] = float(current_pct)
    status['daily_count'] = queue.store.daily_count(my_key, _today())
    status['daily_limit'] = _daily_limit_for(current_user)
    with queue_lock:
        status['last_completed'] = _last_completed_by_user.get(my_key)
        status['last_error']     = _last_error_by_user.get(my_key)
    current_dl = status.get('current_download') or {}
    status['is_mine'] = not current_dl or current_dl.get('user_key') == my_key
    # Qui occupe le worker : l'admin voit le pseudo et le titre en cours, un membre
    # seulement « un autre membre » + combien de titres passent avant le sien.
    worker = {'songs_before_mine': None, 'owner': None, 'current': None}
    if current_dl and not status['is_mine']:
        if songs_before is not None:
            worker['songs_before_mine'] = songs_before + 1  # + le titre en cours
        if current_user.get('role') == 'admin':
            meta = current_dl.get('metadata') or {}
            worker['owner']   = current_dl.get('user_pseudo') or None
            worker['current'] = {'artist': meta.get('artist', ''), 'title': meta.get('title', '')}
    elif songs_before:
        worker['songs_before_mine'] = songs_before
    status['worker'] = worker
    # Titre en cours d'un autre membre : jamais son détail dans current_download.
    if not status['is_mine']:
        status['current_download'] = None
    # Détail "à venir" limité aux titres de l'utilisateur courant — jamais la file
    # d'un autre membre (même logique de confidentialité que is_mine ci-dessus).
    status['pending'] = [
        {'artist': m.get('artist', ''), 'title': m.get('title', ''), 'album': m.get('album', '')}
        for m in (p.get('metadata') or {} for p in my_pending)
    ][:200]
    # Un album = une ligne d'avancement « 3 / 12 titres » (SSF-13), pas un titre par ligne.
    status['jobs'] = queue.store.jobs_for(my_key)[:100]
    # Diagnostic cookies de l'appelant — exposé pour l'UI/debug.
    try:
        cookies_file = _user_cookies_file(current_user)
        status['cookies_present'] = cookies_file.is_file()
        status['cookies_age_days'] = (
            round((time.time() - cookies_file.stat().st_mtime) / 86400, 1)
            if status['cookies_present'] else None
        )
    except Exception:
        status['cookies_present']  = False
        status['cookies_age_days'] = None
    return jsonify(status)


# ── Library ────────────────────────────────────────────────────────────────────

def _build_library_tree(music_dir: Path) -> dict:
    artists = []
    playlists = []
    if not music_dir.exists():
        return {'artists': artists, 'playlists': playlists}
    for top in sorted([d for d in music_dir.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
        direct_songs = sorted(
            [f for f in top.iterdir() if f.is_file() and f.suffix.lower() == '.mp3'],
            key=lambda p: p.name.lower()
        )
        if direct_songs:
            playlists.append({
                'name':  top.name,
                'path':  str(top.relative_to(music_dir)),
                'songs': [{'name': s.name, 'path': str(s.relative_to(music_dir))} for s in direct_songs],
            })
            continue
        albums = []
        for album_dir in sorted([d for d in top.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
            songs = sorted(
                [f for f in album_dir.iterdir() if f.is_file() and f.suffix.lower() == '.mp3'],
                key=lambda p: p.name.lower()
            )
            albums.append({
                'name':  album_dir.name,
                'path':  str(album_dir.relative_to(music_dir)),
                'songs': [{'name': s.name, 'path': str(s.relative_to(music_dir))} for s in songs],
            })
        _PIC_NAMES = ('folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp',
                      'artist.jpg', 'artist.jpeg', 'artist.png', 'artist.webp')
        has_picture = any((top / n).exists() for n in _PIC_NAMES)
        artists.append({'name': top.name, 'path': str(top.relative_to(music_dir)), 'albums': albums, 'has_picture': has_picture})
    return {'artists': artists, 'playlists': playlists}


@app.route('/api/library')
@auth_required
def library_tree():
    try:
        user = _get_current_user()
        tree = _build_library_tree(_user_music_dir(user))
        return jsonify({'success': True, **tree})
    except Exception as e:
        logger.error(f"❌ /api/library: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/move', methods=['POST'])
@auth_required
def library_move_song():
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        data          = request.get_json() or {}
        source        = (data.get('source') or '').strip()
        target_folder = (data.get('target_folder') or '').strip()
        if not source or not target_folder:
            return jsonify({'success': False, 'error': 'source/target_folder requis'}), 400

        src     = (music_dir / source).resolve()
        dst_dir = (music_dir / target_folder).resolve()
        base    = music_dir.resolve()

        if not src.is_relative_to(base) or not dst_dir.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not src.exists() or src.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier source invalide'}), 404

        dst_dir.mkdir(parents=True, exist_ok=True)
        target = dst_dir / src.name
        i = 1
        while target.exists():
            target = dst_dir / f"{src.stem} ({i}){src.suffix}"
            i += 1

        src_parts  = src.relative_to(base).parts
        old_artist = src_parts[0] if len(src_parts) == 3 else None
        shutil.move(str(src), str(target))
        _sync_mp3_tags(target, music_dir, old_artist=old_artist)
        return jsonify({'success': True, 'final_path': str(target.relative_to(music_dir))})
    except Exception as e:
        logger.error(f"❌ /api/library/move: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/move-folder', methods=['POST'])
@auth_required
def library_move_folder():
    """Move an album folder to a different artist folder."""
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        data        = request.get_json() or {}
        folder_path = (data.get('folder_path') or '').strip()
        new_parent  = (data.get('new_parent') or '').strip()
        if not folder_path or not new_parent:
            return jsonify({'success': False, 'error': 'folder_path/new_parent requis'}), 400

        src        = (music_dir / folder_path).resolve()
        dst_parent = (music_dir / new_parent).resolve()
        base       = music_dir.resolve()

        if not src.is_relative_to(base) or not dst_parent.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not src.exists() or not src.is_dir():
            return jsonify({'success': False, 'error': 'Dossier source introuvable'}), 404
        if not dst_parent.exists() or not dst_parent.is_dir():
            return jsonify({'success': False, 'error': 'Dossier cible introuvable'}), 404
        if src.parent == dst_parent:
            return jsonify({'success': False, 'error': 'Album déjà dans cet artiste'}), 400

        dst = dst_parent / src.name
        if dst.exists():
            for item in list(src.iterdir()):
                target = dst / item.name
                if target.exists():
                    counter = 1
                    while target.exists():
                        if item.is_dir():
                            target = dst / f"{item.name} ({counter})"
                        else:
                            target = dst / f"{item.stem} ({counter}){item.suffix}"
                        counter += 1
                shutil.move(str(item), str(target))
            src.rmdir()
        else:
            shutil.move(str(src), str(dst))

        old_parent = src.parent
        if old_parent != base and old_parent.exists() and not any(old_parent.iterdir()):
            old_parent.rmdir()

        old_artist = old_parent.name if old_parent != base else None
        for mp3 in dst.rglob('*.mp3'):
            _sync_mp3_tags(mp3, music_dir, old_artist=old_artist)

        return jsonify({'success': True, 'new_path': str(dst.relative_to(music_dir))})
    except Exception as e:
        logger.error(f"❌ /api/library/move-folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/delete-folder', methods=['POST'])
@auth_required
def library_delete_folder():
    """Delete an artist or album folder — admin only (the admin library is permanent)."""
    try:
        user = _get_current_user()
        if user.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Admin requis'}), 403
        music_dir   = _user_music_dir(user)
        data        = request.get_json() or {}
        folder_path = (data.get('folder_path') or '').strip().strip('/')
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (music_dir / folder_path).resolve()
        base   = music_dir.resolve()
        if folder == base or not folder.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        deleted_songs = len(list(folder.rglob('*.mp3')))
        shutil.rmtree(folder)

        # Album supprimé → retire le dossier artiste s'il est devenu vide
        parent = folder.parent
        if parent != base and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

        logger.info(f"🗑️ Dossier supprimé: {folder_path} ({deleted_songs} titre(s)) par {_user_pseudo(user)}")
        return jsonify({'success': True, 'deleted_songs': deleted_songs})
    except Exception as e:
        logger.error(f"❌ /api/library/delete-folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Les URLs d'images sont versionnées côté frontend (?t=<version>, incrémentée
# uniquement à l'upload d'une pochette) : le navigateur peut donc mettre les
# réponses en cache sans risque de servir une image périmée.
_IMAGE_CACHE_CONTROL = 'private, max-age=86400'


def _image_response(path_or_buffer, mime):
    resp = send_file(path_or_buffer, mimetype=mime)
    resp.headers['Cache-Control'] = _IMAGE_CACHE_CONTROL
    return resp


@app.route('/api/library/folder-cover')
@auth_required
def library_folder_cover():
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        folder_path = (request.args.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return '', 204

        for name, mime in (
            ('cover.jpg', 'image/jpeg'), ('cover.jpeg', 'image/jpeg'),
            ('folder.jpg', 'image/jpeg'), ('folder.jpeg', 'image/jpeg'),
            ('folder.png', 'image/png'),  ('folder.webp', 'image/webp'),
            ('artist.jpg', 'image/jpeg'), ('artist.jpeg', 'image/jpeg'),
            ('artist.png', 'image/png'),  ('artist.webp', 'image/webp'),
        ):
            p = folder / name
            if p.exists():
                return _image_response(p, mime)

        mp3s = sorted(folder.rglob('*.mp3'), key=lambda p: p.name.lower())
        if not mp3s:
            return '', 204

        audio = MP3(mp3s[0])
        tags  = getattr(audio, 'tags', None)
        if tags:
            for frame in tags.values():
                if isinstance(frame, APIC) and getattr(frame, 'data', None):
                    # Persiste l'extraction en cover.jpg (dossier album uniquement,
                    # pas un dossier artiste) : les requêtes suivantes servent le
                    # fichier au lieu de re-parser le MP3 à chaque affichage.
                    if mp3s[0].parent == folder:
                        jpeg = MusicOrganizer(music_dir)._convert_image_bytes_to_jpeg(frame.data)
                        if jpeg:
                            try:
                                cover = folder / 'cover.jpg'
                                tmp   = folder / f'.cover-{secrets.token_hex(4)}.tmp'
                                tmp.write_bytes(jpeg)
                                tmp.replace(cover)  # rename atomique : jamais de fichier tronqué servi
                                return _image_response(cover, 'image/jpeg')
                            except OSError:
                                pass
                    return _image_response(io.BytesIO(frame.data), frame.mime or 'image/jpeg')
        return '', 204
    except Exception as e:
        logger.error(f"❌ /api/library/folder-cover: {e}")
        return '', 204


@app.route('/api/library/artist-picture')
@auth_required
def library_artist_picture():
    """Artist picture: looks for folder.jpg first, then artist.jpg (legacy fallback)."""
    try:
        user        = _get_current_user()
        music_dir   = _user_music_dir(user)
        folder_path = (request.args.get('folder_path') or '').strip()
        folder      = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return '', 204
        if not folder.exists() or not folder.is_dir():
            return '', 204
        for name, mime in (
            ('folder.jpg', 'image/jpeg'), ('folder.jpeg', 'image/jpeg'),
            ('folder.png', 'image/png'),  ('folder.webp', 'image/webp'),
            ('artist.jpg', 'image/jpeg'), ('artist.jpeg', 'image/jpeg'),
            ('artist.png', 'image/png'),  ('artist.webp', 'image/webp'),
        ):
            p = folder / name
            if p.exists():
                return _image_response(p, mime)
        return '', 204
    except Exception:
        return '', 204


def _write_song_tags(target: Path, tags_data: dict) -> None:
    """Writes editable ID3 frames to an MP3 (shared: metadata editor + audit apply)."""
    from mutagen.mp3 import MP3 as _MP3
    from mutagen.id3 import (ID3 as _ID3, TIT2, TPE1, TPE2, TALB, TDRC,
                              TRCK, TPOS, TCON, TCOM, TCOP, TPUB, TBPM,
                              TKEY, TLAN, TSRC, TENC, COMM)
    _FRAME_MAP = {
        'title':        TIT2, 'artist':       TPE1, 'album_artist': TPE2,
        'album':        TALB, 'year':         TDRC, 'track_number': TRCK,
        'disc_number':  TPOS, 'genre':        TCON, 'composer':     TCOM,
        'copyright':    TCOP, 'publisher':    TPUB, 'bpm':          TBPM,
        'key':          TKEY, 'language':     TLAN, 'isrc':         TSRC,
        'encoded_by':   TENC,
    }
    # Champs multi-valeurs : « A; B » → valeurs ID3v2.4 null-séparées.
    # album_artist (TPE2) reste single : c'est la clé de groupement Jellyfin.
    _MULTI_VALUE_FIELDS = {'artist', 'genre', 'composer'}

    audio = _MP3(target, ID3=_ID3)
    if audio.tags is None:
        audio.add_tags()

    for field, FrameClass in _FRAME_MAP.items():
        if field not in tags_data:
            continue
        v = str(tags_data[field]).strip()
        key = FrameClass.__name__
        if v:
            if field in _MULTI_VALUE_FIELDS:
                values = [s.strip() for s in v.split(';') if s.strip()] or [v]
            else:
                values = [v]
            audio.tags[key] = FrameClass(encoding=3, text=values)
        else:
            audio.tags.delall(key)

    # Handle comment separately (needs lang)
    if 'comment' in tags_data:
        audio.tags.delall('COMM')
        v = str(tags_data['comment']).strip()
        if v:
            audio.tags.add(COMM(encoding=3, lang='eng', desc='', text=[v]))

    audio.save()


# Champs acceptés par l'éditeur et l'audit (clés de _FRAME_MAP + comment)
_EDITABLE_FIELDS = {
    'title', 'artist', 'album_artist', 'album', 'year', 'track_number',
    'disc_number', 'genre', 'composer', 'copyright', 'publisher', 'bpm',
    'key', 'language', 'isrc', 'encoded_by', 'comment',
}


@app.route('/api/library/song-meta/save', methods=['POST'])
@auth_required
def save_song_meta():
    """Writes editable ID3 tags back to an MP3 file."""
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        data      = request.get_json() or {}
        path      = (data.get('path') or '').strip()
        tags_data = data.get('tags') or {}

        target = (music_dir / path).resolve()
        if not target.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        _write_song_tags(target, tags_data)
        logger.info(f"💾 Tags sauvegardés : {path}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/song-meta/save: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/song-cover/upload', methods=['POST'])
@auth_required
def upload_song_cover():
    """Embeds uploaded image as APIC in MP3 + saves cover.jpg to album folder."""
    from mutagen.mp3 import MP3 as _MP3
    from mutagen.id3 import ID3 as _ID3, APIC as _APIC
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        path      = (request.form.get('path') or '').strip()
        file      = request.files.get('image')
        if not path or not file:
            return jsonify({'success': False, 'error': 'path et image requis'}), 400

        target = (music_dir / path).resolve()
        if not target.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        img_data = file.read()
        mime     = file.content_type or 'image/jpeg'

        audio = _MP3(target, ID3=_ID3)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.delall('APIC')
        audio.tags.add(_APIC(encoding=3, mime=mime, type=3, desc='Cover', data=img_data))
        audio.save()

        # Also write to folder as cover.jpg for Jellyfin
        ext = '.jpg' if 'jpeg' in mime or 'jpg' in mime else '.png'
        with open(target.parent / f'cover{ext}', 'wb') as f:
            f.write(img_data)

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/song-cover/upload: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/artist-cover/upload', methods=['POST'])
@auth_required
def upload_artist_cover():
    """Saves uploaded image as artist.jpg in the artist folder."""
    try:
        user        = _get_current_user()
        music_dir   = _user_music_dir(user)
        folder_path = (request.form.get('folder_path') or '').strip()
        file        = request.files.get('image')
        if not folder_path or not file:
            return jsonify({'success': False, 'error': 'folder_path et image requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        mime = file.content_type or 'image/jpeg'
        ext  = '.jpg' if 'jpeg' in mime or 'jpg' in mime else '.png'
        with open(folder / f'folder{ext}', 'wb') as f:
            f.write(file.read())

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/artist-cover/upload: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/album-cover/upload', methods=['POST'])
@auth_required
def upload_album_cover():
    """Saves uploaded image as cover.jpg in the album folder (no MP3 embedding)."""
    try:
        user        = _get_current_user()
        music_dir   = _user_music_dir(user)
        folder_path = (request.form.get('folder_path') or '').strip()
        file        = request.files.get('image')
        if not folder_path or not file:
            return jsonify({'success': False, 'error': 'folder_path et image requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        mime = file.content_type or 'image/jpeg'
        ext  = '.jpg' if 'jpeg' in mime or 'jpg' in mime else '.png'
        with open(folder / f'cover{ext}', 'wb') as f:
            f.write(file.read())

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/album-cover/upload: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Extract / Download ─────────────────────────────────────────────────────────

@app.route('/api/extract', methods=['POST'])
@auth_required
def extract_metadata():
    try:
        user = _get_current_user()
        data = request.get_json()
        url  = (data.get('url') or '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL invalide. Collez un lien YouTube Music valide.'}), 400
        if (resp := _cookies_missing_response(user)) is not None:
            return resp
        cookiefile = str(_user_cookies_file(user))

        is_playlist = downloader._detect_type(url) == 'playlist'
        if is_playlist:
            result = downloader.extract_playlist_metadata(url, cookiefile=cookiefile)
            if result.get('success'):
                result['is_playlist'] = True
        else:
            result = downloader.extract_metadata(url, cookiefile=cookiefile)
            if result.get('success') and 'metadata' in result:
                meta = result.pop('metadata')
                result.update(meta)
                result['is_playlist'] = False

        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download', methods=['POST'])
@auth_required
def start_download():
    try:
        user = _get_current_user()
        data = request.get_json()
        url  = (data.get('url') or '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL invalide.'}), 400
        if (resp := _cookies_missing_response(user)) is not None:
            return resp
        # Le serveur draine la file, indépendamment de la page : le titre est empilé
        # comme un job d'une piste. 429 si l'utilisateur a trop de jobs en attente.
        if _queue_full(user):
            return jsonify({'success': False, 'error': QUEUE_FULL_MSG}), 429
        if (resp := _daily_limit_response(user)) is not None:
            return resp

        metadata = {
            'artist':       data.get('artist', 'Unknown Artist'),
            'artists':      data.get('artists') or [],
            'album_artist': data.get('album_artist', ''),
            'album':        data.get('album',  'Unknown Album'),
            'title':        data.get('title',  'Unknown Title'),
            'year':         data.get('year',   ''),
            'track_number': data.get('track_number', ''),
        }
        _enqueue_job(user, [{'url': url, 'metadata': metadata, 'duration': _duration(data.get('duration')),
                             **_job_owner(user)}])
        logger.info(f"➕ Queue: {metadata['artist']} - {metadata['title']} [{_user_pseudo(user)}]")
        return jsonify({'success': True, 'queue_size': queue.store.pending_count()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download-playlist', methods=['POST'])
@auth_required
def download_playlist():
    try:
        user     = _get_current_user()
        data     = request.get_json()
        playlist = data.get('playlist_metadata', {})
        songs    = playlist.get('songs', [])
        if not songs:
            return jsonify({'success': False, 'error': 'Données manquantes'}), 400
        if (resp := _cookies_missing_response(user)) is not None:
            return resp
        # L'album entier est empilé comme un seul job, ses titres dans l'ordre ; le
        # worker alterne avec les titres des autres membres (round-robin) et continue
        # même si on quitte la page.
        if _queue_full(user):
            return jsonify({'success': False, 'error': QUEUE_FULL_MSG}), 429
        if (resp := _daily_limit_response(user)) is not None:
            return resp

        items = [{
            'url':         song['url'],
            'metadata':    {
                'artist':       playlist.get('artist') or song.get('artist') or 'Unknown Artist',
                'artists':      song.get('artists') or [],
                'album_artist': playlist.get('artist') or '',
                'album':        playlist.get('title', 'Unknown Album'),
                'title':        song['title'],
                'year':         playlist.get('year', ''),
                'track_number': song.get('track_number', ''),
                'track_total':  len(songs),
            },
            'duration':    _duration(song.get('duration')),
            **_job_owner(user),
        } for song in songs]

        added = _enqueue_job(user, items)
        return jsonify({'success': True, 'added': added, 'total': len(songs),
                        'queue_size': queue.store.pending_count()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
        user      = _get_current_user()
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
    key   = _user_key(_get_current_user())
    state = queue.store.zip_get(key)
    if state and state['status'] == 'ready' and not Path(state['zip_path']).is_file():
        queue.store.zip_delete(key)   # fichier disparu (config.TEMP_DIR nettoyé) → plus rien à récupérer
        state = None
    return jsonify({'success': True, **_zip_public(state)})


@app.route('/api/download-zip')
@auth_required
def download_zip():
    user      = _get_current_user()
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


# ── Admin logs ────────────────────────────────────────────────────────────────

@app.route('/api/admin/dl-logs')
@auth_required
def api_admin_dl_logs():
    user = _get_current_user()
    if user.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Admin requis'}), 403

    pseudo = (request.args.get('pseudo') or '').strip().lower()
    # `limit=all` : historique complet (fiches par membre du portail) ;
    # sinon 1..500, 100 par défaut ou si la valeur est illisible.
    raw_limit = (request.args.get('limit') or '100').strip().lower()
    if raw_limit == 'all':
        limit = None
    else:
        try:
            limit = min(max(1, int(raw_limit)), 500)
        except ValueError:
            limit = 100

    log_path = config.LOG_DIR / 'downloads.log'
    entries  = []
    try:
        if log_path.exists():
            with open(log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(' | ')
                    if len(parts) < 5:
                        continue
                    ts, log_pseudo, artist, album, title = parts[0], parts[1], parts[2], parts[3], parts[4]
                    if pseudo and log_pseudo.strip().lower() != pseudo:
                        continue
                    entries.append({'timestamp': ts, 'pseudo': log_pseudo.strip(),
                                    'artist': artist.strip(), 'album': album.strip(), 'title': title.strip()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    entries.reverse()
    return jsonify({'success': True, 'entries': entries if limit is None else entries[:limit],
                    'total': len(entries)})


# ── Audit métadonnées (admin) ─────────────────────────────────────────────────

@app.route('/api/library/audit/artist')
@auth_required
def library_audit_artist():
    """Rapport iTunes + cohérence ID3 pour tous les albums d'un artiste.
    Outil expert : admin uniquement (SSF-13)."""
    try:
        user = _get_current_user()
        if not _is_admin(user):
            return _admin_only_response()
        music_dir = _user_music_dir(user)
        path      = (request.args.get('path') or '').strip()
        if not path:
            return jsonify({'success': False, 'error': 'path requis'}), 400

        artist_dir = (music_dir / path).resolve()
        if not artist_dir.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not artist_dir.exists() or not artist_dir.is_dir():
            return jsonify({'success': False, 'error': 'Dossier artiste introuvable'}), 404

        from library_audit import audit_artist
        report = audit_artist(artist_dir, music_dir)
        logger.info(f"🔎 Audit {report['artist']}: {report['total_recommendations']} recommandation(s)")
        return jsonify({'success': True, **report})
    except Exception as e:
        logger.error(f"❌ /api/library/audit/artist: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/audit/apply', methods=['POST'])
@auth_required
def library_audit_apply():
    """Applique les recommandations cochées : [{path, field, value}].
    Outil expert : admin uniquement (SSF-13)."""
    try:
        user = _get_current_user()
        if not _is_admin(user):
            return _admin_only_response()
        music_dir = _user_music_dir(user)
        changes   = (request.get_json(silent=True) or {}).get('changes') or []

        applied, errors = 0, []
        for ch in changes:
            path  = str(ch.get('path') or '').strip()
            field = str(ch.get('field') or '').strip()
            value = str(ch.get('value') or '')
            if not path or field not in _EDITABLE_FIELDS:
                errors.append(f'{path or "?"}: champ invalide')
                continue
            target = (music_dir / path).resolve()
            if not target.is_relative_to(music_dir.resolve()):
                errors.append(f'{path}: chemin invalide')
                continue
            if not target.exists() or target.suffix.lower() != '.mp3':
                errors.append(f'{path}: fichier introuvable')
                continue
            try:
                _write_song_tags(target, {field: value})
                applied += 1
            except Exception as e:
                errors.append(f'{path}: {e}')

        logger.info(f"🔎 Audit apply: {applied} tag(s) écrits, {len(errors)} erreur(s)")
        return jsonify({'success': True, 'applied': applied, 'errors': errors})
    except Exception as e:
        logger.error(f"❌ /api/library/audit/apply: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Extension Chrome — cookies sync (par utilisateur) ──────────────────────────


def _is_netscape_cookies(content: str) -> bool:
    """Format Netscape attendu par yt-dlp : commentaires (#) ou lignes à 7 champs tabulés."""
    entries = 0
    for line in content.splitlines():
        if not line.strip():
            continue
        if line.startswith('#') and not line.startswith('#HttpOnly_'):
            continue
        if len(line.split('\t')) != 7:
            return False
        entries += 1
    return entries > 0


@app.route('/api/cookies/update', methods=['POST'])
@auth_required
def update_cookies():
    """Extension Chrome — reçoit les cookies YouTube de l'utilisateur courant pour yt-dlp."""
    try:
        user    = _get_current_user()
        data    = request.get_json(silent=True) or {}
        content = (data.get('cookies') or '').strip()
        if not content:
            return jsonify({'success': False, 'error': 'Cookies manquants'}), 400
        if not _is_netscape_cookies(content):
            return jsonify({'success': False, 'error': 'Format de cookies invalide (Netscape attendu)'}), 400
        target = _user_cookies_file(user)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.tmp')
        tmp.write_text(content + '\n', encoding='utf-8')
        tmp.chmod(0o600)
        tmp.replace(target)
        count  = sum(1 for l in content.splitlines() if l and not l.startswith('#'))
        pseudo = _user_pseudo(user)
        logger.info(f"🍪 Cookies mis à jour depuis l'extension Chrome ({count} entrées) [{pseudo}]")
        return jsonify({'success': True, 'count': count, 'pseudo': pseudo})
    except Exception as e:
        logger.error(f"❌ /api/cookies/update: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Extension Chrome — preview + queue direct ──────────────────────────────────

def _detect_url_mode(url: str) -> str:
    """Returns 'song', 'album', or 'playlist' from a YouTube Music URL."""
    from urllib.parse import urlparse, parse_qs
    try:
        parsed = urlparse(url)
        if parsed.path == '/watch' and parse_qs(parsed.query).get('v'):
            return 'song'
        if parsed.path == '/playlist':
            list_id = (parse_qs(parsed.query).get('list') or [''])[0]
            return 'album' if list_id.startswith('OLAK5uy_') else 'playlist'
        if '/browse/' in parsed.path:
            browse_id = parsed.path.rstrip('/').split('/')[-1]
            if browse_id.startswith('MPREb_'):
                return 'album'
    except Exception:
        pass
    return 'song'


@app.route('/api/preview', methods=['POST'])
@auth_required
def preview_metadata():
    """
    Extension Chrome — extrait les métadonnées sans effet de bord.
    Utilisé pour la mini-analyse avant confirmation.
    """
    try:
        user     = _get_current_user()
        data     = request.get_json(silent=True) or {}
        url      = (data.get('url') or '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL invalide'}), 400
        if (resp := _cookies_missing_response(user)) is not None:
            return resp

        url_mode   = _detect_url_mode(url)
        cookiefile = str(_user_cookies_file(user))

        if url_mode == 'song':
            result = downloader.extract_metadata(url, cookiefile=cookiefile)
            if not result.get('success'):
                return jsonify({'success': False, 'error': result.get('error', 'Extraction échouée')}), 400
            meta = result.get('metadata', {})
            return jsonify({
                'success':   True,
                'type':      'song',
                'title':     meta.get('title', ''),
                'artist':    meta.get('artist', ''),
                'album':     meta.get('album', ''),
                'year':      meta.get('year', ''),
                'thumbnail': meta.get('thumbnail_url', ''),
            })
        else:
            result = downloader.extract_playlist_metadata(url, cookiefile=cookiefile)
            if not result.get('success'):
                return jsonify({'success': False, 'error': result.get('error', 'Extraction échouée')}), 400
            return jsonify({
                'success':     True,
                'type':        url_mode,
                'title':       result.get('title', ''),
                'artist':      result.get('artist', ''),
                'year':        result.get('year', ''),
                'thumbnail':   result.get('thumbnail_url', ''),
                'song_count':  result.get('total_songs', 0),
            })
    except Exception as e:
        logger.error(f"❌ /api/preview: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _queue_direct_async(url: str, url_mode: str, user: dict, override: dict | None = None):
    """Daemon thread — extrait les métadonnées (sauf si override fourni) puis enqueue."""
    cookiefile = str(_user_cookies_file(user))
    try:
        if url_mode == 'song':
            if override and override.get('title'):
                metadata = {
                    'artist': override.get('artist', 'Unknown Artist') or 'Unknown Artist',
                    'album':  override.get('album',  'Unknown Album')  or 'Unknown Album',
                    'title':  override.get('title',  'Unknown Title')  or 'Unknown Title',
                    'year':   override.get('year',   ''),
                }
                duration = 0
            else:
                result = downloader.extract_metadata(url, cookiefile=cookiefile)
                if not result.get('success'):
                    logger.warning(f"⚠️ queue-direct extract failed: {result.get('error')}")
                    return
                meta = result.get('metadata', {})
                duration = meta.get('duration')
                metadata = {
                    'artist':       (override or {}).get('artist') or meta.get('artist', 'Unknown Artist'),
                    # override artiste → la liste extraite n'est plus fiable
                    'artists':      [] if (override or {}).get('artist') else meta.get('artists') or [],
                    'album_artist': meta.get('album_artist', ''),
                    'album':        (override or {}).get('album')  or meta.get('album',  'Unknown Album'),
                    'title':        meta.get('title', 'Unknown Title'),
                    'year':         meta.get('year', ''),
                    'track_number': meta.get('track_number', ''),
                }
            if _queue_full(user):
                logger.warning("⚠️ queue-direct (song): file pleine")
                return
            _enqueue_job(user, [{'url': url, 'metadata': metadata,
                                 'duration': _duration(duration),
                                 **_job_owner(user)}])
            logger.info(f"📥 queue-direct (song): {metadata['artist']} — {metadata['title']}")
        else:
            result = downloader.extract_playlist_metadata(url, cookiefile=cookiefile)
            if not result.get('success'):
                logger.warning(f"⚠️ queue-direct playlist extract failed: {result.get('error')}")
                return
            songs       = result.get('songs', [])
            album_name  = (override or {}).get('album')  or result.get('title', 'Unknown Album')
            artist_name = (override or {}).get('artist') or result.get('artist', 'Unknown Artist')
            items = [{
                'url':         song['url'],
                'metadata':    {
                    'artist':       artist_name,
                    'artists':      song.get('artists') or [],
                    'album_artist': artist_name,
                    'album':        album_name,
                    'title':        song.get('title', 'Unknown Title'),
                    'year':         result.get('year', ''),
                    'track_number': song.get('track_number', ''),
                    'track_total':  len(songs),
                },
                'duration':    _duration(song.get('duration')),
                **_job_owner(user),
            } for song in songs]
            if _queue_full(user):
                logger.warning("⚠️ queue-direct (album): file pleine")
                return
            added = _enqueue_job(user, items)
            logger.info(f"📥 queue-direct ({url_mode}): {added} titres — {album_name} / {artist_name}")
    except Exception as e:
        logger.error(f"❌ queue-direct async: {e}")


@app.route('/api/queue-direct', methods=['POST'])
@auth_required
def queue_direct():
    """
    Extension Chrome — extrait les métadonnées et empile côté serveur (fire-and-forget).
    Aucune dépendance à la page SongSurf : le NAS télécharge même si aucun onglet n'est
    ouvert. La réponse est immédiate ; l'extraction yt-dlp tourne dans un thread.
    """
    try:
        user = _get_current_user()
        data = request.get_json(silent=True) or {}
        url  = (data.get('url') or '').strip()

        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL invalide'}), 400
        if (resp := _cookies_missing_response(user)) is not None:
            return resp
        if _queue_full(user):
            return jsonify({'success': False, 'error': QUEUE_FULL_MSG}), 429
        if (resp := _daily_limit_response(user)) is not None:
            return resp

        url_mode = _detect_url_mode(url)
        override = {
            'artist': (data.get('artist') or '').strip(),
            'album':  (data.get('album')  or '').strip(),
            'title':  (data.get('title')  or '').strip(),
            'year':   (data.get('year')   or '').strip(),
        }
        threading.Thread(
            target=_queue_direct_async,
            args=(url, url_mode, user, override),
            daemon=True,
        ).start()

        labels = {'song': 'chanson', 'album': 'album', 'playlist': 'playlist'}
        return jsonify({'success': True, 'type': url_mode, 'label': labels.get(url_mode, url_mode)})
    except Exception as e:
        logger.error(f"❌ /api/queue-direct: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Metadata inspector ─────────────────────────────────────────────────────────

def _read_full_meta(file_path: Path, music_dir: Path) -> dict:
    """Returns every readable piece of metadata from an MP3 file."""
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3
    import mutagen

    result = {
        'path':      str(file_path.relative_to(music_dir)),
        'file_name': file_path.name,
        'file_size': file_path.stat().st_size,
        'file_size_mb': round(file_path.stat().st_size / (1024 * 1024), 2),
    }

    try:
        audio = MP3(file_path, ID3=ID3)
        info  = audio.info

        _COVER_NAMES = ('cover.jpg', 'cover.jpeg', 'folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp')
        _ARTIST_PIC_NAMES = (
            'folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp',
            'artist.jpg', 'artist.jpeg', 'artist.png', 'artist.webp',
        )

        tags = audio.tags or {}

        # encoder_settings from TSSE lives in audio, not ID3
        tsse = tags.get('TSSE')
        encoder_settings = None
        if tsse:
            try:
                encoder_settings = str(tsse.text[0]) if hasattr(tsse, 'text') else str(tsse)
            except Exception:
                pass

        result['audio'] = {
            'duration_s':      round(info.length, 1),
            'duration_fmt':    f"{int(info.length)//60}:{int(info.length)%60:02d}",
            'bitrate_kbps':    getattr(info, 'bitrate', 0) // 1000,
            'sample_rate':     getattr(info, 'sample_rate', 0),
            'channels':        getattr(info, 'channels', 0),
            'mode':            str(getattr(info, 'mode', '')),
            'encoder_settings': encoder_settings,
        }

        # Map ID3 text frames (TSSE excluded — handled above)
        _FRAME_LABELS = {
            'TIT2': 'title',          'TPE1': 'artist',
            'TPE2': 'album_artist',   'TPE3': 'conductor',
            'TALB': 'album',          'TDRC': 'year',
            'TRCK': 'track_number',   'TPOS': 'disc_number',
            'TCON': 'genre',          'TCOM': 'composer',
            'TCOP': 'copyright',      'TPUB': 'publisher',
            'TBPM': 'bpm',            'TKEY': 'key',
            'TLAN': 'language',       'TENC': 'encoded_by',
            'TSRC': 'isrc',           'TLEN': 'length_ms',
            'COMM': 'comment',        'USLT': 'lyrics_text',
        }
        id3 = {}
        for frame_id, label in _FRAME_LABELS.items():
            frame = tags.get(frame_id)
            if frame is not None:
                try:
                    if hasattr(frame, 'text'):
                        # Multi-valeurs (TPE1 null-séparé, etc.) → « A; B »
                        id3[label] = '; '.join(str(t) for t in frame.text)
                    else:
                        id3[label] = str(frame)
                except Exception:
                    pass

        # TYER fallback for ID3v2.3 files that use TYER instead of TDRC
        if not id3.get('year'):
            tyer = tags.get('TYER')
            if tyer is not None:
                try:
                    id3['year'] = str(tyer.text[0]).strip()[:4]
                except Exception:
                    pass

        # APIC (embedded cover)
        id3['has_embedded_cover'] = any(k.startswith('APIC') for k in tags.keys())

        # TXXX (custom tags — MusicBrainz IDs, ReplayGain, etc.)
        custom = {}
        for k, v in tags.items():
            if k.startswith('TXXX'):
                try:
                    custom[str(v.desc)] = str(v.text[0])
                except Exception:
                    pass
        if custom:
            id3['custom_tags'] = custom

        result['id3'] = id3

        # External cover in album folder
        covers = [n for n in _COVER_NAMES if (file_path.parent / n).exists()]
        result['cover_files']    = covers
        result['has_album_cover'] = len(covers) > 0

        # Artist picture in artist root folder (only for Artist/Album/song.mp3 structure)
        rel_parts = file_path.relative_to(music_dir).parts
        artist_pics = []
        if len(rel_parts) >= 3:
            artist_folder = music_dir / rel_parts[0]
            artist_pics   = [n for n in _ARTIST_PIC_NAMES if (artist_folder / n).exists()]
        result['artist_picture_files'] = artist_pics

    except Exception as e:
        result['error'] = str(e)

    return result


@app.route('/api/library/song-meta')
@auth_required
def library_song_meta():
    """Full metadata dump for a single MP3 file."""
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        path      = (request.args.get('path') or '').strip()
        if not path:
            return jsonify({'success': False, 'error': 'path requis'}), 400

        target = (music_dir / path).resolve()
        if not target.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        return jsonify({'success': True, **_read_full_meta(target, music_dir)})
    except Exception as e:
        logger.error(f"❌ /api/library/song-meta: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/album-tracks')
@auth_required
def library_album_tracks():
    """Tracklist légère d'un album (titre, TRCK, artistes, année, genres) :
    page album, mode « Numéroter » et assistant « À remplir »."""
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        folder_path = (request.args.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        from library_audit import _read_tags
        items = []
        for f in sorted([p for p in folder.iterdir()
                         if p.is_file() and p.suffix.lower() == '.mp3'],
                        key=lambda p: p.name.lower()):
            tags = _read_tags(f)
            items.append({
                'path':         str(f.relative_to(music_dir)),
                'name':         f.name,
                'title':        tags['title'],
                'track_number': tags['track_number'],
                'artists':      tags['artists'],
                'year':         tags['year'],
                'genres':       tags['genres'],
            })
        return jsonify({'success': True, 'tracks': items})
    except Exception as e:
        logger.error(f"❌ /api/library/album-tracks: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Complétude d'un album, mise en cache tant que ses MP3 ne changent pas
# (signature = noms + mtime + taille) : l'écriture d'un tag invalide l'entrée.
_album_status_cache: dict[str, tuple] = {}
_album_status_lock = threading.Lock()


def _album_status(album_dir: Path, music_dir: Path) -> dict | None:
    """{path, name, tracks, missing{genre,year,track_number}, genres, complete} — None sans MP3."""
    try:
        mp3s = sorted(f for f in album_dir.iterdir() if f.is_file() and f.suffix.lower() == '.mp3')
    except OSError:
        return None
    if not mp3s:
        return None
    sig = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in mp3s)
    key = str(album_dir)
    with _album_status_lock:
        hit = _album_status_cache.get(key)
    if hit and hit[0] == sig:
        result = hit[1]
    else:
        from library_audit import _read_tags
        missing = {'genre': 0, 'year': 0, 'track_number': 0}
        genres  = set()
        for f in mp3s:
            tags = _read_tags(f)
            if not tags['genres']:
                missing['genre'] += 1
            genres.update(tags['genres'])
            if not tags['year']:
                missing['year'] += 1
            if not tags['track_number']:
                missing['track_number'] += 1
        result = {'tracks': len(mp3s), 'missing': missing, 'genres': sorted(genres),
                  'complete': not any(missing.values())}
        with _album_status_lock:
            _album_status_cache[key] = (sig, result)
    return {'path': str(album_dir.relative_to(music_dir)), 'name': album_dir.name, **result}


@app.route('/api/library/todo')
@auth_required
def library_todo():
    """Albums aux infos incomplètes (année, n° de piste ou genre) de toute la
    bibliothèque de l'utilisateur : bouton et assistant « À remplir » (SSF-13)."""
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        albums = []
        if music_dir.exists():
            for artist_dir in sorted((d for d in music_dir.iterdir() if d.is_dir()),
                                     key=lambda p: p.name.lower()):
                for album_dir in sorted((d for d in artist_dir.iterdir() if d.is_dir()),
                                        key=lambda p: p.name.lower()):
                    st = _album_status(album_dir, music_dir)
                    if st and not st['complete']:
                        albums.append({**st, 'artist': artist_dir.name,
                                       'artist_path': str(artist_dir.relative_to(music_dir))})
        return jsonify({'success': True, 'albums': albums})
    except Exception as e:
        logger.error(f"❌ /api/library/todo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


_FORBIDDEN_NAME_CHARS = '<>:"/\\|?*'


def _clean_folder_name(name: str) -> str:
    """Nom de dossier sûr (mêmes caractères interdits que l'organizer)."""
    for ch in _FORBIDDEN_NAME_CHARS:
        name = name.replace(ch, '')
    name = name.strip().rstrip('.')
    return '' if name in ('', '.', '..') else name


@app.route('/api/library/album-tags/save', methods=['POST'])
@auth_required
def library_album_tags_save():
    """« Modifier l'album » et « À remplir » (SSF-13) : écrit sur tous les titres
    d'un album les champs fournis parmi `album`, `year`, `genre`.

    Nouveau nom d'album → TALB de chaque titre + dossier renommé (SongSurf et
    Jellyfin restent d'accord). 409 si un album du même nom existe déjà.
    """
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        data        = request.get_json(silent=True) or {}
        folder_path = (data.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        base   = music_dir.resolve()
        folder = (music_dir / folder_path).resolve()
        if folder == base or folder.parent == base or not folder.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        tags = {}
        if 'year' in data:
            year = str(data.get('year') or '').strip()
            if year and not re.fullmatch(r'\d{4}', year):
                return jsonify({'success': False, 'error': 'Année invalide (4 chiffres)'}), 400
            tags['year'] = year
        if 'genre' in data:
            tags['genre'] = str(data.get('genre') or '').strip()

        target = folder
        if 'album' in data:
            new_name = _clean_folder_name(str(data.get('album') or ''))
            if not new_name:
                return jsonify({'success': False, 'error': "Nom d'album invalide"}), 400
            tags['album'] = new_name
            if new_name != folder.name:
                target = folder.parent / new_name
                # Renommage de casse seule (« live » → « Live ») autorisé sur un FS insensible
                if target.exists() and target.resolve() != folder:
                    return jsonify({'success': False, 'error': 'Un album porte déjà ce nom',
                                    'code': 'album_exists'}), 409
                folder.rename(target)

        mp3s = sorted(f for f in target.iterdir() if f.is_file() and f.suffix.lower() == '.mp3')
        updated, errors = 0, []
        for f in mp3s:
            try:
                if tags:
                    _write_song_tags(f, tags)
                updated += 1
            except Exception as e:
                errors.append({'path': str(f.relative_to(base)), 'error': str(e)})

        logger.info(f"💾 Album {folder_path} → {target.name} : {sorted(tags)} sur {updated} titre(s)")
        return jsonify({'success': True, 'path': str(target.relative_to(base)),
                        'updated': updated, 'errors': errors})
    except Exception as e:
        logger.error(f"❌ /api/library/album-tags/save: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/delete-song', methods=['POST'])
@auth_required
def library_delete_song():
    """Supprime un titre — admin uniquement (SSF-13). Album devenu sans MP3 →
    dossier retiré (pochette comprise), puis l'artiste s'il est vide."""
    try:
        user = _get_current_user()
        if not _is_admin(user):
            return _admin_only_response()
        music_dir = _user_music_dir(user)
        path      = ((request.get_json(silent=True) or {}).get('path') or '').strip()
        if not path:
            return jsonify({'success': False, 'error': 'path requis'}), 400

        base   = music_dir.resolve()
        target = (music_dir / path).resolve()
        if not target.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or not target.is_file() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        target.unlink()
        album = target.parent
        removed_album = False
        if album != base and not any(f.suffix.lower() == '.mp3' for f in album.rglob('*') if f.is_file()):
            shutil.rmtree(album)
            removed_album = True
            artist = album.parent
            if artist != base and artist.exists() and not any(artist.iterdir()):
                artist.rmdir()

        logger.info(f"🗑️ Titre supprimé : {path} par {_user_pseudo(user)}")
        return jsonify({'success': True, 'removed_album': removed_album})
    except Exception as e:
        logger.error(f"❌ /api/library/delete-song: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/album-status')
@auth_required
def library_album_status():
    """Complétude des tags par album d'un artiste (badges de la vue artiste).

    `?folder_path=<dossier artiste>` → par album : nombre de titres sans
    genre / année / numéro de piste.
    """
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        folder_path = (request.args.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        albums = []
        for album_dir in sorted([d for d in folder.iterdir() if d.is_dir()],
                                key=lambda p: p.name.lower()):
            st = _album_status(album_dir, music_dir)
            if st:
                albums.append(st)
        return jsonify({'success': True, 'albums': albums})
    except Exception as e:
        logger.error(f"❌ /api/library/album-status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/renumber-album', methods=['POST'])
@auth_required
def library_renumber_album():
    """Réécrit TRCK `i/total` sur tout un album, dans l'ordre fourni.

    `paths` doit couvrir exactement les MP3 du dossier : garantit une
    numérotation 1..N cohérente (pas de trous ni de doublons).
    Outil expert : admin uniquement (SSF-13).
    """
    try:
        user      = _get_current_user()
        if not _is_admin(user):
            return _admin_only_response()
        music_dir = _user_music_dir(user)
        data        = request.get_json(silent=True) or {}
        folder_path = (data.get('folder_path') or '').strip()
        paths       = data.get('paths') or []
        if not folder_path or not paths or not isinstance(paths, list):
            return jsonify({'success': False, 'error': 'folder_path et paths requis'}), 400

        folder = (music_dir / folder_path).resolve()
        base   = music_dir.resolve()
        if not folder.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        targets = []
        for p in paths:
            target = (music_dir / str(p)).resolve()
            if not target.is_relative_to(base) or target.parent != folder:
                return jsonify({'success': False, 'error': f'Chemin invalide : {p}'}), 400
            if not target.exists() or target.suffix.lower() != '.mp3':
                return jsonify({'success': False, 'error': f'Fichier introuvable : {p}'}), 404
            targets.append(target)

        folder_mp3s = {f for f in folder.iterdir()
                       if f.is_file() and f.suffix.lower() == '.mp3'}
        if len(targets) != len(set(targets)) or set(targets) != folder_mp3s:
            return jsonify({'success': False,
                            'error': "paths doit lister chaque titre de l'album exactement une fois"}), 400

        total = len(targets)
        for i, target in enumerate(targets, start=1):
            _write_song_tags(target, {'track_number': f'{i}/{total}'})

        logger.info(f"🔢 Album renuméroté 1..{total} : {folder_path}")
        return jsonify({'success': True, 'total': total})
    except Exception as e:
        logger.error(f"❌ /api/library/renumber-album: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/set-artist-genre', methods=['POST'])
@auth_required
def library_set_artist_genre():
    """Écrit TCON sur tous les MP3 d'un dossier artiste (tous ses albums).

    `genre` accepte plusieurs valeurs séparées par « ; » (frame multi-valeurs,
    même convention que l'éditeur de métadonnées). Écrase le genre existant.
    Outil expert : admin uniquement (SSF-13).
    """
    try:
        user      = _get_current_user()
        if not _is_admin(user):
            return _admin_only_response()
        music_dir = _user_music_dir(user)
        data        = request.get_json(silent=True) or {}
        folder_path = (data.get('folder_path') or '').strip()
        genre       = str(data.get('genre') or '').strip()
        if not folder_path or not genre:
            return jsonify({'success': False, 'error': 'folder_path et genre requis'}), 400

        base   = music_dir.resolve()
        folder = (music_dir / folder_path).resolve()
        if folder == base or not folder.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        mp3s = sorted(f for f in folder.rglob('*')
                      if f.is_file() and f.suffix.lower() == '.mp3')
        updated, errors = 0, []
        for f in mp3s:
            try:
                _write_song_tags(f, {'genre': genre})
                updated += 1
            except Exception as e:
                errors.append({'path': str(f.relative_to(base)), 'error': str(e)})

        logger.info(f"🎼 Genre « {genre} » appliqué à {updated} titre(s) : {folder_path}")
        return jsonify({'success': True, 'updated': updated, 'errors': errors})
    except Exception as e:
        logger.error(f"❌ /api/library/set-artist-genre: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    flask_port = int(os.getenv('FLASK_PORT', '8081'))
    if DEV_MODE:
        mode = "DEV (sans authentification)"
    elif SONGSURF_PROXY_SECRET:
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
