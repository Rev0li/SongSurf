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
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_permanent(role: str) -> bool:
    return role == 'admin'


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
            return render_template('pages/unavailable.html'), 503
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
        return send_file(index)
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
    return jsonify(status)


# ── Library ────────────────────────────────────────────────────────────────────

def _build_library_tree(music_dir: Path) -> dict:
    artists = []
    playlists = []
    if not music_dir.exists():
        return {'artists': artists, 'playlists': playlists}
    for top in sorted([d for d in music_dir.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
        direct_songs = sorted(top.glob('*.mp3'), key=lambda p: p.name.lower())
        if direct_songs:
            playlists.append({
                'name':  top.name,
                'path':  str(top.relative_to(music_dir)),
                'songs': [{'name': s.name, 'path': str(s.relative_to(music_dir))} for s in direct_songs],
            })
            continue
        albums = []
        for album_dir in sorted([d for d in top.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
            songs = sorted(album_dir.glob('*.mp3'), key=lambda p: p.name.lower())
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
        if not src.exists() or src.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier source invalide'}), 404

        dst_dir.mkdir(parents=True, exist_ok=True)
        target = dst_dir / src.name
        i = 1
        while target.exists():
            target = dst_dir / f"{src.stem} ({i}){src.suffix}"
            i += 1

        shutil.move(str(src), str(target))
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
        if dst.exists():
            return jsonify({'success': False, 'error': 'Un dossier avec ce nom existe déjà'}), 409

        src.rename(dst)
        return jsonify({'success': True, 'new_path': str(dst.relative_to(music_dir))})
    except Exception as e:
        logger.error(f"❌ /api/library/rename-folder: {e}")
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
                'artist': song.get('artist', playlist.get('artist', 'Unknown')),
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
