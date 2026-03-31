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

# Donation / soutien
DONATION_BTC = os.getenv('DONATION_BTC', 'bc1qxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx')
DONATION_ETH = os.getenv('DONATION_ETH', '0xXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')
DONATION_SOL = os.getenv('DONATION_SOL', 'SoLxXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')

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

DONATION_DIR = LOG_DIR / 'donations'

for d in [TEMP_DIR, MUSIC_DIR, GUEST_MUSIC_DIR, GUEST_TEMP_DIR, LOG_DIR, DONATION_DIR]:
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


def _is_playlist_url(url: str) -> bool:
    """Détecte les URLs album/playlist, y compris watch?v=...&list=..."""
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse((url or '').strip())
        path = (parsed.path or '').lower()
        query = parse_qs(parsed.query or '')

        if '/playlist' in path or '/browse/' in path:
            return True

        list_id = query.get('list', [''])[0].strip()
        if list_id:
            return True
    except Exception:
        return False
    return False



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
    'batch_active': False,
    'batch_total': 0,
    'batch_done': 0,
    'batch_percent': 0,
}

admin_prefetch_lock = threading.Lock()
admin_prefetch_state = {
    'token': '',
    'status': 'idle',  # idle, pending, ready, failed
    'file_path': '',
    'updated_at': '',
}


def _start_or_extend_batch(added_count: int):
    """Suit la progression globale d'un lot multi-titres."""
    if added_count <= 0:
        return
    with queue_lock:
        if not download_status.get('batch_active'):
            download_status['batch_active'] = True
            download_status['batch_total'] = 0
            download_status['batch_done'] = 0
            download_status['batch_percent'] = 0
        download_status['batch_total'] += added_count


def _prefetch_cleanup_file(file_path: str):
    """Supprime un MP3 temp prefetched et ses sidecars image éventuels."""
    if not file_path:
        return
    try:
        p = Path(file_path)
        if p.exists() and p.is_file():
            p.unlink()
        stem = p.with_suffix('')
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            side = Path(str(stem) + ext)
            if side.exists() and side.is_file():
                side.unlink()
    except Exception as e:
        logger.warning(f"⚠️ Nettoyage prefetch impossible: {e}")


def _prefetch_first_playlist_song_async(dl, playlist_meta, on_done=None):
    """Précharge la 1re piste d'une playlist sans bloquer l'API d'analyse."""
    try:
        songs = (playlist_meta or {}).get('songs') or []
        if not songs:
            return

        first = songs[0] or {}
        first_url = (first.get('url') or '').strip()
        if not first_url:
            return

        metadata = {
            'artist': first.get('artist', (playlist_meta or {}).get('artist', 'Unknown Artist')),
            'album': (playlist_meta or {}).get('title', 'Unknown Album'),
            'title': first.get('title', 'Unknown Title'),
            'year': (playlist_meta or {}).get('year', ''),
        }

        def _job():
            result = dl.prefetch_first_track(first_url, metadata)
            if callable(on_done):
                try:
                    on_done(result)
                except Exception as cb_err:
                    logger.warning(f"⚠️ Callback prefetch en erreur: {cb_err}")

        threading.Thread(target=_job, daemon=True).start()
    except Exception as e:
        logger.warning(f"⚠️ Prefetch async non démarré: {e}")


def _start_admin_prefetch(dl, playlist_meta):
    """Lance un prefetch admin et renvoie le token de suivi côté frontend."""
    old_file = ''
    token = secrets.token_urlsafe(16)
    with admin_prefetch_lock:
        old_file = admin_prefetch_state.get('file_path', '')
        admin_prefetch_state['token'] = token
        admin_prefetch_state['status'] = 'pending'
        admin_prefetch_state['file_path'] = ''
        admin_prefetch_state['updated_at'] = datetime.now().isoformat()

    if old_file:
        _prefetch_cleanup_file(old_file)

    def _done(result):
        file_path = (result or {}).get('file_path', '') if (result or {}).get('success') else ''
        with admin_prefetch_lock:
            current_token = admin_prefetch_state.get('token', '')
            if current_token != token:
                # Un nouveau prefetch a déjà été demandé; nettoyer cet ancien fichier.
                if file_path:
                    _prefetch_cleanup_file(file_path)
                return
            admin_prefetch_state['status'] = 'ready' if file_path else 'failed'
            admin_prefetch_state['file_path'] = file_path
            admin_prefetch_state['updated_at'] = datetime.now().isoformat()

    _prefetch_first_playlist_song_async(dl, playlist_meta, on_done=_done)
    return token


def _cancel_admin_prefetch(token=''):
    with admin_prefetch_lock:
        current = admin_prefetch_state.get('token', '')
        if token and current and token != current:
            return False
        file_path = admin_prefetch_state.get('file_path', '')
        admin_prefetch_state['token'] = ''
        admin_prefetch_state['status'] = 'idle'
        admin_prefetch_state['file_path'] = ''
        admin_prefetch_state['updated_at'] = datetime.now().isoformat()

    if file_path:
        _prefetch_cleanup_file(file_path)
    return True

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
                mp4_mode = bool(item.get('mp4_mode', False))
                result = dl.download(url, metadata, mp4_mode=mp4_mode)

                if cancel.is_set():
                    raise Exception("Annulé par l'utilisateur")
                if not result['success']:
                    raise Exception(result.get('error', 'Erreur inconnue'))

                playlist_mode = item.get('playlist_mode', False)
                media_mode = result.get('media_mode', 'mp3')
                org_result = org.organize(result['file_path'], metadata, playlist_mode=playlist_mode, media_mode=media_mode)
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


def _donation_access_allowed() -> bool:
    """Autorise l'accès donation pour admin ou guest authentifiés."""
    watcher_token = request.headers.get('X-Watcher-Token', '')
    if WATCHER_SECRET and watcher_token == WATCHER_SECRET:
        role = request.headers.get('X-User-Role', '')
        if role in ('admin', 'guest'):
            return True

    if session.get('authenticated'):
        return True

    sid = session.get('guest_session_id')
    if sid:
        with guest_sessions_lock:
            return sid in guest_sessions

    return False


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
        return render_template('pages/login.html', error=f'Trop de tentatives. Réessayez dans {minutes} min.', locked=True)

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

    return render_template('pages/login.html', error=error, locked=_is_locked(ip),
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
        return render_template('pages/login.html',
            error="L'accès guest est désactivé (SONGSURF_GUEST_PASSWORD non défini).",
            locked=True, is_guest=True)

    ip = _get_client_ip()
    error = None

    if _is_locked(ip):
        return render_template('pages/login.html',
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

    return render_template('pages/login.html', error=error, locked=_is_locked(ip), is_guest=True)


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
    return render_template('pages/dashboard_admin.html', stats=stats, admin_login_path=ADMIN_LOGIN_PATH)


@app.route('/donation', methods=['GET'])
def donation_page():
    if not _donation_access_allowed():
        return redirect(url_for('login'))
    return render_template(
        'pages/donation.html',
        btc_address=DONATION_BTC,
        eth_address=DONATION_ETH,
        sol_address=DONATION_SOL,
    )


@app.route('/api/donation/upload-coupon', methods=['POST'])
def donation_upload_coupon():
    if not _donation_access_allowed():
        return jsonify({'success': False, 'error': 'Non authentifié'}), 401

    try:
        coupon_code = (request.form.get('coupon_code') or '').strip()
        note = (request.form.get('note') or '').strip()
        image = request.files.get('coupon_image')

        if not coupon_code:
            return jsonify({'success': False, 'error': 'Code coupon requis'}), 400
        if image is None:
            return jsonify({'success': False, 'error': 'Image coupon requise'}), 400

        safe_code = re.sub(r'[^A-Za-z0-9\-_.]', '_', coupon_code)[:80]
        src_name = secure_filename(image.filename or 'coupon')
        ext = '.jpg'
        if '.' in src_name:
            ext_guess = '.' + src_name.rsplit('.', 1)[1].lower()
            if ext_guess in {'.jpg', '.jpeg', '.png', '.webp'}:
                ext = ext_guess
        ctype = (image.content_type or '').lower()
        if ext == '.jpg' and ('png' in ctype):
            ext = '.png'
        elif ext == '.jpg' and ('webp' in ctype):
            ext = '.webp'

        token = secrets.token_hex(6)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_name = f"coupon_{safe_code}_{stamp}_{token}{ext}"
        out_path = DONATION_DIR / out_name
        image.save(out_path)

        donor_role = request.headers.get('X-User-Role', '') or ('guest' if session.get('guest_session_id') else 'admin')
        meta = {
            'timestamp': datetime.now().isoformat(),
            'coupon_code': coupon_code,
            'note': note,
            'file_name': out_name,
            'role': donor_role,
            'ip': request.headers.get('X-Forwarded-For', request.remote_addr or ''),
        }
        with open(DONATION_DIR / 'coupons.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(meta, ensure_ascii=False) + '\n')

        logger.info(f"💝 Coupon donation reçu: {out_name}")
        return jsonify({'success': True, 'message': 'Coupon reçu, merci pour ton soutien ❤️'})
    except Exception as e:
        logger.error(f"❌ /api/donation/upload-coupon: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# DASHBOARD GUEST
# ============================================

@app.route('/guest')
@guest_required
def guest_dashboard():
    sid = session['guest_session_id']
    with guest_sessions_lock:
        sess = guest_sessions.get(sid, {})
    return render_template('pages/guest_dashboard.html',
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
        current_pct = 0
        if status['in_progress']:
            status['progress'] = downloader.get_progress()
            current_pct = max(0, min(100, int(status['progress'].get('percent', 0))))

        if status.get('batch_active'):
            total = max(1, int(status.get('batch_total', 0) or 0))
            done = max(0, min(total, int(status.get('batch_done', 0) or 0)))
            composed = ((done + (current_pct / 100.0 if status['in_progress'] else 0.0)) / total) * 100.0
            status['batch_percent'] = round(max(0.0, min(100.0, composed)), 1)
        else:
            status['batch_percent'] = float(current_pct)
    return jsonify(status)


@app.route('/api/library', methods=['GET'])
@login_required
def library_tree():
    """Retourne l'arborescence musique pour affichage dashboard."""
    try:
        artists = []
        playlists = []

        if not MUSIC_DIR.exists():
            return jsonify({'success': True, 'artists': artists, 'playlists': playlists})

        for top in sorted([d for d in MUSIC_DIR.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
            direct_songs = sorted(top.glob('*.mp3'), key=lambda p: p.name.lower())
            if direct_songs:
                playlists.append({
                    'name': top.name,
                    'path': str(top.relative_to(MUSIC_DIR)),
                    'songs': [
                        {
                            'name': s.name,
                            'path': str(s.relative_to(MUSIC_DIR)),
                        }
                        for s in direct_songs
                    ]
                })
                continue

            albums = []
            for album_dir in sorted([d for d in top.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
                songs = sorted(album_dir.glob('*.mp3'), key=lambda p: p.name.lower())
                albums.append({
                    'name': album_dir.name,
                    'path': str(album_dir.relative_to(MUSIC_DIR)),
                    'songs': [
                        {
                            'name': s.name,
                            'path': str(s.relative_to(MUSIC_DIR)),
                        }
                        for s in songs
                    ]
                })

            artists.append({
                'name': top.name,
                'path': str(top.relative_to(MUSIC_DIR)),
                'albums': albums,
            })

        return jsonify({'success': True, 'artists': artists, 'playlists': playlists})
    except Exception as e:
        logger.error(f"❌ /api/library: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/move', methods=['POST'])
@login_required
def library_move_song():
    """Déplace un MP3 vers un dossier cible (tri manuel)."""
    try:
        data = request.get_json() or {}
        source = (data.get('source') or '').strip()
        target_folder = (data.get('target_folder') or '').strip()
        if not source or not target_folder:
            return jsonify({'success': False, 'error': 'source/target_folder requis'}), 400

        src = (MUSIC_DIR / source).resolve()
        dst_dir = (MUSIC_DIR / target_folder).resolve()
        base = MUSIC_DIR.resolve()

        if not str(src).startswith(str(base)) or not str(dst_dir).startswith(str(base)):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not src.exists() or src.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier source invalide'}), 404

        dst_dir.mkdir(parents=True, exist_ok=True)
        target = dst_dir / src.name
        if target.exists():
            stem = src.stem
            suffix = src.suffix
            i = 1
            while target.exists():
                target = dst_dir / f"{stem} ({i}){suffix}"
                i += 1

        shutil.move(str(src), str(target))
        rel = str(target.relative_to(MUSIC_DIR))
        return jsonify({'success': True, 'final_path': rel})
    except Exception as e:
        logger.error(f"❌ /api/library/move: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/rename-folder', methods=['POST'])
@login_required
def library_rename_folder():
    """Renomme un dossier dans la bibliothèque."""
    try:
        data = request.get_json() or {}
        folder_path = (data.get('folder_path') or '').strip()
        new_name = (data.get('new_name') or '').strip()
        if not folder_path or not new_name:
            return jsonify({'success': False, 'error': 'folder_path/new_name requis'}), 400

        src = (MUSIC_DIR / folder_path).resolve()
        base = MUSIC_DIR.resolve()
        if not str(src).startswith(str(base)):
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
        return jsonify({'success': True, 'new_path': str(dst.relative_to(MUSIC_DIR))})
    except Exception as e:
        logger.error(f"❌ /api/library/rename-folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/upload-image', methods=['POST'])
@login_required
def library_upload_image():
    """Upload une image dans un dossier de la bibliothèque (nommée folder.<ext>)."""
    try:
        target_folder = (request.form.get('target_folder') or '').strip()
        image = request.files.get('image')

        if not target_folder:
            return jsonify({'success': False, 'error': 'Dossier cible requis'}), 400
        if image is None:
            return jsonify({'success': False, 'error': 'Fichier image requis'}), 400

        dst_dir = (MUSIC_DIR / target_folder).resolve()
        base = MUSIC_DIR.resolve()
        if not str(dst_dir).startswith(str(base)):
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
                return jsonify({'success': False, 'error': 'Format image non supporté (jpg, png, webp)'}), 400

        for old in ('folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp'):
            old_path = dst_dir / old
            if old_path.exists():
                old_path.unlink()

        out_name = f"folder{ext}"
        out_path = dst_dir / out_name
        image.save(out_path)

        rel_path = str(out_path.relative_to(MUSIC_DIR))
        logger.info(f"🖼️ Image dossier uploadée: {rel_path}")
        return jsonify({'success': True, 'path': rel_path})
    except Exception as e:
        logger.error(f"❌ /api/library/upload-image: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/library/folder-cover', methods=['GET'])
@login_required
def library_folder_cover():
    """Retourne la pochette d'un dossier (folder.* ou cover embarquée ID3)."""
    try:
        folder_path = (request.args.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (MUSIC_DIR / folder_path).resolve()
        base = MUSIC_DIR.resolve()
        if not str(folder).startswith(str(base)):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        for name, mime in (
            ('cover.jpg', 'image/jpeg'),
            ('cover.jpeg', 'image/jpeg'),
            ('folder.jpg', 'image/jpeg'),
            ('folder.jpeg', 'image/jpeg'),
            ('folder.png', 'image/png'),
            ('folder.webp', 'image/webp'),
        ):
            p = folder / name
            if p.exists() and p.is_file():
                return send_file(p, mimetype=mime)

        mp3s = sorted(folder.rglob('*.mp3'), key=lambda p: p.name.lower())
        if not mp3s:
            return '', 204

        audio = MP3(mp3s[0])
        tags = getattr(audio, 'tags', None)
        if not tags:
            return '', 204

        for frame in tags.values():
            if isinstance(frame, APIC) and getattr(frame, 'data', None):
                mime = frame.mime or 'image/jpeg'
                return send_file(io.BytesIO(frame.data), mimetype=mime)

        return '', 204
    except Exception as e:
        logger.error(f"❌ /api/library/folder-cover: {e}")
        return '', 204


@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    return jsonify(organizer.get_stats())


@app.route('/api/admin/extract-covers', methods=['POST'])
@login_required
def admin_extract_covers():
    """Extrait/écrit cover.jpg dans chaque dossier album."""
    try:
        data = request.get_json(silent=True) or {}
        overwrite = bool(data.get('overwrite', False))
        result = organizer.extract_album_covers(overwrite=overwrite)
        code = 200 if result.get('success') else 500
        return jsonify(result), code
    except Exception as e:
        logger.error(f"❌ /api/admin/extract-covers: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/prepare-zip', methods=['POST'])
@login_required
def admin_prepare_zip():
    """Crée un ZIP des musiques récentes (admin)."""
    try:
        limit = 200
        zip_path = TEMP_DIR / 'songsurf_admin_recent.zip'

        if zip_path.exists():
            zip_path.unlink()

        files = [p for p in MUSIC_DIR.rglob('*.mp3') if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        files = files[:limit]

        if not files:
            return jsonify({'success': False, 'error': 'Aucune musique disponible pour créer le ZIP.'}), 404

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                arcname = str(f.relative_to(MUSIC_DIR))
                zf.write(f, arcname)

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        logger.info(f"📦 ZIP admin créé: {len(files)} fichiers, {size_mb:.1f} MB")
        return jsonify({
            'success': True,
            'count': len(files),
            'size_mb': round(size_mb, 1),
            'download_url': '/api/admin/download-zip'
        })
    except Exception as e:
        logger.error(f"❌ Erreur ZIP admin: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/download-zip', methods=['GET'])
@login_required
def admin_download_zip():
    """Télécharge le ZIP admin généré."""
    zip_path = TEMP_DIR / 'songsurf_admin_recent.zip'
    if not zip_path.exists():
        return jsonify({'success': False, 'error': 'ZIP non disponible, utilisez /api/admin/prepare-zip d\'abord'}), 404

    return send_file(
        zip_path,
        as_attachment=True,
        download_name='SongSurf_recents_admin.zip',
        mimetype='application/zip'
    )


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
        is_playlist = _is_playlist_url(url)
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


@app.route('/api/prefetch/cover', methods=['GET'])
@login_required
def admin_prefetch_cover():
    """Retourne la pochette APIC ou image sidecar du prefetch admin en cours."""
    token = (request.args.get('token') or '').strip()
    if not token:
        return '', 204

    with admin_prefetch_lock:
        if token != admin_prefetch_state.get('token', ''):
            return '', 204
        if admin_prefetch_state.get('status') != 'ready':
            return '', 204
        file_path = (admin_prefetch_state.get('file_path') or '').strip()

    if not file_path:
        return '', 204

    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return '', 204

    try:
        audio = MP3(p)
        tags = getattr(audio, 'tags', None)
        if tags:
            for frame in tags.values():
                if isinstance(frame, APIC) and getattr(frame, 'data', None):
                    mime = frame.mime or 'image/jpeg'
                    return send_file(io.BytesIO(frame.data), mimetype=mime)
    except Exception as e:
        logger.warning(f"⚠️ Prefetch cover APIC: {e}")

    stem = p.with_suffix('')
    for ext, mime in (('.jpg', 'image/jpeg'), ('.jpeg', 'image/jpeg'), ('.png', 'image/png'), ('.webp', 'image/webp')):
        side = Path(str(stem) + ext)
        if side.exists() and side.is_file():
            return send_file(side, mimetype=mime)

    return '', 204


@app.route('/api/prefetch/cancel', methods=['POST'])
@login_required
def admin_prefetch_cancel():
    """Annule le prefetch courant et supprime les fichiers temporaires associés."""
    try:
        data = request.get_json(silent=True) or {}
        token = (data.get('token') or '').strip()
        ok = _cancel_admin_prefetch(token)
        if not ok:
            return jsonify({'success': False, 'error': 'Prefetch token mismatch'}), 409
        return jsonify({'success': True})
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
        mp4_mode = bool(data.get('mp4_mode', False))
        metadata = {
            'artist': data.get('artist', 'Unknown Artist'),
            'album':  data.get('album',  'Unknown Album'),
            'title':  data.get('title',  'Unknown Title'),
            'year':   data.get('year',   '')
        }
        download_queue.put({'url': url, 'metadata': metadata, 'playlist_mode': playlist_mode, 'mp4_mode': mp4_mode, 'added_at': datetime.now().isoformat()})
        _start_or_extend_batch(1)
        logger.info(f"➕ Admin queue: {metadata['artist']} - {metadata['title']} [playlist_mode={playlist_mode}, mp4_mode={mp4_mode}]")
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
        mp4_mode = bool(data.get('mp4_mode', False))
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
            download_queue.put({'url': song['url'], 'metadata': metadata, 'playlist_mode': playlist_mode, 'mp4_mode': mp4_mode, 'added_at': datetime.now().isoformat()})
            added += 1

        _start_or_extend_batch(added)

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
    _cancel_admin_prefetch('')
    if TEMP_DIR.exists():
        for f in TEMP_DIR.iterdir():
            if f.is_file():
                f.unlink()
                deleted.append(f.name)
    with queue_lock:
        download_status['in_progress'] = False
        download_status['current_download'] = None
        download_status['last_error'] = None
        download_status['batch_active'] = False
        download_status['batch_total'] = 0
        download_status['batch_done'] = 0
        download_status['batch_percent'] = 0
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
        is_playlist = _is_playlist_url(url)
        if is_playlist:
            result = dl.extract_playlist_metadata(url)
            if result.get('success'):
                result['is_playlist'] = True
                _prefetch_first_playlist_song_async(dl, result)
        else:
            result = dl.extract_metadata(url)
            # Aplatir la réponse : sortir les métadonnées du sous-objet 'metadata'
            if result.get('success') and 'metadata' in result:
                meta = result.pop('metadata')
                result.update(meta)
                result['is_playlist'] = False
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
        mp4_mode = bool(data.get('mp4_mode', False))
        metadata = {
            'artist': data.get('artist', 'Unknown Artist'),
            'album':  data.get('album',  'Unknown Album'),
            'title':  data.get('title',  'Unknown Title'),
            'year':   data.get('year',   '')
        }

        sess['queue'].put({'url': url, 'metadata': metadata, 'playlist_mode': playlist_mode, 'mp4_mode': mp4_mode, 'added_at': datetime.now().isoformat()})
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
        mp4_mode = bool(data.get('mp4_mode', False))

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
            sess['queue'].put({'url': song['url'], 'metadata': metadata, 'playlist_mode': playlist_mode, 'mp4_mode': mp4_mode, 'added_at': datetime.now().isoformat()})
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
                mp4_mode = bool(item.get('mp4_mode', False))
                result = downloader.download(url, metadata, mp4_mode=mp4_mode)
                if cancel_flag.is_set():
                    raise Exception("Annulé par l'utilisateur")
                if not result['success']:
                    raise Exception(result.get('error', 'Erreur inconnue'))

                playlist_mode = item.get('playlist_mode', False)
                media_mode = result.get('media_mode', 'mp3')
                org_result = organizer.organize(result['file_path'], metadata, playlist_mode=playlist_mode, media_mode=media_mode)
                if not org_result['success']:
                    raise Exception(org_result.get('error', 'Erreur organisation'))

                with queue_lock:
                    download_status['in_progress'] = False
                    download_status['current_download'] = None
                    download_status['batch_done'] = int(download_status.get('batch_done', 0)) + 1
                    download_status['last_completed'] = {
                        'success': True,
                        'file_path': org_result['final_path'],
                        'metadata': metadata,
                        'timestamp': datetime.now().isoformat()
                    }
                    if download_status.get('batch_done', 0) >= download_status.get('batch_total', 0) and download_queue.qsize() == 0:
                        download_status['batch_active'] = False
                logger.info(f"✅ Admin: {org_result['final_path']}")

            except Exception as e:
                logger.error(f"❌ Admin: {e}")
                with queue_lock:
                    download_status['in_progress'] = False
                    download_status['current_download'] = None
                    download_status['batch_done'] = int(download_status.get('batch_done', 0)) + 1
                    download_status['last_error'] = {
                        'error': str(e), 'metadata': metadata,
                        'timestamp': datetime.now().isoformat()
                    }
                    if download_status.get('batch_done', 0) >= download_status.get('batch_total', 0) and download_queue.qsize() == 0:
                        download_status['batch_active'] = False

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
