#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SongSurf - Serveur de téléchargement musical

Dashboard web avec authentification pour télécharger de la musique
depuis YouTube Music via yt-dlp. Organise automatiquement les fichiers MP3.

Modes:
  - Admin  : accès complet, musique stockée dans /data/music
  - Guest  : quota configurable, musique dans /data/music_guest/<session_id>
             ZIP téléchargeable, nettoyage automatique après 1h

Usage:
  python app.py
  Serveur sur http://0.0.0.0:8080
"""

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
import threading
import time
import queue
import os
import secrets
import shutil
import zipfile
import logging
import re

from downloader import YouTubeDownloader
from organizer import MusicOrganizer

# ============================================
# CONFIGURATION
# ============================================

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(days=7)

# Mots de passe (utilisés uniquement en mode standalone, sans Watcher)
DASHBOARD_PASSWORD = os.getenv('SONGSURF_PASSWORD', '')
GUEST_PASSWORD     = os.getenv('SONGSURF_GUEST_PASSWORD', '')

# Secret partagé avec le Watcher (si vide → mode standalone sans Watcher)
WATCHER_SECRET = os.getenv('WATCHER_SECRET', '')

# Quota guest (0 = illimité)
GUEST_MAX_SONGS = int(os.getenv('GUEST_MAX_SONGS', '10'))

# Durée de conservation des fichiers guest (en secondes, défaut 1h)
GUEST_SESSION_TTL = int(os.getenv('GUEST_SESSION_TTL', '3600'))

# URL de la page de login admin (fallback mode standalone)
ADMIN_LOGIN_PATH = os.getenv('ADMIN_LOGIN_PATH', '/administrator')
if not ADMIN_LOGIN_PATH.startswith('/'):
    ADMIN_LOGIN_PATH = '/' + ADMIN_LOGIN_PATH

if WATCHER_SECRET:
    print("✅ Mode Watcher activé — authentification déléguée au Watcher.")
else:
    if not DASHBOARD_PASSWORD:
        print("⚠️  SONGSURF_PASSWORD non défini ! Le dashboard admin sera non protégé.")
    if not GUEST_PASSWORD:
        print("⚠️  SONGSURF_GUEST_PASSWORD non défini ! L'accès guest sera désactivé.")

# ============================================
# DOSSIERS
# ============================================

if Path(__file__).parent == Path('/app'):
    TEMP_DIR        = Path('/data/temp')
    MUSIC_DIR       = Path('/data/music')
    GUEST_MUSIC_DIR = Path('/data/music_guest')
    GUEST_TEMP_DIR  = Path('/data/temp_guest')
    LOG_DIR         = Path('/app/logs')
else:
    BASE_DIR        = Path(__file__).parent.parent
    TEMP_DIR        = BASE_DIR / "temp"
    MUSIC_DIR       = BASE_DIR / "music"
    GUEST_MUSIC_DIR = BASE_DIR / "music_guest"
    GUEST_TEMP_DIR  = BASE_DIR / "temp_guest"
    LOG_DIR         = BASE_DIR / "logs"

for d in [TEMP_DIR, MUSIC_DIR, GUEST_MUSIC_DIR, GUEST_TEMP_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================
# LOGGING (conservé même après nettoyage guest)
# ============================================

# --- Logger technique complet (console uniquement) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)

# Silence werkzeug (les GET /ping, /api/guest/status etc.) dans la console
logging.getLogger('werkzeug').setLevel(logging.ERROR)

logger = logging.getLogger('songsurf')

# --- Logger activité lisible (fichier dédié) ---
# Format : 2026-02-20 17:13:42 | MESSAGE
activity_handler = logging.FileHandler(LOG_DIR / 'activity.log', encoding='utf-8')
activity_handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
activity_logger = logging.getLogger('songsurf.activity')
activity_logger.addHandler(activity_handler)
activity_logger.propagate = False  # Ne pas remonter au logger parent
activity_logger.setLevel(logging.INFO)

# ============================================
# VALIDATION URL
# ============================================

# Domaines YouTube autorisés
_ALLOWED_YT_DOMAINS = ('youtube.com', 'music.youtube.com', 'www.youtube.com', 'youtu.be')

def _is_valid_youtube_url(url: str) -> bool:
    """
    Vérifie que l'URL :
      1. Commence par https://
      2. Appartient à un domaine YouTube autorisé
      3. Ne contient pas de caractères dangereux (injection)
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    # Doit commencer par https://
    if not url.startswith('https://'):
        return False
    # Extraire le domaine
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.netloc.lower().lstrip('www.')
        # Accepter avec ou sans www.
        host_no_www = parsed.netloc.lower()
        if host_no_www.startswith('www.'):
            host_no_www = host_no_www[4:]
    except Exception:
        return False
    if host_no_www not in _ALLOWED_YT_DOMAINS and parsed.netloc.lower() not in _ALLOWED_YT_DOMAINS:
        return False
    # Bloquer les caractères dangereux dans le path/query
    dangerous = re.compile(r'[<>\'";{}\\`]')
    if dangerous.search(url):
        return False
    return True



# ============================================
# INSTANCES
# ============================================

downloader = YouTubeDownloader(TEMP_DIR, MUSIC_DIR)
organizer  = MusicOrganizer(MUSIC_DIR)

# Queue admin
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
}

# ============================================
# SESSIONS GUEST
# ============================================
# Structure :
# guest_sessions = {
#   session_id: {
#     'created_at': datetime,
#     'expires_at': datetime,
#     'songs_downloaded': int,
#     'files': [str],          # chemins absolus des MP3
#     'queue': Queue,
#     'status': dict,
#     'downloader': YouTubeDownloader,
#     'organizer': MusicOrganizer,
#     'cancel_flag': Event,
#   }
# }
guest_sessions = {}
guest_sessions_lock = threading.Lock()


def _new_guest_session(guest_name="Inconnu", sid=None):
    """Crée une nouvelle session guest et retourne son ID."""
    if sid is None:
        sid = secrets.token_urlsafe(16)
    session_dir      = GUEST_MUSIC_DIR / sid
    session_temp_dir = GUEST_TEMP_DIR  / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    session_temp_dir.mkdir(parents=True, exist_ok=True)

    guest_dl  = YouTubeDownloader(session_temp_dir, session_dir)
    guest_org = MusicOrganizer(session_dir)

    sess = {
        'created_at':       datetime.now(),
        'expires_at':       datetime.now() + timedelta(seconds=GUEST_SESSION_TTL),
        'guest_name':       guest_name,
        'songs_downloaded': 0,
        'files':            [],
        'queue':            queue.Queue(maxsize=MAX_QUEUE_SIZE),
        'status': {
            'in_progress':    False,
            'current_download': None,
            'last_completed': None,
            'last_error':     None,
            'progress':       None,
            'queue_size':     0,
        },
        'downloader':   guest_dl,
        'organizer':    guest_org,
        'cancel_flag':  threading.Event(),
        'music_dir':    session_dir,
        'temp_dir':     session_temp_dir,
        'zip_path':     None,
    }

    with guest_sessions_lock:
        guest_sessions[sid] = sess

    # Démarrer le worker dédié à cette session
    t = threading.Thread(target=guest_queue_worker, args=(sid,), daemon=True)
    t.start()

    logger.info(f"🎭 Nouvelle session guest: {guest_name} ({sid[:8]})")
    activity_logger.info(f"🎭 CONNEXION  | {guest_name} | session {sid[:8]}")
    return sid


def _cleanup_guest_session(sid, reason="manuel"):
    """Supprime les fichiers d'une session guest (logs conservés)."""
    with guest_sessions_lock:
        sess = guest_sessions.pop(sid, None)

    if not sess:
        return

    name  = sess.get('guest_name', 'Inconnu')
    songs = sess.get('songs_downloaded', 0)
    files = sess.get('files', [])

    activity_logger.info(f"🧹 FIN SESSION | {name} | {songs} chanson(s) téléchargée(s) | raison: {reason}")
    for f in files:
        activity_logger.info(f"   └─ {f}")

    logger.info(f"🧹 Nettoyage session {name} ({sid[:8]}) — {songs} chansons")

    # Supprimer les dossiers de la session
    for d in [sess.get('music_dir'), sess.get('temp_dir')]:
        if d and Path(d).exists():
            shutil.rmtree(d, ignore_errors=True)

    # Supprimer le ZIP s'il existe
    zip_path = sess.get('zip_path')
    if zip_path and Path(zip_path).exists():
        Path(zip_path).unlink(missing_ok=True)


def guest_cleanup_worker():
    """Thread qui nettoie les sessions guest expirées toutes les 5 minutes."""
    while True:
        time.sleep(300)
        now = datetime.now()
        expired = []
        with guest_sessions_lock:
            for sid, sess in list(guest_sessions.items()):
                exp = sess.get('expires_at', now)
                if isinstance(exp, str):
                    exp = datetime.fromisoformat(exp)
                if now >= exp:
                    expired.append(sid)

        for sid in expired:
            _cleanup_guest_session(sid, reason="expiration automatique")


def guest_queue_worker(sid):
    """Worker de téléchargement dédié à une session guest."""
    logger.info(f"🔄 Guest worker démarré pour session {sid}")

    with guest_sessions_lock:
        sess = guest_sessions.get(sid)
    if not sess:
        return

    dl_queue    = sess['queue']
    dl          = sess['downloader']
    org         = sess['organizer']
    status      = sess['status']
    cancel      = sess['cancel_flag']

    while True:
        # Vérifier si la session existe encore
        with guest_sessions_lock:
            if sid not in guest_sessions:
                break

        try:
            try:
                item = dl_queue.get(timeout=5)
            except queue.Empty:
                continue

            if item is None:
                break

            url      = item['url']
            metadata = item['metadata']
            cancel.clear()

            status['in_progress'] = True
            status['current_download'] = {
                'url': url,
                'metadata': metadata,
                'started_at': datetime.now().isoformat()
            }
            status['last_error'] = None

            logger.info(f"[GUEST:{sid[:8]}] ⬇️  {metadata['artist']} - {metadata['title']}")

            try:
                result = dl.download(url, metadata)

                if cancel.is_set():
                    raise Exception("Annulé par l'utilisateur")
                if not result['success']:
                    raise Exception(result.get('error', 'Erreur inconnue'))

                playlist_mode = item.get('playlist_mode', False)
                org_result = org.organize(result['file_path'], metadata, playlist_mode=playlist_mode)
                if not org_result['success']:
                    raise Exception(org_result.get('error', 'Erreur organisation'))

                # Enregistrer le fichier dans la session
                with guest_sessions_lock:
                    if sid in guest_sessions:
                        guest_sessions[sid]['songs_downloaded'] += 1
                        guest_sessions[sid]['files'].append(org_result['final_path'])
                        guest_name = guest_sessions[sid].get('guest_name', 'Inconnu')

                status['in_progress'] = False
                status['current_download'] = None
                status['last_completed'] = {
                    'success': True,
                    'file_path': org_result['final_path'],
                    'metadata': metadata,
                    'timestamp': datetime.now().isoformat()
                }
                logger.info(f"[GUEST:{sid[:8]}] ✅ {org_result['final_path']}")
                activity_logger.info(f"🎵 DOWNLOAD    | {guest_name} | {metadata['artist']} - {metadata['title']}")

            except Exception as e:
                logger.error(f"[GUEST:{sid[:8]}] ❌ {e}")
                status['in_progress'] = False
                status['current_download'] = None
                status['last_error'] = {
                    'error': str(e),
                    'metadata': metadata,
                    'timestamp': datetime.now().isoformat()
                }

            dl_queue.task_done()

        except Exception as e:
            logger.error(f"Guest worker {sid} erreur: {e}")
            time.sleep(1)


# ============================================
# AUTHENTIFICATION
# ============================================

login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION   = timedelta(minutes=15)


def _get_client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()


def _is_locked(ip):
    info = login_attempts.get(ip)
    if not info or not info.get('locked_until'):
        return False
    if datetime.now() >= info['locked_until']:
        login_attempts.pop(ip, None)
        return False
    return True


def _remaining_lockout(ip):
    info = login_attempts.get(ip, {})
    locked_until = info.get('locked_until')
    if not locked_until:
        return 0
    remaining = (locked_until - datetime.now()).total_seconds()
    return max(1, int(remaining // 60) + 1)


def _record_failed_attempt(ip):
    if ip not in login_attempts:
        login_attempts[ip] = {'attempts': 0, 'locked_until': None}
    login_attempts[ip]['attempts'] += 1
    attempts = login_attempts[ip]['attempts']
    logger.warning(f"🚫 Échec login depuis {ip} ({attempts}/{MAX_LOGIN_ATTEMPTS})")
    if attempts >= MAX_LOGIN_ATTEMPTS:
        login_attempts[ip]['locked_until'] = datetime.now() + LOCKOUT_DURATION
        logger.warning(f"🔒 IP {ip} bloquée {LOCKOUT_DURATION.total_seconds()//60:.0f} min")


def _reset_attempts(ip):
    login_attempts.pop(ip, None)


def login_required(f):
    """Réservé aux admins.
    Accepte soit le token Watcher (mode production), soit la session Flask (mode standalone/dev).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # ── Mode Watcher : vérifier le token d'en-tête ──────────────────────
        watcher_token = request.headers.get('X-Watcher-Token', '')
        if WATCHER_SECRET and watcher_token == WATCHER_SECRET:
            if request.headers.get('X-User-Role') == 'admin':
                session['authenticated'] = True   # maintenir session locale
                return f(*args, **kwargs)
            # Token valide mais rôle incorrect
            if request.is_json:
                return jsonify({'success': False, 'error': 'Accès admin requis'}), 403
            return redirect(url_for('login'))

        # ── Fallback : session classique (mode standalone sans Watcher) ─────
        if not DASHBOARD_PASSWORD or session.get('authenticated'):
            return f(*args, **kwargs)
        if request.is_json:
            return jsonify({'success': False, 'error': 'Non authentifié'}), 401
        return redirect(url_for('login'))
    return decorated


def guest_required(f):
    """Réservé aux guests.
    Accepte soit le token Watcher (mode production), soit la session Flask (mode standalone/dev).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # ── Mode Watcher : vérifier le token d'en-tête ──────────────────────
        watcher_token = request.headers.get('X-Watcher-Token', '')
        if WATCHER_SECRET and watcher_token == WATCHER_SECRET:
            role     = request.headers.get('X-User-Role', '')
            guest_id = request.headers.get('X-Guest-Session-Id', '')
            if role == 'guest' and guest_id:
                # Créer la session guest complète si elle n'existe pas encore
                with guest_sessions_lock:
                    already_exists = guest_id in guest_sessions
                if not already_exists:
                    guest_name = request.headers.get('X-Guest-Name', 'Guest')
                    _new_guest_session(guest_name=guest_name, sid=guest_id)
                session['guest_session_id'] = guest_id   # sync session locale
                return f(*args, **kwargs)
            if request.is_json:
                return jsonify({'success': False, 'error': 'Session guest invalide'}), 401
            return redirect(url_for('guest_login'))

        # ── Fallback : session classique (mode standalone sans Watcher) ─────
        sid = session.get('guest_session_id')
        if not sid:
            if request.is_json:
                return jsonify({'success': False, 'error': 'Session guest invalide'}), 401
            return redirect(url_for('guest_login'))
        with guest_sessions_lock:
            if sid not in guest_sessions:
                session.clear()
                if request.is_json:
                    return jsonify({'success': False, 'error': 'Session expirée'}), 401
                return redirect(url_for('guest_login'))
        return f(*args, **kwargs)
    return decorated


# ============================================
# ROUTES LOGIN ADMIN
# ============================================

@app.route(ADMIN_LOGIN_PATH, methods=['GET', 'POST'])
def login():
    """Page de login admin — chemin configurable via ADMIN_LOGIN_PATH."""
    if not DASHBOARD_PASSWORD:
        session['authenticated'] = True
        session.permanent = True
        return redirect(url_for('dashboard'))

    ip = _get_client_ip()
    error = None

    if _is_locked(ip):
        minutes = _remaining_lockout(ip)
        return render_template('login.html', error=f'Trop de tentatives. Réessayez dans {minutes} min.', locked=True)

    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == DASHBOARD_PASSWORD:
            session['authenticated'] = True
            session.permanent = True
            _reset_attempts(ip)
            logger.info(f"✅ Login admin depuis {ip}")
            return redirect(url_for('dashboard'))
        else:
            _record_failed_attempt(ip)
            if _is_locked(ip):
                error = f'Trop de tentatives. Réessayez dans {_remaining_lockout(ip)} min.'
            else:
                remaining = MAX_LOGIN_ATTEMPTS - login_attempts.get(ip, {}).get('attempts', 0)
                error = f'Mot de passe incorrect ({remaining} essai{"s" if remaining > 1 else ""} restant{"s" if remaining > 1 else ""})'

    return render_template('login.html', error=error, locked=_is_locked(ip),
                           admin_login_path=ADMIN_LOGIN_PATH)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============================================
# ROUTES LOGIN GUEST
# ============================================

@app.route('/guest/login', methods=['GET', 'POST'])
def guest_login():
    if not GUEST_PASSWORD:
        return render_template('login.html',
            error="L'accès guest est désactivé (SONGSURF_GUEST_PASSWORD non défini).",
            locked=True, is_guest=True)

    ip = _get_client_ip()
    error = None

    if _is_locked(ip):
        return render_template('login.html',
            error=f'Trop de tentatives. Réessayez dans {_remaining_lockout(ip)} min.',
            locked=True, is_guest=True)

    if request.method == 'POST':
        password   = request.form.get('password', '')
        guest_name = request.form.get('guest_name', '').strip() or 'Inconnu'
        if password == GUEST_PASSWORD:
            sid = _new_guest_session(guest_name)
            session['guest_session_id'] = sid
            session['guest_name'] = guest_name
            session.permanent = False
            _reset_attempts(ip)
            logger.info(f"🎭 Login guest '{guest_name}' depuis {ip} → session {sid[:8]}")
            return redirect(url_for('guest_dashboard'))
        else:
            _record_failed_attempt(ip)
            if _is_locked(ip):
                error = f'Trop de tentatives. Réessayez dans {_remaining_lockout(ip)} min.'
            else:
                remaining = MAX_LOGIN_ATTEMPTS - login_attempts.get(ip, {}).get('attempts', 0)
                error = f'Mot de passe incorrect ({remaining} essai{"s" if remaining > 1 else ""} restant{"s" if remaining > 1 else ""})'

    return render_template('login.html', error=error, locked=_is_locked(ip), is_guest=True)


@app.route('/guest/logout')
def guest_logout():
    sid = session.get('guest_session_id')
    session.clear()
    logger.info(f"🚪 Guest logout, session {sid[:8] if sid else '?'} conservée jusqu'à expiration")
    return redirect(url_for('guest_login'))


# ============================================
# DASHBOARD ADMIN
# ============================================

@app.route('/')
@login_required
def dashboard():
    stats = organizer.get_stats()
    return render_template('dashboard.html', stats=stats, admin_login_path=ADMIN_LOGIN_PATH)


# ============================================
# DASHBOARD GUEST
# ============================================

@app.route('/guest')
@guest_required
def guest_dashboard():
    sid = session['guest_session_id']
    with guest_sessions_lock:
        sess = guest_sessions.get(sid, {})
    return render_template('guest_dashboard.html',
        session_id=sid,
        songs_downloaded=sess.get('songs_downloaded', 0),
        max_songs=GUEST_MAX_SONGS,
        expires_at=(sess['expires_at'] if isinstance(sess.get('expires_at'), str) else sess.get('expires_at', datetime.now()).isoformat()),  # str si déjà sérialisé, sinon datetime→str
    )


# ============================================
# API PUBLIQUE
# ============================================

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'status': 'ok', 'message': 'SongSurf is running', 'timestamp': datetime.now().isoformat()})



# ============================================
# API ADMIN
# ============================================

@app.route('/api/status', methods=['GET'])
@login_required
def get_status():
    with queue_lock:
        status = download_status.copy()
        status['queue_size'] = download_queue.qsize()
        if status['in_progress']:
            status['progress'] = downloader.get_progress()
    return jsonify(status)


@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    return jsonify(organizer.get_stats())


@app.route('/api/extract', methods=['POST'])
@login_required
def extract_metadata():
    try:
        data = request.get_json()
        url  = data.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            logger.warning(f"[ADMIN] URL invalide rejetée: {url[:80]}")
            return jsonify({'success': False, 'error': 'URL invalide. Veuillez coller un lien YouTube Music valide.'}), 400
        is_playlist = ('/playlist?list=' in url or '/browse/' in url) and '/watch?' not in url
        if is_playlist:
            result = downloader.extract_playlist_metadata(url)
        else:
            result = downloader.extract_metadata(url)
            if result.get('success') and 'metadata' in result:
                meta = result.pop('metadata')
                result.update(meta)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download', methods=['POST'])
@login_required
def start_download():
    try:
        data = request.get_json()
        url  = data.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            logger.warning(f"[ADMIN] URL invalide rejetée au download: {url[:80]}")
            return jsonify({'success': False, 'error': 'URL invalide. Veuillez coller un lien YouTube Music valide.'}), 400
        # Brider à 1 téléchargement à la fois
        if download_status['in_progress'] or download_queue.qsize() > 0:
            return jsonify({'success': False, 'error': 'Un téléchargement est déjà en cours. Attendez qu\'il se termine.'}), 429

        playlist_mode = bool(data.get('playlist_mode', False))
        metadata = {
            'artist': data.get('artist', 'Unknown Artist'),
            'album':  data.get('album',  'Unknown Album'),
            'title':  data.get('title',  'Unknown Title'),
            'year':   data.get('year',   '')
        }
        download_queue.put({'url': url, 'metadata': metadata, 'playlist_mode': playlist_mode, 'added_at': datetime.now().isoformat()})
        logger.info(f"➕ Admin queue: {metadata['artist']} - {metadata['title']} [playlist_mode={playlist_mode}]")
        return jsonify({'success': True, 'message': 'Ajouté à la queue', 'queue_size': download_queue.qsize()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download-playlist', methods=['POST'])
@login_required
def download_playlist():
    try:
        data     = request.get_json()
        url      = data.get('url', '')
        playlist = data.get('playlist_metadata', {})
        if not url or not playlist:
            return jsonify({'success': False, 'error': 'Données manquantes'}), 400
        # Brider à 1 téléchargement à la fois
        if download_status['in_progress'] or download_queue.qsize() > 0:
            return jsonify({'success': False, 'error': 'Un téléchargement est déjà en cours. Attendez qu\'il se termine.'}), 429

        playlist_mode = bool(data.get('playlist_mode', False))
        songs = playlist.get('songs', [])
        added = 0
        for song in songs:
            if download_queue.full():
                break
            metadata = {
                'artist': song.get('artist', playlist.get('artist', 'Unknown')),
                'album':  playlist.get('title', 'Unknown Album'),
                'title':  song['title'],
                'year':   playlist.get('year', '')
            }
            download_queue.put({'url': song['url'], 'metadata': metadata, 'playlist_mode': playlist_mode, 'added_at': datetime.now().isoformat()})
            added += 1

        return jsonify({'success': True, 'added': added, 'total': len(songs), 'queue_size': download_queue.qsize()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cancel', methods=['POST'])
@login_required
def cancel_download():
    if not download_status['in_progress']:
        return jsonify({'success': False, 'error': 'Aucun téléchargement en cours'}), 400
    cancel_flag.set()
    return jsonify({'success': True, 'message': 'Annulation demandée'})


@app.route('/api/cleanup', methods=['POST'])
@login_required
def cleanup():
    deleted = []
    if TEMP_DIR.exists():
        for f in TEMP_DIR.iterdir():
            if f.is_file():
                f.unlink()
                deleted.append(f.name)
    download_status['in_progress'] = False
    download_status['current_download'] = None
    download_status['last_error'] = None
    return jsonify({'success': True, 'deleted': len(deleted)})
# API GUEST
# ============================================

@app.route('/api/guest/status', methods=['GET'])
@guest_required
def guest_status():
    sid  = session['guest_session_id']
    with guest_sessions_lock:
        sess = guest_sessions.get(sid, {})
    status = sess.get('status', {}).copy()
    status['queue_size']       = sess['queue'].qsize() if 'queue' in sess else 0
    status['songs_downloaded'] = sess.get('songs_downloaded', 0)
    status['max_songs']        = GUEST_MAX_SONGS
    exp = sess.get('expires_at', datetime.now())
    status['expires_at']       = exp if isinstance(exp, str) else exp.isoformat()
    if status.get('in_progress') and 'downloader' in sess:
        status['progress'] = sess['downloader'].get_progress()
    return jsonify(status)


@app.route('/api/guest/extend-session', methods=['POST'])
@guest_required
def guest_extend_session():
    """Prolonge la session guest d'une heure supplémentaire."""
    sid = session['guest_session_id']
    with guest_sessions_lock:
        sess = guest_sessions.get(sid)
        if not sess:
            return jsonify({'success': False, 'error': 'Session introuvable'}), 404
        # Normaliser expires_at en datetime si nécessaire
        if isinstance(sess['expires_at'], str):
            sess['expires_at'] = datetime.fromisoformat(sess['expires_at'])
        sess['expires_at'] = sess['expires_at'] + timedelta(seconds=GUEST_SESSION_TTL)
        new_expires = sess['expires_at'].isoformat()
    logger.info(f"🔄 Session guest prolongée: {sid[:8]} → expire à {new_expires}")
    return jsonify({'success': True, 'expires_at': new_expires})


@app.route('/api/guest/extract', methods=['POST'])
@guest_required
def guest_extract():
    try:
        data = request.get_json()
        url  = data.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            logger.warning(f"[GUEST] URL invalide rejetée: {url[:80]}")
            return jsonify({'success': False, 'error': 'URL invalide. Veuillez coller un lien YouTube Music valide (https://music.youtube.com/... ou https://www.youtube.com/...).'}), 400

        sid = session['guest_session_id']
        with guest_sessions_lock:
            sess = guest_sessions.get(sid)
        if not sess:
            return jsonify({'success': False, 'error': 'Session expirée'}), 401

        dl = sess['downloader']
        # Playlist seulement si URL pointe vers une vraie playlist, pas une chanson avec &list=
        is_playlist = ('/playlist?list=' in url or '/browse/' in url) and '/watch?' not in url
        if is_playlist:
            result = dl.extract_playlist_metadata(url)
        else:
            result = dl.extract_metadata(url)
            # Aplatir la réponse : sortir les métadonnées du sous-objet 'metadata'
            if result.get('success') and 'metadata' in result:
                meta = result.pop('metadata')
                result.update(meta)
        # Masquer les détails d'erreur yt-dlp côté guest
        if not result.get('success'):
            logger.warning(f"[GUEST:{sid[:8]}] Extraction échouée pour {url[:60]}")
            return jsonify({'success': False, 'error': 'Impossible d\'extraire les informations. Vérifiez que le lien est correct et accessible.'}), 400
        return jsonify(result)
    except Exception as e:
        logger.error(f"[GUEST] guest_extract exception: {e}")
        return jsonify({'success': False, 'error': 'Une erreur est survenue. Vérifiez votre lien YouTube Music.'}), 500


@app.route('/api/guest/download', methods=['POST'])
@guest_required
def guest_download():
    try:
        sid = session['guest_session_id']
        with guest_sessions_lock:
            sess = guest_sessions.get(sid)
        if not sess:
            return jsonify({'success': False, 'error': 'Session expirée'}), 401

        # Vérifier le quota
        if GUEST_MAX_SONGS > 0 and sess['songs_downloaded'] >= GUEST_MAX_SONGS:
            return jsonify({
                'success': False,
                'error': f'Quota atteint ({GUEST_MAX_SONGS} chansons max par session)'
            }), 429

        # Vérifier la queue
        if sess['queue'].full():
            return jsonify({'success': False, 'error': 'Queue pleine'}), 429

        data = request.get_json()
        url  = data.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
        if not _is_valid_youtube_url(url):
            logger.warning(f"[GUEST] URL invalide rejetée au download: {url[:80]}")
            return jsonify({'success': False, 'error': 'URL invalide. Veuillez coller un lien YouTube Music valide.'}), 400

        playlist_mode = bool(data.get('playlist_mode', False))
        metadata = {
            'artist': data.get('artist', 'Unknown Artist'),
            'album':  data.get('album',  'Unknown Album'),
            'title':  data.get('title',  'Unknown Title'),
            'year':   data.get('year',   '')
        }

        sess['queue'].put({'url': url, 'metadata': metadata, 'playlist_mode': playlist_mode, 'added_at': datetime.now().isoformat()})
        logger.info(f"[GUEST:{sid[:8]}] ➕ {metadata['artist']} - {metadata['title']}")

        return jsonify({
            'success': True,
            'message': 'Ajouté à la queue',
            'queue_size': sess['queue'].qsize(),
            'songs_downloaded': sess['songs_downloaded'],
            'max_songs': GUEST_MAX_SONGS
        })
    except Exception as e:
        logger.error(f"[GUEST] guest_download exception: {e}")
        return jsonify({'success': False, 'error': 'Une erreur est survenue lors de l\'ajout à la queue.'}), 500


@app.route('/api/guest/download-playlist', methods=['POST'])
@guest_required
def guest_download_playlist():
    try:
        sid = session['guest_session_id']
        with guest_sessions_lock:
            sess = guest_sessions.get(sid)
        if not sess:
            return jsonify({'success': False, 'error': 'Session expirée'}), 401

        data     = request.get_json()
        playlist = data.get('playlist_metadata', {})
        songs    = playlist.get('songs', [])
        playlist_mode = bool(data.get('playlist_mode', False))

        # Calculer combien on peut encore ajouter
        already = sess['songs_downloaded'] + sess['queue'].qsize()
        remaining_quota = (GUEST_MAX_SONGS - already) if GUEST_MAX_SONGS > 0 else len(songs)
        songs_to_add = songs[:remaining_quota]

        added = 0
        for song in songs_to_add:
            if sess['queue'].full():
                break
            metadata = {
                'artist': song.get('artist', playlist.get('artist', 'Unknown')),
                'album':  playlist.get('title', 'Unknown Album'),
                'title':  song['title'],
                'year':   playlist.get('year', '')
            }
            sess['queue'].put({'url': song['url'], 'metadata': metadata, 'playlist_mode': playlist_mode, 'added_at': datetime.now().isoformat()})
            added += 1

        return jsonify({
            'success': True,
            'added': added,
            'total': len(songs),
            'skipped': len(songs) - added,
            'quota_remaining': max(0, remaining_quota - added),
            'queue_size': sess['queue'].qsize()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/guest/prepare-zip', methods=['POST'])
@guest_required
def guest_prepare_zip():
    """Génère le ZIP des musiques téléchargées par le guest."""
    sid = session['guest_session_id']
    with guest_sessions_lock:
        sess = guest_sessions.get(sid)
    if not sess:
        return jsonify({'success': False, 'error': 'Session expirée'}), 401

    music_dir = sess['music_dir']

    # Attendre que la queue soit vide (timeout 30s)
    try:
        sess['queue'].join()
    except Exception:
        pass

    # Lister tous les MP3
    mp3_files = list(Path(music_dir).rglob('*.mp3'))
    if not mp3_files:
        return jsonify({'success': False, 'error': 'Aucun fichier à télécharger'}), 404

    # Créer le ZIP
    zip_path = GUEST_TEMP_DIR / f"songsurf_guest_{sid[:8]}.zip"
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for mp3 in mp3_files:
                arcname = mp3.relative_to(music_dir)
                zf.write(mp3, arcname)

        with guest_sessions_lock:
            if sid in guest_sessions:
                guest_sessions[sid]['zip_path'] = str(zip_path)

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        logger.info(f"[GUEST:{sid[:8]}] 📦 ZIP créé: {len(mp3_files)} fichiers, {size_mb:.1f} MB")

        return jsonify({
            'success': True,
            'file_count': len(mp3_files),
            'size_mb': round(size_mb, 1),
            'download_url': url_for('guest_download_zip')
        })
    except Exception as e:
        logger.error(f"[GUEST:{sid[:8]}] ❌ Erreur ZIP: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/guest/download-zip', methods=['GET'])
@guest_required
def guest_download_zip():
    """Envoie le ZIP au client puis déclenche le nettoyage."""
    sid = session['guest_session_id']
    with guest_sessions_lock:
        sess = guest_sessions.get(sid)
    if not sess:
        return jsonify({'success': False, 'error': 'Session expirée'}), 401

    zip_path = sess.get('zip_path')
    if not zip_path or not Path(zip_path).exists():
        return jsonify({'success': False, 'error': 'ZIP non disponible, utilisez /api/guest/prepare-zip d\'abord'}), 404

    logger.info(f"[GUEST:{sid[:8]}] ⬇️  Téléchargement ZIP par l'utilisateur")

    # Planifier le nettoyage 15 min après le téléchargement
    # Le navigateur gère le DL de façon indépendante (fermer l'onglet ne l'arrête pas),
    # mais le fichier ZIP doit rester disponible jusqu'à la fin du transfert.
    # 15 min couvre les gros fichiers sur connexion lente.
    def delayed_cleanup():
        time.sleep(900)  # 15 minutes
        _cleanup_guest_session(sid, reason="téléchargement ZIP effectué")

    threading.Thread(target=delayed_cleanup, daemon=True).start()

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f'SongSurf_musiques.zip',
        mimetype='application/zip'
    )


@app.route('/api/guest/cancel', methods=['POST'])
@guest_required
def guest_cancel():
    sid = session['guest_session_id']
    with guest_sessions_lock:
        sess = guest_sessions.get(sid)
    if not sess:
        return jsonify({'success': False, 'error': 'Session expirée'}), 401
    sess['cancel_flag'].set()
    return jsonify({'success': True, 'message': 'Annulation demandée'})


# ============================================
# QUEUE WORKER ADMIN
# ============================================

def queue_worker():
    """Thread qui traite la queue de téléchargements admin."""
    logger.info("🔄 Admin queue worker démarré")
    while True:
        try:
            item = download_queue.get()
            if item is None:
                break

            url      = item['url']
            metadata = item['metadata']
            cancel_flag.clear()

            with queue_lock:
                download_status['in_progress'] = True
                download_status['current_download'] = {
                    'url': url, 'metadata': metadata,
                    'started_at': datetime.now().isoformat()
                }
                download_status['last_error'] = None

            logger.info(f"🎵 Admin: {metadata['artist']} - {metadata['title']}")

            try:
                result = downloader.download(url, metadata)
                if cancel_flag.is_set():
                    raise Exception("Annulé par l'utilisateur")
                if not result['success']:
                    raise Exception(result.get('error', 'Erreur inconnue'))

                playlist_mode = item.get('playlist_mode', False)
                org_result = organizer.organize(result['file_path'], metadata, playlist_mode=playlist_mode)
                if not org_result['success']:
                    raise Exception(org_result.get('error', 'Erreur organisation'))

                with queue_lock:
                    download_status['in_progress'] = False
                    download_status['current_download'] = None
                    download_status['last_completed'] = {
                        'success': True,
                        'file_path': org_result['final_path'],
                        'metadata': metadata,
                        'timestamp': datetime.now().isoformat()
                    }
                logger.info(f"✅ Admin: {org_result['final_path']}")

            except Exception as e:
                logger.error(f"❌ Admin: {e}")
                with queue_lock:
                    download_status['in_progress'] = False
                    download_status['current_download'] = None
                    download_status['last_error'] = {
                        'error': str(e), 'metadata': metadata,
                        'timestamp': datetime.now().isoformat()
                    }

            download_queue.task_done()

        except Exception as e:
            logger.error(f"❌ Admin queue worker error: {e}")
            time.sleep(1)

from flask import send_from_directory

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)
# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    flask_port = int(os.getenv('FLASK_PORT', '8080'))
    print("\n" + "=" * 60)
    print("🎵 SongSurf - Dashboard Musical")
    print("=" * 60)
    print(f"📁 Music admin : {MUSIC_DIR}")
    print(f"📁 Music guest : {GUEST_MUSIC_DIR}")
    print(f"🔐 Admin auth  : {'✅ Protégé' if DASHBOARD_PASSWORD else '⚠️  OUVERT'}")
    print(f"🎭 Guest auth  : {'✅ Protégé' if GUEST_PASSWORD else '❌ Désactivé'}")
    print(f"🎵 Guest quota : {GUEST_MAX_SONGS if GUEST_MAX_SONGS > 0 else 'illimité'} chansons/session")
    print(f"⏱️  Guest TTL   : {GUEST_SESSION_TTL // 60} minutes")
    print(f"📝 Logs        : {LOG_DIR / 'songsurf.log'}")
    print("=" * 60)
    print(f"🚀 http://0.0.0.0:{flask_port}")
    print("=" * 60 + "\n")

    # Démarrer les workers
    threading.Thread(target=queue_worker,         daemon=True).start()
    threading.Thread(target=guest_cleanup_worker, daemon=True).start()

    app.run(host='0.0.0.0', port=flask_port, debug=False, use_reloader=False)
