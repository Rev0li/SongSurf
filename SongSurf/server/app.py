#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SongSurf — music download server

Auth model (Phase 2):
  - Watcher injects X-Watcher-Token + X-User-Id + X-User-Role + X-User-Email
  - SongSurf trusts these headers (no JWT validation here)
  - WATCHER_SECRET set   → require token match, then read user from headers
  - WATCHER_SECRET unset + DEV_MODE=true → inject dev user (standalone testing)

Storage: /data/music/<user_sub>/
  - Admin role: files never deleted
  - Member role: music folder deleted 60s after ZIP download

Phase 3: see documentation/CONNECTOR.md
"""

from flask import Flask, request, jsonify, send_file, send_from_directory
from pathlib import Path
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from mutagen.mp3 import MP3
from mutagen.id3 import APIC
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

from downloader import YouTubeDownloader
from organizer import MusicOrganizer

# ── Configuration ─────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

WATCHER_SECRET = os.getenv('WATCHER_SECRET', '')
DEV_MODE       = os.getenv('DEV_MODE', 'false').lower() == 'true'

DONATION_BTC = os.getenv('DONATION_BTC', '')
DONATION_ETH = os.getenv('DONATION_ETH', '')
DONATION_SOL = os.getenv('DONATION_SOL', '')
DONATION_XMR = os.getenv('DONATION_XMR', '')

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

DONATION_DIR = LOG_DIR / 'donations'

for _d in [BASE_MUSIC_DIR, TEMP_DIR, LOG_DIR, DONATION_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

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


def _user_music_dir(sub: str) -> Path:
    d = (BASE_MUSIC_DIR / sub).resolve()
    if not str(d).startswith(str(BASE_MUSIC_DIR.resolve())):
        raise ValueError(f"Invalid user sub — path escapes music dir: {sub!r}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_permanent(role: str) -> bool:
    return role == 'admin'


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
        if request.headers.get('X-Watcher-Token') != WATCHER_SECRET:
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


@app.route('/donation')
@auth_required
def donation_page():
    return _spa()


@app.route('/_app/<path:filename>')
def svelte_assets(filename):
    """Serve SvelteKit's generated JS/CSS bundles (no auth needed)."""
    return send_from_directory(_FRONTEND_BUILD / '_app', filename)


# ── User identity ──────────────────────────────────────────────────────────────

@app.route('/api/me')
@auth_required
def api_me():
    return jsonify(_get_current_user())


# ── Donation config ────────────────────────────────────────────────────────────

@app.route('/api/donation-config')
@auth_required
def api_donation_config():
    return jsonify({'btc': DONATION_BTC, 'eth': DONATION_ETH, 'sol': DONATION_SOL, 'xmr': DONATION_XMR})


@app.route('/api/donation/upload-coupon', methods=['POST'])
@auth_required
def donation_upload_coupon():
    try:
        coupon_code = (request.form.get('coupon_code') or '').strip()
        note        = (request.form.get('note') or '').strip()
        image       = request.files.get('coupon_image')

        if not coupon_code:
            return jsonify({'success': False, 'error': 'Code coupon requis'}), 400

        safe_code = re.sub(r'[^A-Za-z0-9\-_.]', '_', coupon_code)[:80]
        ext = '.jpg'
        if image is not None:
            src_name = secure_filename(image.filename or 'coupon')
            if '.' in src_name:
                ext_guess = '.' + src_name.rsplit('.', 1)[1].lower()
                if ext_guess in {'.jpg', '.jpeg', '.png', '.webp'}:
                    ext = ext_guess

        stamp    = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_name = f"coupon_{safe_code}_{stamp}_{secrets.token_hex(6)}{ext}"
        out_path = DONATION_DIR / out_name

        if image is not None:
            image.save(out_path)

        user = _get_current_user()
        meta = {
            'timestamp':   datetime.now().isoformat(),
            'coupon_code': coupon_code,
            'note':        note,
            'file_name':   out_name if image is not None else None,
            'role':        (user or {}).get('role', ''),
            'sub':         (user or {}).get('sub', ''),
            'ip':          request.headers.get('X-Forwarded-For', request.remote_addr or ''),
        }
        with open(DONATION_DIR / 'coupons.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(meta, ensure_ascii=False) + '\n')

        logger.info(f"💝 Coupon reçu: {coupon_code}")
        return jsonify({'success': True, 'message': 'Coupon reçu, merci ❤️'})
    except Exception as e:
        logger.error(f"❌ /api/donation/upload-coupon: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
    return jsonify(status)


# ── Library ────────────────────────────────────────────────────────────────────

def _build_library_tree(music_dir: Path) -> dict:
    artists = []
    playlists = []
    if not music_dir.exists():
        return {'artists': artists, 'playlists': playlists}
    for top in sorted([d for d in music_dir.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
        direct_songs = sorted(
            [f for f in top.iterdir() if f.is_file() and f.suffix.lower() in ('.mp3', '.mp4')],
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
                [f for f in album_dir.iterdir() if f.is_file() and f.suffix.lower() in ('.mp3', '.mp4')],
                key=lambda p: p.name.lower()
            )
            albums.append({
                'name':  album_dir.name,
                'path':  str(album_dir.relative_to(music_dir)),
                'songs': [{'name': s.name, 'path': str(s.relative_to(music_dir))} for s in songs],
            })
        artists.append({'name': top.name, 'path': str(top.relative_to(music_dir)), 'albums': albums})
    return {'artists': artists, 'playlists': playlists}


@app.route('/api/library')
@auth_required
def library_tree():
    try:
        user = _get_current_user()
        tree = _build_library_tree(_user_music_dir(user['sub']))
        return jsonify({'success': True, **tree})
    except Exception as e:
        logger.error(f"❌ /api/library: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/move', methods=['POST'])
@auth_required
def library_move_song():
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])
        data          = request.get_json() or {}
        source        = (data.get('source') or '').strip()
        target_folder = (data.get('target_folder') or '').strip()
        if not source or not target_folder:
            return jsonify({'success': False, 'error': 'source/target_folder requis'}), 400

        src     = (music_dir / source).resolve()
        dst_dir = (music_dir / target_folder).resolve()
        base    = music_dir.resolve()

        if not str(src).startswith(str(base)) or not str(dst_dir).startswith(str(base)):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not src.exists() or src.suffix.lower() not in ('.mp3', '.mp4'):
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


@app.route('/api/library/rename-folder', methods=['POST'])
@auth_required
def library_rename_folder():
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])
        data        = request.get_json() or {}
        folder_path = (data.get('folder_path') or '').strip()
        new_name    = (data.get('new_name') or '').strip()
        if not folder_path or not new_name:
            return jsonify({'success': False, 'error': 'folder_path/new_name requis'}), 400

        src = (music_dir / folder_path).resolve()
        if not str(src).startswith(str(music_dir.resolve())):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not src.exists() or not src.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        cleaned = ''.join(ch for ch in new_name if ch not in '<>:"/\\|?*').strip()
        if not cleaned:
            return jsonify({'success': False, 'error': 'Nom invalide'}), 400

        dst = src.parent / cleaned
        merged = False
        if dst.exists() and dst != src:
            # Merge: move all contents of src into dst
            for item in list(src.iterdir()):
                target = dst / item.name
                if target.exists():
                    counter = 1
                    stem = item.stem if item.is_file() else item.name
                    suffix = item.suffix if item.is_file() else ''
                    while target.exists():
                        if item.is_dir():
                            target = dst / f"{item.name} ({counter})"
                        else:
                            target = dst / f"{stem} ({counter}){suffix}"
                        counter += 1
                shutil.move(str(item), str(target))
            src.rmdir()
            merged = True
        elif dst != src:
            src.rename(dst)
        for mp3 in dst.rglob('*.mp3'):
            _sync_mp3_tags(mp3, music_dir)
        return jsonify({'success': True, 'new_path': str(dst.relative_to(music_dir)), 'merged': merged})
    except Exception as e:
        logger.error(f"❌ /api/library/rename-folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/move-folder', methods=['POST'])
@auth_required
def library_move_folder():
    """Move an album folder to a different artist folder."""
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])
        data        = request.get_json() or {}
        folder_path = (data.get('folder_path') or '').strip()
        new_parent  = (data.get('new_parent') or '').strip()
        if not folder_path or not new_parent:
            return jsonify({'success': False, 'error': 'folder_path/new_parent requis'}), 400

        src        = (music_dir / folder_path).resolve()
        dst_parent = (music_dir / new_parent).resolve()
        base       = music_dir.resolve()

        if not str(src).startswith(str(base)) or not str(dst_parent).startswith(str(base)):
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
    """Delete an artist or album folder and all its contents."""
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])
        data        = request.get_json() or {}
        folder_path = (data.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        target = (music_dir / folder_path).resolve()
        base   = music_dir.resolve()

        if not str(target).startswith(str(base) + os.sep):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404
        if not target.is_dir():
            return jsonify({'success': False, 'error': 'Cible n\'est pas un dossier'}), 400

        shutil.rmtree(str(target))

        parent = target.parent
        if parent != base and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/delete-folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/upload-image', methods=['POST'])
@auth_required
def library_upload_image():
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])
        target_folder = (request.form.get('target_folder') or '').strip()
        image         = request.files.get('image')
        if not target_folder:
            return jsonify({'success': False, 'error': 'Dossier cible requis'}), 400
        if image is None:
            return jsonify({'success': False, 'error': 'Fichier image requis'}), 400

        dst_dir = (music_dir / target_folder).resolve()
        if not str(dst_dir).startswith(str(music_dir.resolve())):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not dst_dir.exists() or not dst_dir.is_dir():
            return jsonify({'success': False, 'error': 'Dossier cible introuvable'}), 404

        filename = (image.filename or '').lower()
        ext = ''
        if '.' in filename:
            ext = '.' + filename.rsplit('.', 1)[1]
        if ext not in {'.jpg', '.jpeg', '.png', '.webp'}:
            ctype = (image.content_type or '').lower()
            if 'jpeg' in ctype or 'jpg' in ctype:
                ext = '.jpg'
            elif 'png' in ctype:
                ext = '.png'
            elif 'webp' in ctype:
                ext = '.webp'
            else:
                return jsonify({'success': False, 'error': 'Format non supporté (jpg, png, webp)'}), 400

        for old in ('folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp'):
            (dst_dir / old).unlink(missing_ok=True)

        out_path = dst_dir / f"folder{ext}"
        image.save(out_path)
        return jsonify({'success': True, 'path': str(out_path.relative_to(music_dir))})
    except Exception as e:
        logger.error(f"❌ /api/library/upload-image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/folder-cover')
@auth_required
def library_folder_cover():
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])
        folder_path = (request.args.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not str(folder).startswith(str(music_dir.resolve())):
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
    """Artist picture: looks for artist.jpg first, then folder images."""
    try:
        user        = _get_current_user()
        music_dir   = _user_music_dir(user['sub'])
        folder_path = (request.args.get('folder_path') or '').strip()
        folder      = (music_dir / folder_path).resolve()
        if not str(folder).startswith(str(music_dir.resolve())):
            return '', 204
        if not folder.exists() or not folder.is_dir():
            return '', 204
        for name, mime in (
            ('artist.jpg', 'image/jpeg'), ('artist.jpeg', 'image/jpeg'),
            ('artist.png', 'image/png'),  ('artist.webp', 'image/webp'),
            ('folder.jpg', 'image/jpeg'), ('folder.jpeg', 'image/jpeg'),
            ('folder.png', 'image/png'),  ('folder.webp', 'image/webp'),
        ):
            p = folder / name
            if p.exists():
                return send_file(p, mimetype=mime)
        return '', 204
    except Exception:
        return '', 204


@app.route('/api/library/song-meta/save', methods=['POST'])
@auth_required
def save_song_meta():
    """Writes editable ID3 tags back to an MP3 file."""
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
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])
        data      = request.get_json() or {}
        path      = (data.get('path') or '').strip()
        tags_data = data.get('tags') or {}

        target = (music_dir / path).resolve()
        if not str(target).startswith(str(music_dir.resolve())):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        audio = _MP3(target, ID3=_ID3)
        if audio.tags is None:
            audio.add_tags()

        for field, FrameClass in _FRAME_MAP.items():
            if field not in tags_data:
                continue
            v = str(tags_data[field]).strip()
            key = FrameClass.__name__
            if v:
                audio.tags[key] = FrameClass(encoding=3, text=[v])
            else:
                audio.tags.delall(key)

        # Handle comment separately (needs lang)
        if 'comment' in tags_data:
            audio.tags.delall('COMM')
            v = str(tags_data['comment']).strip()
            if v:
                audio.tags.add(COMM(encoding=3, lang='eng', desc='', text=[v]))

        audio.save()
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
        music_dir = _user_music_dir(user['sub'])
        path      = (request.form.get('path') or '').strip()
        file      = request.files.get('image')
        if not path or not file:
            return jsonify({'success': False, 'error': 'path et image requis'}), 400

        target = (music_dir / path).resolve()
        if not str(target).startswith(str(music_dir.resolve())):
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
        music_dir   = _user_music_dir(user['sub'])
        folder_path = (request.form.get('folder_path') or '').strip()
        file        = request.files.get('image')
        if not folder_path or not file:
            return jsonify({'success': False, 'error': 'folder_path et image requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not str(folder).startswith(str(music_dir.resolve())):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        mime = file.content_type or 'image/jpeg'
        ext  = '.jpg' if 'jpeg' in mime or 'jpg' in mime else '.png'
        with open(folder / f'artist{ext}', 'wb') as f:
            f.write(file.read())

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/artist-cover/upload: {e}")
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
        if download_status['in_progress'] or download_queue.qsize() > 0:
            return jsonify({'success': False, 'error': 'Un téléchargement est déjà en cours.'}), 429

        metadata = {
            'artist': data.get('artist', 'Unknown Artist'),
            'album':  data.get('album',  'Unknown Album'),
            'title':  data.get('title',  'Unknown Title'),
            'year':   data.get('year',   ''),
        }
        download_queue.put({
            'url':           url,
            'metadata':      metadata,
            'playlist_mode': bool(data.get('playlist_mode', False)),
            'mp4_mode':      bool(data.get('mp4_mode', False)),
            'user_sub':      user['sub'],
            'user_role':     user['role'],
            'added_at':      datetime.now().isoformat(),
        })
        _start_or_extend_batch(1)
        logger.info(f"➕ Queue: {metadata['artist']} - {metadata['title']} [{user['sub'][:8]}]")
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
        if download_status['in_progress'] or download_queue.qsize() > 0:
            return jsonify({'success': False, 'error': 'Un téléchargement est déjà en cours.'}), 429

        playlist_mode = bool(data.get('playlist_mode', False))
        mp4_mode      = bool(data.get('mp4_mode', False))
        added = 0
        for song in songs:
            if download_queue.full():
                break
            metadata = {
                'artist': playlist.get('artist') or song.get('artist') or 'Unknown Artist',
                'album':  playlist.get('title', 'Unknown Album'),
                'title':  song['title'],
                'year':   playlist.get('year', ''),
            }
            download_queue.put({
                'url':           song['url'],
                'metadata':      metadata,
                'playlist_mode': playlist_mode,
                'mp4_mode':      mp4_mode,
                'user_sub':      user['sub'],
                'user_role':     user['role'],
                'added_at':      datetime.now().isoformat(),
            })
            added += 1

        _start_or_extend_batch(added)
        return jsonify({'success': True, 'added': added, 'total': len(songs), 'queue_size': download_queue.qsize()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cancel', methods=['POST'])
@auth_required
def cancel_download():
    if not download_status['in_progress']:
        return jsonify({'success': False, 'error': 'Aucun téléchargement en cours'}), 400
    cancel_flag.set()
    return jsonify({'success': True})


@app.route('/api/cleanup', methods=['POST'])
@auth_required
def cleanup():
    deleted = []
    _cancel_admin_prefetch('')
    if TEMP_DIR.exists():
        for f in TEMP_DIR.iterdir():
            if f.is_file():
                f.unlink()
                deleted.append(f.name)
    with queue_lock:
        download_status.update({
            'in_progress': False, 'current_download': None, 'last_error': None,
            'batch_active': False, 'batch_total': 0, 'batch_done': 0, 'batch_percent': 0,
        })
    return jsonify({'success': True, 'deleted': len(deleted)})


# ── ZIP ────────────────────────────────────────────────────────────────────────

@app.route('/api/prepare-zip', methods=['POST'])
@auth_required
def prepare_zip():
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])
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

    permanent = _is_permanent(user['role'])
    _sub      = user['sub']

    def _maybe_cleanup():
        # Wait long enough for the browser to finish downloading before cleaning up.
        time.sleep(60)
        try:
            zip_path.unlink(missing_ok=True)
            with user_zip_lock:
                user_zip_state.pop(_sub, None)
            if not permanent:
                music_dir = BASE_MUSIC_DIR / _sub
                shutil.rmtree(music_dir, ignore_errors=True)
                logger.info(f"🧹 Member cleanup: dossier {_sub[:8]} supprimé")
        except Exception as e:
            logger.warning(f"⚠️ Cleanup après ZIP: {e}")

    threading.Thread(target=_maybe_cleanup, daemon=True).start()

    return send_file(
        zip_path,
        as_attachment=True,
        download_name='SongSurf_musiques.zip',
        mimetype='application/zip',
    )


# ── Admin-only utilities ───────────────────────────────────────────────────────

@app.route('/api/admin/extract-covers', methods=['POST'])
@auth_required
def admin_extract_covers():
    try:
        user = _get_current_user()
        if user.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Admin requis'}), 403
        data      = request.get_json(silent=True) or {}
        music_dir = _user_music_dir(user['sub'])
        org       = MusicOrganizer(music_dir)
        result    = org.extract_album_covers(overwrite=bool(data.get('overwrite', False)))
        return jsonify(result), 200 if result.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
                    'artist': (override or {}).get('artist') or meta.get('artist', 'Unknown Artist'),
                    'album':  (override or {}).get('album')  or meta.get('album',  'Unknown Album'),
                    'title':  meta.get('title', 'Unknown Title'),
                    'year':   meta.get('year', ''),
                }
            if not download_queue.full():
                download_queue.put({
                    'url': url, 'metadata': metadata,
                    'playlist_mode': False, 'mp4_mode': False,
                    'user_sub': user['sub'], 'user_role': user['role'],
                    'added_at': datetime.now().isoformat(),
                })
                _start_or_extend_batch(1)
                logger.info(f"📥 queue-direct (song): {metadata['artist']} — {metadata['title']}")
        else:
            result = downloader.extract_playlist_metadata(url)
            if not result.get('success'):
                logger.warning(f"⚠️ queue-direct playlist extract failed: {result.get('error')}")
                return
            songs         = result.get('songs', [])
            playlist_mode = (url_mode == 'playlist')
            album_name    = (override or {}).get('album')  or result.get('title', 'Unknown Album')
            artist_name   = (override or {}).get('artist') or result.get('artist', 'Unknown Artist')
            added = 0
            for song in songs:
                if download_queue.full():
                    break
                metadata = {
                    'artist': artist_name,
                    'album':  album_name,
                    'title':  song.get('title', 'Unknown Title'),
                    'year':   result.get('year', ''),
                }
                download_queue.put({
                    'url': song['url'], 'metadata': metadata,
                    'playlist_mode': playlist_mode, 'mp4_mode': False,
                    'user_sub': user['sub'], 'user_role': user['role'],
                    'added_at': datetime.now().isoformat(),
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
            'artist.jpg', 'artist.jpeg', 'artist.png', 'artist.webp',
            'folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp',
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
                    id3[label] = str(frame.text[0]) if hasattr(frame, 'text') else str(frame)
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
        music_dir = _user_music_dir(user['sub'])
        path      = (request.args.get('path') or '').strip()
        if not path:
            return jsonify({'success': False, 'error': 'path requis'}), 400

        target = (music_dir / path).resolve()
        if not str(target).startswith(str(music_dir.resolve())):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        return jsonify({'success': True, **_read_full_meta(target, music_dir)})
    except Exception as e:
        logger.error(f"❌ /api/library/song-meta: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/issues')
@auth_required
def library_issues():
    """Scans the library for MP3s with missing/unknown metadata fields."""
    try:
        user      = _get_current_user()
        music_dir = _user_music_dir(user['sub'])

        _UNKNOWN = {'', 'unknown artist', 'unknown album', 'unknown title', 'unknown'}

        issues = []
        for mp3 in sorted(music_dir.rglob('*.mp3'), key=lambda p: str(p).lower()):
            try:
                from mutagen.mp3 import MP3
                from mutagen.id3 import ID3
                audio = MP3(mp3, ID3=ID3)
                tags  = audio.tags or {}

                def _val(frame_id):
                    f = tags.get(frame_id)
                    if f is None: return ''
                    try:    return str(f.text[0]).strip()
                    except: return ''

                title  = _val('TIT2')
                artist = _val('TPE1')
                album  = _val('TALB')
                year   = _val('TDRC')

                _COVER_NAMES      = ('cover.jpg', 'cover.jpeg', 'folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp')
                _ARTIST_PIC_NAMES = (
                    'artist.jpg', 'artist.jpeg', 'artist.png', 'artist.webp',
                    'folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp',
                )

                flags = []
                if title.lower()  in _UNKNOWN or not title:  flags.append('title')
                if artist.lower() in _UNKNOWN or not artist:  flags.append('artist')
                if album.lower()  in _UNKNOWN or not album:   flags.append('album')
                if not year:                                   flags.append('year')

                # Cover warnings (only once per album folder — deduplicated by set below)
                album_folder = mp3.parent
                if not any((album_folder / n).exists() for n in _COVER_NAMES):
                    flags.append('no_album_cover')

                rel_parts = mp3.relative_to(music_dir).parts
                if len(rel_parts) == 3:
                    artist_folder = music_dir / rel_parts[0]
                    if not any((artist_folder / n).exists() for n in _ARTIST_PIC_NAMES):
                        flags.append('no_artist_picture')

                if flags:
                    issues.append({
                        'path':   str(mp3.relative_to(music_dir)),
                        'title':  title or '—',
                        'artist': artist or '—',
                        'album':  album or '—',
                        'year':   year or '—',
                        'issues': flags,
                    })
            except Exception:
                issues.append({'path': str(mp3.relative_to(music_dir)), 'issues': ['unreadable']})

        return jsonify({'success': True, 'count': len(issues), 'issues': issues})
    except Exception as e:
        logger.error(f"❌ /api/library/issues: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Queue worker ───────────────────────────────────────────────────────────────

def queue_worker():
    logger.info("🔄 Queue worker démarré")
    while True:
        try:
            item = download_queue.get()
            if item is None:
                break

            url       = item['url']
            metadata  = item['metadata']
            user_sub  = item.get('user_sub', 'dev-user-local')
            cancel_flag.clear()

            music_dir = _user_music_dir(user_sub)
            org       = MusicOrganizer(music_dir)

            with queue_lock:
                download_status.update({
                    'in_progress':      True,
                    'current_download': {
                        'url': url, 'metadata': metadata,
                        'started_at': datetime.now().isoformat()
                    },
                    'last_error': None,
                })

            logger.info(f"🎵 {metadata['artist']} - {metadata['title']} [{user_sub[:8]}]")

            try:
                mp4_mode = bool(item.get('mp4_mode', False))
                result   = downloader.download(url, metadata, mp4_mode=mp4_mode)

                if cancel_flag.is_set():
                    raise Exception("Annulé par l'utilisateur")
                if not result['success']:
                    raise Exception(result.get('error', 'Erreur inconnue'))

                playlist_mode = item.get('playlist_mode', False)
                media_mode    = result.get('media_mode', 'mp3')
                # phase already set to 'organizing' by downloader
                org_result    = org.organize(result['file_path'], metadata,
                                             playlist_mode=playlist_mode, media_mode=media_mode)
                if not org_result['success']:
                    raise Exception(org_result.get('error', 'Erreur organisation'))

                downloader.progress.phase   = 'completed'
                downloader.progress.percent = 100

                with queue_lock:
                    download_status['in_progress']    = False
                    download_status['current_download'] = None
                    download_status['batch_done']     = int(download_status.get('batch_done', 0)) + 1
                    download_status['last_completed'] = {
                        'success':   True,
                        'file_path': org_result['final_path'],
                        'metadata':  metadata,
                        'timestamp': datetime.now().isoformat(),
                    }
                    if (download_status['batch_done'] >= download_status.get('batch_total', 0)
                            and download_queue.qsize() == 0):
                        download_status['batch_active'] = False

                logger.info(f"✅ {org_result['final_path']}")
                activity_logger.info(f"🎵 DOWNLOAD | {user_sub[:8]} | {metadata['artist']} - {metadata['title']}")

            except Exception as e:
                logger.error(f"❌ {e}")
                with queue_lock:
                    download_status['in_progress']    = False
                    download_status['current_download'] = None
                    download_status['batch_done']     = int(download_status.get('batch_done', 0)) + 1
                    download_status['last_error']     = {
                        'error': str(e), 'metadata': metadata,
                        'timestamp': datetime.now().isoformat(),
                    }
                    if (download_status['batch_done'] >= download_status.get('batch_total', 0)
                            and download_queue.qsize() == 0):
                        download_status['batch_active'] = False

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
    threading.Thread(target=queue_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=flask_port, debug=False, use_reloader=False)
