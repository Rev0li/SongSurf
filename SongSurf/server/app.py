#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SongSurf — music download server

Auth model (Phase 2):
  - Watcher injects X-Watcher-Token + X-User-Id + X-User-Role + X-User-Email
  - SongSurf trusts these headers (no JWT validation here)
  - WATCHER_SECRET set   → require token match, then read user from headers
  - WATCHER_SECRET unset + DEV_MODE=true → inject dev user (standalone testing)

Storage: /data/music/Artist/Album/  (flat, no user-sub prefix)

Phase 3: see documentation/CONNECTOR.md
"""

from flask import Flask, request, jsonify, send_file, send_from_directory, Response, abort
from pathlib import Path
from datetime import datetime
from functools import wraps
from mutagen.mp3 import MP3
from mutagen.id3 import APIC
import hmac
import threading
import time
import queue
import os
import secrets
import shutil
import zipfile
import logging
import re
import json
import io
import sys

from downloader import YouTubeDownloader
from organizer import MusicOrganizer
from genre_lookup import lookup_genres

# En Docker, events_client.py est copié à côté de app.py ;
# en dev local (make dev) il vit dans ../shared.
_SHARED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared')
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)
import events_client

# ── Configuration ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

WATCHER_SECRET = os.getenv('WATCHER_SECRET', '')
DEV_MODE       = os.getenv('DEV_MODE', 'false').lower() == 'true'

DAILY_DOWNLOAD_LIMIT = int(os.getenv('DAILY_DOWNLOAD_LIMIT', '50'))  # 0 = unlimited

_DEV_USER = {'sub': 'dev-user-local', 'role': 'admin', 'email': 'dev@local'}

# ── Directories ───────────────────────────────────────────────────────────────

if Path(__file__).parent == Path('/app'):
    BASE_MUSIC_DIR = Path('/data/music')
    TEMP_DIR       = Path('/data/temp')
    LOG_DIR        = Path('/app/logs')
else:
    _base          = Path(__file__).parent.parent
    BASE_MUSIC_DIR = _base / 'music'
    TEMP_DIR       = _base / 'temp'
    LOG_DIR        = _base / 'logs'

for _d in [BASE_MUSIC_DIR, TEMP_DIR, LOG_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Push d'événements d'activité vers rev0auth (no-op si AUTH_EVENTS_URL absent)
events_client.init('songsurf', str(LOG_DIR / 'events-pending-songsurf.jsonl'))

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logger = logging.getLogger('songsurf')

_ah = logging.FileHandler(LOG_DIR / 'activity.log', encoding='utf-8')
_ah.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
activity_logger = logging.getLogger('songsurf.activity')
activity_logger.addHandler(_ah)
activity_logger.propagate = False
activity_logger.setLevel(logging.INFO)

_dlh = logging.FileHandler(LOG_DIR / 'downloads.log', encoding='utf-8')
_dlh.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
dl_logger = logging.getLogger('songsurf.downloads')
dl_logger.addHandler(_dlh)
dl_logger.propagate = False
dl_logger.setLevel(logging.INFO)

# ── URL validation ─────────────────────────────────────────────────────────────

_ALLOWED_YT_DOMAINS = ('youtube.com', 'music.youtube.com', 'www.youtube.com', 'youtu.be')


def _is_valid_youtube_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith('https://'):
        return False
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.lower()
        host = netloc[4:] if netloc.startswith('www.') else netloc
    except Exception:
        return False
    if host not in _ALLOWED_YT_DOMAINS and netloc not in _ALLOWED_YT_DOMAINS:
        return False
    if re.search(r'[<>\'";{}\\`]', url):
        return False
    return True


# ── Downloader (global, uses TEMP_DIR for staging) ────────────────────────────

downloader = YouTubeDownloader(TEMP_DIR, BASE_MUSIC_DIR)

# ── Download queue ─────────────────────────────────────────────────────────────

MAX_QUEUE_SIZE = 50
download_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
queue_lock     = threading.Lock()
cancel_flag    = threading.Event()

download_status = {
    'in_progress': False,
    'current_download': None,
    'last_completed': None,
    'last_error': None,
    'progress': None,
    'queue_size': 0,
    'batch_active': False,
    'batch_total': 0,
    'batch_done': 0,
    'batch_percent': 0,
}

# Items submitted via Chrome extension — held here until the frontend UrlQueue picks them up
extension_pending    = []
extension_pending_lk = threading.Lock()

# ── Daily download counter ─────────────────────────────────────────────────────
_daily_lock  = threading.Lock()
_daily_count = 0
_daily_date  = None  # date object; reset on new calendar day


def _daily_reset_if_needed():
    """Must be called under _daily_lock. Resets counter on new day."""
    global _daily_count, _daily_date
    today = datetime.now().date()
    if _daily_date != today:
        _daily_count = 0
        _daily_date  = today


def _daily_limit_reached() -> bool:
    if DAILY_DOWNLOAD_LIMIT <= 0:
        return False
    with _daily_lock:
        _daily_reset_if_needed()
        return _daily_count >= DAILY_DOWNLOAD_LIMIT


def _daily_increment():
    global _daily_count
    with _daily_lock:
        _daily_reset_if_needed()
        _daily_count += 1


def _start_or_extend_batch(added_count: int):
    if added_count <= 0:
        return
    with queue_lock:
        if not download_status.get('batch_active'):
            download_status['batch_active'] = True
            download_status['batch_total'] = 0
            download_status['batch_done'] = 0
            download_status['batch_percent'] = 0
        download_status['batch_total'] += added_count


# ── Prefetch ───────────────────────────────────────────────────────────────────

admin_prefetch_lock  = threading.Lock()
admin_prefetch_state = {'token': '', 'status': 'idle', 'file_path': '', 'updated_at': ''}


def _prefetch_cleanup_file(file_path: str):
    if not file_path:
        return
    try:
        p = Path(file_path)
        if p.exists() and p.is_file():
            p.unlink()
        stem = p.with_suffix('')
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            side = Path(str(stem) + ext)
            if side.exists():
                side.unlink()
    except Exception as e:
        logger.warning(f"⚠️ Prefetch cleanup: {e}")


def _prefetch_first_playlist_song_async(dl, playlist_meta, on_done=None):
    songs = (playlist_meta or {}).get('songs') or []
    if not songs:
        return
    first = songs[0] or {}
    first_url = (first.get('url') or '').strip()
    if not first_url:
        return
    metadata = {
        'artist': first.get('artist', (playlist_meta or {}).get('artist', 'Unknown Artist')),
        'album':  (playlist_meta or {}).get('title', 'Unknown Album'),
        'title':  first.get('title', 'Unknown Title'),
        'year':   (playlist_meta or {}).get('year', ''),
    }

    def _job():
        result = dl.prefetch_first_track(first_url, metadata)
        if callable(on_done):
            try:
                on_done(result)
            except Exception as e:
                logger.warning(f"⚠️ Prefetch callback: {e}")

    threading.Thread(target=_job, daemon=True).start()


def _start_admin_prefetch(dl, playlist_meta) -> str:
    token = secrets.token_urlsafe(16)
    with admin_prefetch_lock:
        old_file = admin_prefetch_state.get('file_path', '')
        admin_prefetch_state.update({
            'token': token, 'status': 'pending',
            'file_path': '', 'updated_at': datetime.now().isoformat()
        })
    if old_file:
        _prefetch_cleanup_file(old_file)

    def _done(result):
        file_path = (result or {}).get('file_path', '') if (result or {}).get('success') else ''
        with admin_prefetch_lock:
            if admin_prefetch_state.get('token') != token:
                if file_path:
                    _prefetch_cleanup_file(file_path)
                return
            admin_prefetch_state['status'] = 'ready' if file_path else 'failed'
            admin_prefetch_state['file_path'] = file_path
            admin_prefetch_state['updated_at'] = datetime.now().isoformat()

    _prefetch_first_playlist_song_async(dl, playlist_meta, on_done=_done)
    return token


def _cancel_admin_prefetch(token='') -> bool:
    with admin_prefetch_lock:
        current = admin_prefetch_state.get('token', '')
        if token and current and token != current:
            return False
        file_path = admin_prefetch_state.get('file_path', '')
        admin_prefetch_state.update({
            'token': '', 'status': 'idle',
            'file_path': '', 'updated_at': datetime.now().isoformat()
        })
    if file_path:
        _prefetch_cleanup_file(file_path)
    return True


# ── Per-user storage ───────────────────────────────────────────────────────────

user_zip_state = {}  # {sub: {'zip_path': str, 'count': int, 'size_mb': float}}
user_zip_lock  = threading.Lock()


ADMIN_PSEUDO = os.getenv('ADMIN_PSEUDO', 'rev0admin')


def _user_pseudo(user: dict) -> str:
    """Derive a filesystem-safe pseudo from a user dict.

    Uses the part before '@' in the email, falls back to sub.
    '_pseudo' key is accepted as a pre-computed override (used by queue worker).
    Admin role always maps to ADMIN_PSEUDO so the folder is stable regardless of email.
    """
    if user.get('_pseudo'):
        return user['_pseudo']
    if user.get('role') == 'admin' and ADMIN_PSEUDO:
        return ADMIN_PSEUDO
    email = (user.get('email') or '').strip().lower()
    if email and '@' in email:
        raw = email.split('@')[0]
    else:
        raw = (user.get('sub') or 'user')
    pseudo = re.sub(r'[^a-z0-9._-]', '_', raw)
    return pseudo.strip('._-') or 'user'


def _user_music_dir(user: dict) -> Path:
    """Return the music directory for a user.

    DEV_MODE  → BASE_MUSIC_DIR  (flat: Artist/Album/)
    Production → BASE_MUSIC_DIR/<pseudo>/  (per-user: pseudo/Artist/Album/)
    """
    if DEV_MODE:
        BASE_MUSIC_DIR.mkdir(parents=True, exist_ok=True)
        return BASE_MUSIC_DIR
    pseudo = _user_pseudo(user)
    d = (BASE_MUSIC_DIR / pseudo).resolve()
    if not d.is_relative_to(BASE_MUSIC_DIR.resolve()):
        raise ValueError(f"Invalid pseudo — path escapes music dir: {pseudo!r}")
    d.mkdir(parents=True, exist_ok=True)
    return d



def _sync_mp3_tags(file_path: Path, music_dir: Path) -> None:
    """Updates TPE1/TALB tags to match the file's actual folder position.

    Structure assumed:
      Artist/Album/song.mp3  →  artist=parts[0], album=parts[1]
      Album/song.mp3         →  album=parts[0]  (playlist mode)
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
        from mutagen.id3 import ID3, TPE1, TALB
        audio = MP3(file_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        if artist:
            audio.tags['TPE1'] = TPE1(encoding=3, text=artist)
        audio.tags['TALB'] = TALB(encoding=3, text=album)
        audio.save()
    except Exception as e:
        logger.warning(f"⚠️ sync_mp3_tags({file_path.name}): {e}")


# ── Authentication ─────────────────────────────────────────────────────────────

def _get_current_user() -> dict | None:
    """
    Returns user identity from Watcher-injected headers.
    - WATCHER_SECRET set   → require X-Watcher-Token match
    - WATCHER_SECRET unset + DEV_MODE → dev user (standalone testing)
    - Otherwise            → None
    """
    if WATCHER_SECRET:
        if not hmac.compare_digest(
            request.headers.get('X-Watcher-Token', ''),
            WATCHER_SECRET,
        ):
            return None
        return {
            'sub':   request.headers.get('X-User-Id', ''),
            'role':  request.headers.get('X-User-Role', 'member').lower(),
            'email': request.headers.get('X-User-Email', ''),
        }
    if DEV_MODE:
        return _DEV_USER.copy()
    return None


def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user or not user.get('sub'):
            if request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'success': False, 'error': 'Non authentifié'}), 401
            return 'Service unavailable', 503
        return f(*args, **kwargs)
    return decorated


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


@app.route('/_app/<path:filename>')
def svelte_assets(filename):
    """Serve SvelteKit's generated JS/CSS bundles (no auth needed)."""
    return send_from_directory(_FRONTEND_BUILD / '_app', filename)


@app.route('/<path:filename>')
def static_assets(filename):
    """Serve top-level static files copied from SvelteKit's static/ dir
    (fonts, help/ tutorial images, favicon…). Public assets — no auth.
    Only real files are served; unknown paths 404 (SPA page routes are
    handled client-side, so a direct hit on e.g. /metadata still 404s as
    before). This catch-all is the least specific rule, so explicit API /
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
@auth_required
def get_status():
    with queue_lock:
        status = download_status.copy()
        status['queue_size'] = download_queue.qsize()
        current_pct = 0
        if status['in_progress']:
            status['progress'] = downloader.get_progress()
            phase   = status['progress'].get('phase', '')
            raw_pct = max(0, min(100, int(status['progress'].get('percent', 0))))
            # Map phase → weighted percent: download=0-50, converting=55, organizing=90, completed=100
            if phase == 'converting':
                current_pct = 55
            elif phase == 'organizing':
                current_pct = 90
            elif phase == 'completed':
                current_pct = 100
            else:  # downloading or unknown
                current_pct = int(raw_pct * 0.5)
        if status.get('batch_active'):
            total    = max(1, int(status.get('batch_total', 0) or 0))
            done     = max(0, min(total, int(status.get('batch_done', 0) or 0)))
            composed = ((done + (current_pct / 100.0 if status['in_progress'] else 0.0)) / total) * 100.0
            status['batch_percent'] = round(max(0.0, min(100.0, composed)), 1)
        else:
            status['batch_percent'] = float(current_pct)
    with extension_pending_lk:
        status['extension_pending_count'] = len(extension_pending)
    with _daily_lock:
        _daily_reset_if_needed()
        status['daily_count'] = _daily_count
    status['daily_limit'] = DAILY_DOWNLOAD_LIMIT
    current_user = _get_current_user()
    current_dl = status.get('current_download') or {}
    status['is_mine'] = (
        not current_dl or
        current_dl.get('user_sub') == (current_user or {}).get('sub')
    )
    # Diagnostic cookies (vidéos restreintes par âge) — exposé pour l'UI/debug.
    try:
        status['cookies_present'] = _COOKIES_FILE.is_file()
        status['cookies_age_days'] = (
            round((time.time() - _COOKIES_FILE.stat().st_mtime) / 86400, 1)
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

        shutil.move(str(src), str(target))
        _sync_mp3_tags(target, music_dir)
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

        for mp3 in dst.rglob('*.mp3'):
            _sync_mp3_tags(mp3, music_dir)

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

        logger.info(f"🗑️ Dossier supprimé: {folder_path} ({deleted_songs} titre(s)) par {user.get('email')}")
        return jsonify({'success': True, 'deleted_songs': deleted_songs})
    except Exception as e:
        logger.error(f"❌ /api/library/delete-folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
                return send_file(p, mimetype=mime)

        mp3s = sorted(folder.rglob('*.mp3'), key=lambda p: p.name.lower())
        if not mp3s:
            return '', 204

        audio = MP3(mp3s[0])
        tags  = getattr(audio, 'tags', None)
        if tags:
            for frame in tags.values():
                if isinstance(frame, APIC) and getattr(frame, 'data', None):
                    return send_file(io.BytesIO(frame.data), mimetype=frame.mime or 'image/jpeg')
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
                return send_file(p, mimetype=mime)
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
        data = request.get_json()
        url  = (data.get('url') or '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL invalide. Collez un lien YouTube Music valide.'}), 400

        is_playlist = downloader._detect_type(url) == 'playlist'
        if is_playlist:
            result = downloader.extract_playlist_metadata(url)
            if result.get('success'):
                result['is_playlist'] = True
                result['prefetch_token'] = _start_admin_prefetch(downloader, result)
        else:
            _cancel_admin_prefetch('')
            result = downloader.extract_metadata(url)
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
        # La file serveur draine séquentiellement, indépendamment de la page : on
        # accepte d'empiler tant que la file n'est pas pleine (bug « ça bloque si
        # on quitte la page Téléchargement »).
        if download_queue.full():
            return jsonify({'success': False, 'error': 'File pleine, réessaie dans un instant.'}), 429
        if _daily_limit_reached():
            return jsonify({'success': False, 'error': f'Limite journalière atteinte ({DAILY_DOWNLOAD_LIMIT} titres/jour).'}), 429

        metadata = {
            'artist':       data.get('artist', 'Unknown Artist'),
            'artists':      data.get('artists') or [],
            'album_artist': data.get('album_artist', ''),
            'album':        data.get('album',  'Unknown Album'),
            'title':        data.get('title',  'Unknown Title'),
            'year':         data.get('year',   ''),
            'track_number': data.get('track_number', ''),
        }
        download_queue.put({
            'url':         url,
            'metadata':    metadata,
            'user_sub':    user['sub'],
            'user_role':   user.get('role', 'member'),
            'user_pseudo': _user_pseudo(user),
            'added_at':    datetime.now().isoformat(),
        })
        _start_or_extend_batch(1)
        logger.info(f"➕ Queue: {metadata['artist']} - {metadata['title']} [{_user_pseudo(user)}]")
        return jsonify({'success': True, 'queue_size': download_queue.qsize()})
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
        # File serveur drainée séquentiellement : on empile même si un batch tourne
        # déjà (le worker enchaîne sans dépendre de la page ouverte).
        if download_queue.full():
            return jsonify({'success': False, 'error': 'File pleine, réessaie dans un instant.'}), 429
        if _daily_limit_reached():
            return jsonify({'success': False, 'error': f'Limite journalière atteinte ({DAILY_DOWNLOAD_LIMIT} titres/jour).'}), 429

        added = 0
        for song in songs:
            if download_queue.full():
                break
            metadata = {
                'artist':       playlist.get('artist') or song.get('artist') or 'Unknown Artist',
                'artists':      song.get('artists') or [],
                'album_artist': playlist.get('artist') or '',
                'album':        playlist.get('title', 'Unknown Album'),
                'title':        song['title'],
                'year':         playlist.get('year', ''),
                'track_number': song.get('track_number', ''),
                'track_total':  len(songs),
            }
            download_queue.put({
                'url':         song['url'],
                'metadata':    metadata,
                'user_sub':    user['sub'],
                'user_role':   user.get('role', 'member'),
                'user_pseudo': _user_pseudo(user),
                'added_at':    datetime.now().isoformat(),
            })
            added += 1

        _start_or_extend_batch(added)
        return jsonify({'success': True, 'added': added, 'total': len(songs), 'queue_size': download_queue.qsize()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── ZIP ────────────────────────────────────────────────────────────────────────

@app.route('/api/prepare-zip', methods=['POST'])
@auth_required
def prepare_zip():
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user)
        files = sorted([p for p in music_dir.rglob('*.mp3') if p.is_file()],
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return jsonify({'success': False, 'error': 'Aucune musique disponible'}), 404

        zip_path = TEMP_DIR / f"songsurf_{user['sub'][:16]}.zip"
        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, f.relative_to(music_dir))

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        with user_zip_lock:
            user_zip_state[user['sub']] = {
                'zip_path': str(zip_path),
                'count':    len(files),
                'size_mb':  round(size_mb, 1),
            }

        logger.info(f"📦 ZIP prêt: {len(files)} fichiers, {size_mb:.1f} MB [{user['sub'][:8]}]")
        return jsonify({
            'success':      True,
            'count':        len(files),
            'size_mb':      round(size_mb, 1),
            'download_url': '/api/download-zip',
        })
    except Exception as e:
        logger.error(f"❌ /api/prepare-zip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download-zip')
@auth_required
def download_zip():
    user = _get_current_user()
    with user_zip_lock:
        state = user_zip_state.get(user['sub'])
    if not state:
        return jsonify({'success': False, 'error': 'ZIP non prêt, utilisez /api/prepare-zip'}), 404

    zip_path = Path(state['zip_path'])
    if not zip_path.exists():
        return jsonify({'success': False, 'error': 'ZIP introuvable'}), 404

    _sub      = user['sub']
    _is_admin = user.get('role') == 'admin'
    _pseudo   = _user_pseudo(user)
    _role     = user.get('role', '')
    _zip_meta = {'count': state.get('count', 0), 'size_mb': state.get('size_mb', 0)}
    music_dir = _user_music_dir(user)
    file_size = zip_path.stat().st_size

    def _stream_and_cleanup():
        try:
            with open(zip_path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk
        finally:
            # Appelé par le WSGI quand le stream est terminé (ou connexion coupée)
            try:
                zip_path.unlink(missing_ok=True)
                with user_zip_lock:
                    user_zip_state.pop(_sub, None)
                # Bibliothèque membre = temporaire, supprimée après export.
                # La bibliothèque admin est persistante : jamais supprimée.
                if not _is_admin and music_dir != BASE_MUSIC_DIR and music_dir.exists():
                    shutil.rmtree(music_dir, ignore_errors=True)
                    logger.info(f"🗑️ Bibliothèque supprimée post-ZIP [{_sub[:8]}]")
                events_client.emit(
                    'zip_export',
                    pseudo=_pseudo,
                    role=_role,
                    detail={**_zip_meta, 'library_purged': not _is_admin},
                )
            except Exception as e:
                logger.warning(f"⚠️ Post-download cleanup: {e}")

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
    limit  = min(max(1, int(request.args.get('limit', '100'))), 500)

    log_path = LOG_DIR / 'downloads.log'
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
    return jsonify({'success': True, 'entries': entries[:limit], 'total': len(entries)})


# ── Admin-only utilities ───────────────────────────────────────────────────────

@app.route('/api/admin/extract-covers', methods=['POST'])
@auth_required
def admin_extract_covers():
    try:
        user = _get_current_user()
        if user.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Admin requis'}), 403
        data      = request.get_json(silent=True) or {}
        music_dir = _user_music_dir(user)
        org       = MusicOrganizer(music_dir)
        result    = org.extract_album_covers(overwrite=bool(data.get('overwrite', False)))
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Audit métadonnées + backfill genre (admin) ────────────────────────────────

_backfill_lock  = threading.Lock()
_backfill_state = {'status': 'idle', 'total': 0, 'done': 0, 'updated': 0,
                   'failed': 0, 'last_file': '', 'started_at': '', 'finished_at': ''}


@app.route('/api/admin/audit/artist')
@auth_required
def admin_audit_artist():
    """Rapport iTunes + cohérence ID3 pour tous les albums d'un artiste."""
    try:
        user = _get_current_user()
        if user.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Admin requis'}), 403
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
        logger.error(f"❌ /api/admin/audit/artist: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/audit/apply', methods=['POST'])
@auth_required
def admin_audit_apply():
    """Applique les recommandations cochées : [{path, field, value}]."""
    try:
        user = _get_current_user()
        if user.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Admin requis'}), 403
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
        logger.error(f"❌ /api/admin/audit/apply: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/genre-backfill', methods=['POST'])
@auth_required
def admin_genre_backfill():
    """Lance le backfill TCON de la bibliothèque admin (thread d'arrière-plan)."""
    try:
        user = _get_current_user()
        if user.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Admin requis'}), 403

        with _backfill_lock:
            if _backfill_state['status'] == 'running':
                return jsonify({'success': False, 'error': 'Backfill déjà en cours'}), 409
            _backfill_state.update({
                'status': 'running', 'total': 0, 'done': 0, 'updated': 0,
                'failed': 0, 'last_file': '',
                'started_at': datetime.now().isoformat(), 'finished_at': '',
            })

        music_dir = _user_music_dir(user)

        def _job():
            from library_audit import backfill_genres
            try:
                backfill_genres(music_dir, _backfill_state, _backfill_lock)
            except Exception as e:
                logger.error(f"❌ Backfill genres: {e}")
                with _backfill_lock:
                    _backfill_state['status'] = 'error'
                    _backfill_state['error']  = str(e)
            finally:
                with _backfill_lock:
                    _backfill_state['finished_at'] = datetime.now().isoformat()

        threading.Thread(target=_job, daemon=True).start()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/admin/genre-backfill: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/genre-backfill/status')
@auth_required
def admin_genre_backfill_status():
    user = _get_current_user()
    if user.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Admin requis'}), 403
    with _backfill_lock:
        return jsonify({'success': True, **_backfill_state})


# ── Prefetch routes ────────────────────────────────────────────────────────────

@app.route('/api/prefetch/cover')
@auth_required
def admin_prefetch_cover():
    token = (request.args.get('token') or '').strip()
    if not token:
        return '', 204
    with admin_prefetch_lock:
        if token != admin_prefetch_state.get('token') or admin_prefetch_state.get('status') != 'ready':
            return '', 204
        file_path = admin_prefetch_state.get('file_path', '')
    if not file_path:
        return '', 204
    p = Path(file_path)
    if not p.exists():
        return '', 204
    try:
        audio = MP3(p)
        tags  = getattr(audio, 'tags', None)
        if tags:
            for frame in tags.values():
                if isinstance(frame, APIC) and getattr(frame, 'data', None):
                    return send_file(io.BytesIO(frame.data), mimetype=frame.mime or 'image/jpeg')
    except Exception as e:
        logger.warning(f"⚠️ Prefetch cover: {e}")
    stem = p.with_suffix('')
    for ext, mime in (('.jpg', 'image/jpeg'), ('.jpeg', 'image/jpeg'), ('.png', 'image/png'), ('.webp', 'image/webp')):
        side = Path(str(stem) + ext)
        if side.exists():
            return send_file(side, mimetype=mime)
    return '', 204


@app.route('/api/prefetch/cancel', methods=['POST'])
@auth_required
def admin_prefetch_cancel():
    try:
        data  = request.get_json(silent=True) or {}
        token = (data.get('token') or '').strip()
        ok    = _cancel_admin_prefetch(token)
        return jsonify({'success': ok}), 200 if ok else 409
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Extension Chrome — cookies sync ───────────────────────────────────────────

_COOKIES_FILE = Path(os.environ.get('YTDLP_COOKIES', '/data/cookies.txt'))

@app.route('/api/cookies/update', methods=['POST'])
@auth_required
def update_cookies():
    """Extension Chrome — reçoit les cookies YouTube et les écrit pour yt-dlp."""
    try:
        data    = request.get_json(silent=True) or {}
        content = (data.get('cookies') or '').strip()
        if not content:
            return jsonify({'success': False, 'error': 'Cookies manquants'}), 400
        _COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        _COOKIES_FILE.write_text(content, encoding='utf-8')
        count = sum(1 for l in content.splitlines() if l and not l.startswith('#'))
        logger.info(f"🍪 Cookies mis à jour depuis l'extension Chrome ({count} entrées)")
        return jsonify({'success': True, 'count': count})
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
    Extension Chrome — extrait les métadonnées sans effet de bord (pas de prefetch).
    Utilisé pour la mini-analyse avant confirmation.
    """
    try:
        data     = request.get_json(silent=True) or {}
        url      = (data.get('url') or '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL invalide'}), 400

        url_mode = _detect_url_mode(url)

        if url_mode == 'song':
            result = downloader.extract_metadata(url)
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
            result = downloader.extract_playlist_metadata(url)
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
    try:
        if url_mode == 'song':
            if override and override.get('title'):
                metadata = {
                    'artist': override.get('artist', 'Unknown Artist') or 'Unknown Artist',
                    'album':  override.get('album',  'Unknown Album')  or 'Unknown Album',
                    'title':  override.get('title',  'Unknown Title')  or 'Unknown Title',
                    'year':   override.get('year',   ''),
                }
            else:
                result = downloader.extract_metadata(url)
                if not result.get('success'):
                    logger.warning(f"⚠️ queue-direct extract failed: {result.get('error')}")
                    return
                meta = result.get('metadata', {})
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
            if not download_queue.full():
                download_queue.put({
                    'url':         url,
                    'metadata':    metadata,
                    'user_sub':    user['sub'],
                    'user_role':   user.get('role', 'member'),
                    'user_pseudo': _user_pseudo(user),
                    'added_at':    datetime.now().isoformat(),
                })
                _start_or_extend_batch(1)
                logger.info(f"📥 queue-direct (song): {metadata['artist']} — {metadata['title']}")
        else:
            result = downloader.extract_playlist_metadata(url)
            if not result.get('success'):
                logger.warning(f"⚠️ queue-direct playlist extract failed: {result.get('error')}")
                return
            songs       = result.get('songs', [])
            album_name  = (override or {}).get('album')  or result.get('title', 'Unknown Album')
            artist_name = (override or {}).get('artist') or result.get('artist', 'Unknown Artist')
            added = 0
            for song in songs:
                if download_queue.full():
                    break
                metadata = {
                    'artist':       artist_name,
                    'artists':      song.get('artists') or [],
                    'album_artist': artist_name,
                    'album':        album_name,
                    'title':        song.get('title', 'Unknown Title'),
                    'year':         result.get('year', ''),
                    'track_number': song.get('track_number', ''),
                    'track_total':  len(songs),
                }
                download_queue.put({
                    'url':         song['url'],
                    'metadata':    metadata,
                    'user_sub':    user['sub'],
                    'user_role':   user.get('role', 'member'),
                    'user_pseudo': _user_pseudo(user),
                    'added_at':    datetime.now().isoformat(),
                })
                added += 1
            _start_or_extend_batch(added)
            logger.info(f"📥 queue-direct ({url_mode}): {added} titres — {album_name} / {artist_name}")
    except Exception as e:
        logger.error(f"❌ queue-direct async: {e}")


@app.route('/api/queue-direct', methods=['POST'])
@auth_required
def queue_direct():
    """
    Extension Chrome — stocke l'URL dans extension_pending ; le frontend UrlQueue
    la récupère via /api/extension-queue/consume et la traite dans sa file visuelle.
    """
    try:
        data = request.get_json(silent=True) or {}
        url  = (data.get('url') or '').strip()

        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL invalide'}), 400

        url_mode = _detect_url_mode(url)
        item = {
            'url':      url,
            'url_mode': url_mode,
            'artist':   (data.get('artist') or '').strip(),
            'album':    (data.get('album')  or '').strip(),
            'title':    (data.get('title')  or '').strip(),
            'year':     (data.get('year')   or '').strip(),
        }
        with extension_pending_lk:
            if len(extension_pending) >= MAX_QUEUE_SIZE:
                return jsonify({'success': False, 'error': 'Queue pleine'}), 429
            extension_pending.append(item)

        labels = {'song': 'chanson', 'album': 'album', 'playlist': 'playlist'}
        return jsonify({'success': True, 'type': url_mode, 'label': labels.get(url_mode, url_mode)})
    except Exception as e:
        logger.error(f"❌ /api/queue-direct: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extension-queue/consume', methods=['POST'])
@auth_required
def extension_queue_consume():
    """Frontend UrlQueue — récupère et vide les items en attente de l'extension."""
    with extension_pending_lk:
        items = list(extension_pending)
        extension_pending.clear()
    return jsonify({'success': True, 'items': items})


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
    """Tracklist légère d'un album (titre + TRCK) pour le mode « Numéroter »."""
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
            })
        return jsonify({'success': True, 'tracks': items})
    except Exception as e:
        logger.error(f"❌ /api/library/album-tracks: {e}")
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

        from library_audit import _read_tags
        albums = []
        for album_dir in sorted([d for d in folder.iterdir() if d.is_dir()],
                                key=lambda p: p.name.lower()):
            mp3s = [f for f in album_dir.iterdir()
                    if f.is_file() and f.suffix.lower() == '.mp3']
            if not mp3s:
                continue
            missing = {'genre': 0, 'year': 0, 'track_number': 0}
            for f in mp3s:
                tags = _read_tags(f)
                if not tags['genres']:
                    missing['genre'] += 1
                if not tags['year']:
                    missing['year'] += 1
                if not tags['track_number']:
                    missing['track_number'] += 1
            albums.append({
                'path':     str(album_dir.relative_to(music_dir)),
                'name':     album_dir.name,
                'tracks':   len(mp3s),
                'missing':  missing,
                'complete': not any(missing.values()),
            })
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
    """
    try:
        user      = _get_current_user()
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


# ── Cookies / vidéos restreintes (âge, connexion requise) ──────────────────────

_AGE_COOKIE_MARKERS = (
    'confirm your age',
    'sign in to confirm',
    'inappropriate for some users',
    'cookies-from-browser',
    'use --cookies',
    "confirm you're not a bot",
    'confirm you’re not a bot',
)


def _is_cookie_error(msg: str) -> bool:
    """Vrai si l'erreur yt-dlp réclame des cookies (âge / connexion / anti-bot)."""
    m = (msg or '').lower()
    return any(marker in m for marker in _AGE_COOKIE_MARKERS)


def _cookies_diagnostic() -> str:
    """État du fichier cookies pour les logs : présence + nb d'entrées + âge."""
    try:
        if not _COOKIES_FILE.is_file():
            return f"cookies ABSENTS ({_COOKIES_FILE})"
        age_days = (time.time() - _COOKIES_FILE.stat().st_mtime) / 86400
        n = sum(1 for l in _COOKIES_FILE.read_text(encoding='utf-8', errors='ignore').splitlines()
                if l and not l.startswith('#'))
        return f"cookies présents ({n} entrées, {age_days:.1f} j)"
    except Exception as e:
        return f"cookies état inconnu ({e})"


def _friendly_download_error(msg: str) -> str:
    """Traduit les erreurs yt-dlp obscures en message actionnable pour l'utilisateur."""
    if _is_cookie_error(msg):
        return ("Vidéo restreinte (âge ou connexion requise). Resynchronise tes "
                "cookies YouTube via l'extension Chrome, puis relance le téléchargement.")
    return msg


# ── Queue worker ───────────────────────────────────────────────────────────────

def queue_worker():
    logger.info("🔄 Queue worker démarré")
    while True:
        try:
            item = download_queue.get()
            if item is None:
                break

            url         = item['url']
            metadata    = item['metadata']
            user_sub    = item.get('user_sub', 'dev-user-local')
            user_pseudo = item.get('user_pseudo', '')
            cancel_flag.clear()

            music_dir = _user_music_dir({'sub': user_sub, '_pseudo': user_pseudo})
            org       = MusicOrganizer(music_dir)

            with queue_lock:
                download_status.update({
                    'in_progress':      True,
                    'current_download': {
                        'url': url, 'metadata': metadata,
                        'user_sub': user_sub,
                        'started_at': datetime.now().isoformat()
                    },
                    'last_error': None,
                })

            logger.info(f"🎵 {metadata['artist']} - {metadata['title']} [{user_sub[:8]}]")

            try:
                # Court-circuit doublon : si le titre est déjà en bibliothèque,
                # on ne télécharge même pas (économie de bande passante / quota).
                if org.target_exists(metadata):
                    logger.info(f"⏭️ Doublon ignoré (pas de download): {metadata.get('artist')} - {metadata.get('title')}")
                    org_result = {'success': True, 'skipped': True, 'final_path': ''}
                else:
                    result = downloader.download(url, metadata)

                    if cancel_flag.is_set():
                        raise Exception("Annulé par l'utilisateur")
                    if not result['success']:
                        raise Exception(result.get('error', 'Erreur inconnue'))

                    # Genre iTunes (admin uniquement) — échec silencieux, jamais bloquant.
                    if item.get('user_role') == 'admin' and not metadata.get('genres'):
                        metadata['genres'] = lookup_genres(
                            metadata.get('artist', ''),
                            metadata.get('title', ''),
                            metadata.get('album', ''),
                        )

                    org_result = org.organize(result['file_path'], metadata)
                    if not org_result['success']:
                        raise Exception(org_result.get('error', 'Erreur organisation'))

                downloader.progress.phase   = 'completed'
                downloader.progress.percent = 100
                _skipped = bool(org_result.get('skipped'))

                with queue_lock:
                    download_status['in_progress']    = False
                    download_status['current_download'] = None
                    download_status['batch_done']     = int(download_status.get('batch_done', 0)) + 1
                    download_status['last_completed'] = {
                        'success':   True,
                        'skipped':   _skipped,
                        'file_path': org_result.get('final_path', ''),
                        'metadata':  metadata,
                        'timestamp': datetime.now().isoformat(),
                    }
                    if (download_status['batch_done'] >= download_status.get('batch_total', 0)
                            and download_queue.qsize() == 0):
                        download_status['batch_active'] = False

                # Un doublon ignoré ne compte pas comme téléchargement (quota, logs, events).
                if _skipped:
                    logger.info(f"✅ Doublon ignoré : {metadata.get('artist')} - {metadata.get('title')}")
                else:
                    logger.info(f"✅ {org_result['final_path']}")
                    _label = user_pseudo or user_sub[:8]
                    activity_logger.info(f"🎵 DOWNLOAD | {_label} | {metadata['artist']} - {metadata['title']}")
                    dl_logger.info(f"{_label} | {metadata['artist']} | {metadata.get('album', '')} | {metadata['title']}")
                    events_client.emit(
                        'download_success',
                        pseudo=_label,
                        artist=metadata.get('artist', ''),
                        album=metadata.get('album', ''),
                        title=metadata.get('title', ''),
                    )
                    _daily_increment()

            except Exception as e:
                err_msg  = str(e)
                friendly = _friendly_download_error(err_msg)
                if _is_cookie_error(err_msg):
                    logger.warning(f"🍪 Échec lié aux cookies/âge — {_cookies_diagnostic()}")
                logger.error(f"❌ {err_msg}")
                with queue_lock:
                    download_status['in_progress']    = False
                    download_status['current_download'] = None
                    download_status['batch_done']     = int(download_status.get('batch_done', 0)) + 1
                    download_status['last_error']     = {
                        'error': friendly, 'metadata': metadata,
                        'timestamp': datetime.now().isoformat(),
                    }
                    if (download_status['batch_done'] >= download_status.get('batch_total', 0)
                            and download_queue.qsize() == 0):
                        download_status['batch_active'] = False
                events_client.emit(
                    'download_failed',
                    pseudo=user_pseudo or user_sub[:8],
                    artist=(metadata or {}).get('artist', ''),
                    album=(metadata or {}).get('album', ''),
                    title=(metadata or {}).get('title', ''),
                    detail={'error': err_msg[:300]},
                )

            download_queue.task_done()

        except Exception as e:
            logger.error(f"❌ Worker error: {e}")
            time.sleep(1)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    flask_port = int(os.getenv('FLASK_PORT', '8081'))
    if WATCHER_SECRET:
        mode = "Watcher"
    elif DEV_MODE:
        mode = "DEV (standalone, no Watcher)"
    else:
        mode = "LOCKED (set DEV_MODE=true or WATCHER_SECRET)"

    logger.info(f"🎵 SongSurf démarré — port={flask_port}, mode={mode}, music={BASE_MUSIC_DIR}")
    events_client.start_replay_thread()
    threading.Thread(target=queue_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=flask_port, debug=False, use_reloader=False)
