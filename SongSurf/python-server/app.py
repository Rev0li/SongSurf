#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SongSurf - Serveur de téléchargement musical

Dashboard web avec authentification pour télécharger de la musique
depuis YouTube Music via yt-dlp. Organise automatiquement les fichiers MP3.

Usage:
  python app.py

  Serveur sur http://0.0.0.0:8080
"""

# Fix encodage Windows
import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
import threading
import time
import queue
import os
import secrets

from downloader import YouTubeDownloader
from organizer import MusicOrganizer

# ============================================
# CONFIGURATION
# ============================================

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(days=7)

# Mot de passe du dashboard (OBLIGATOIRE en production)
DASHBOARD_PASSWORD = os.getenv('SONGSURF_PASSWORD', '')

if not DASHBOARD_PASSWORD:
    print("⚠️  SONGSURF_PASSWORD non défini ! Le dashboard sera non protégé.")
    print("   Définissez-le dans docker-compose.yml ou en variable d'environnement.")

# Dossiers
if Path(__file__).parent == Path('/app'):
    TEMP_DIR = Path('/data/temp')
    MUSIC_DIR = Path('/data/music')
else:
    BASE_DIR = Path(__file__).parent.parent
    TEMP_DIR = BASE_DIR / "temp"
    MUSIC_DIR = BASE_DIR / "music"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# Instances
downloader = YouTubeDownloader(TEMP_DIR, MUSIC_DIR)
organizer = MusicOrganizer(MUSIC_DIR)

# Queue de téléchargement
MAX_QUEUE_SIZE = 50
download_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
queue_lock = threading.Lock()
cancel_flag = threading.Event()

# État global
download_status = {
    'in_progress': False,
    'current_download': None,
    'last_completed': None,
    'last_error': None,
    'progress': None,
    'queue_size': 0,
}

# ============================================
# AUTHENTIFICATION + ANTI-BRUTEFORCE
# ============================================

# Tracking des tentatives de login par IP
# { ip: { 'attempts': int, 'locked_until': datetime | None } }
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def _get_client_ip():
    """Récupère l'IP réelle (supporte reverse proxy)"""
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()


def _is_locked(ip):
    """Vérifie si une IP est bloquée"""
    info = login_attempts.get(ip)
    if not info or not info.get('locked_until'):
        return False
    if datetime.now() >= info['locked_until']:
        # Lockout expiré, reset
        login_attempts.pop(ip, None)
        return False
    return True


def _remaining_lockout(ip):
    """Retourne le temps restant de blocage en minutes"""
    info = login_attempts.get(ip, {})
    locked_until = info.get('locked_until')
    if not locked_until:
        return 0
    remaining = (locked_until - datetime.now()).total_seconds()
    return max(1, int(remaining // 60) + 1)


def _record_failed_attempt(ip):
    """Enregistre un échec de login"""
    if ip not in login_attempts:
        login_attempts[ip] = {'attempts': 0, 'locked_until': None}
    login_attempts[ip]['attempts'] += 1
    attempts = login_attempts[ip]['attempts']
    print(f"🚫 Échec login depuis {ip} ({attempts}/{MAX_LOGIN_ATTEMPTS})")
    if attempts >= MAX_LOGIN_ATTEMPTS:
        login_attempts[ip]['locked_until'] = datetime.now() + LOCKOUT_DURATION
        print(f"🔒 IP {ip} bloquée pour {LOCKOUT_DURATION.total_seconds()//60:.0f} minutes")


def _reset_attempts(ip):
    """Reset le compteur après un login réussi"""
    login_attempts.pop(ip, None)


def login_required(f):
    """Décorateur : redirige vers /login si non authentifié"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not DASHBOARD_PASSWORD:
            return f(*args, **kwargs)
        if not session.get('authenticated'):
            if request.is_json:
                return jsonify({'success': False, 'error': 'Non authentifié'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion avec protection anti-bruteforce"""
    if not DASHBOARD_PASSWORD:
        session['authenticated'] = True
        session.permanent = True
        return redirect(url_for('dashboard'))

    ip = _get_client_ip()
    error = None

    # Vérifier si l'IP est bloquée
    if _is_locked(ip):
        minutes = _remaining_lockout(ip)
        error = f'Trop de tentatives. Réessayez dans {minutes} min.'
        return render_template('login.html', error=error, locked=True)

    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == DASHBOARD_PASSWORD:
            session['authenticated'] = True
            session.permanent = True
            _reset_attempts(ip)
            return redirect(url_for('dashboard'))
        else:
            _record_failed_attempt(ip)
            if _is_locked(ip):
                minutes = _remaining_lockout(ip)
                error = f'Trop de tentatives. Réessayez dans {minutes} min.'
            else:
                remaining = MAX_LOGIN_ATTEMPTS - login_attempts.get(ip, {}).get('attempts', 0)
                error = f'Mot de passe incorrect ({remaining} essai{"s" if remaining > 1 else ""} restant{"s" if remaining > 1 else ""})'

    return render_template('login.html', error=error, locked=_is_locked(ip))


@app.route('/logout')
def logout():
    """Déconnexion"""
    session.clear()
    return redirect(url_for('login'))


# ============================================
# DASHBOARD
# ============================================

@app.route('/')
@login_required
def dashboard():
    """Page principale du dashboard"""
    stats = organizer.get_stats()
    return render_template('dashboard.html', stats=stats)


# ============================================
# API
# ============================================

@app.route('/ping', methods=['GET'])
def ping():
    """Health check (public)"""
    return jsonify({
        'status': 'ok',
        'message': 'SongSurf is running',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/status', methods=['GET'])
@login_required
def get_status():
    """Statut du téléchargement en cours"""
    with queue_lock:
        status = download_status.copy()
        status['queue_size'] = download_queue.qsize()
        if status['in_progress']:
            status['progress'] = downloader.get_progress()
        return jsonify(status)


@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """Statistiques de la bibliothèque"""
    return jsonify(organizer.get_stats())


@app.route('/api/extract', methods=['POST'])
@login_required
def extract_metadata():
    """Extrait les métadonnées d'une URL YouTube"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400

        print(f"🔍 Extraction: {url}")

        # Playlist/Album ou chanson simple ?
        if '/playlist?list=' in url or '/browse/' in url:
            result = downloader.extract_playlist_metadata(url)
        else:
            result = downloader.extract_metadata(url)

        return jsonify(result)

    except Exception as e:
        print(f"❌ Erreur extraction: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download', methods=['POST'])
@login_required
def start_download():
    """Ajoute un téléchargement à la queue"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400

        if download_queue.full():
            return jsonify({'success': False, 'error': f'Queue pleine ({MAX_QUEUE_SIZE} max)'}), 429

        metadata = {
            'artist': data.get('artist', 'Unknown Artist'),
            'album': data.get('album', 'Unknown Album'),
            'title': data.get('title', 'Unknown Title'),
            'year': data.get('year', '')
        }

        download_queue.put({
            'url': url,
            'metadata': metadata,
            'added_at': datetime.now().isoformat()
        })

        print(f"➕ Queue: {metadata['artist']} - {metadata['title']} ({download_queue.qsize()}/{MAX_QUEUE_SIZE})")

        return jsonify({
            'success': True,
            'message': 'Ajouté à la queue',
            'queue_size': download_queue.qsize()
        })

    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download-playlist', methods=['POST'])
@login_required
def download_playlist():
    """Ajoute toutes les chansons d'une playlist à la queue"""
    try:
        data = request.get_json()
        url = data.get('url', '')
        playlist = data.get('playlist_metadata', {})

        if not url or not playlist:
            return jsonify({'success': False, 'error': 'Données manquantes'}), 400

        songs = playlist.get('songs', [])
        added = 0

        for song in songs:
            if download_queue.full():
                break

            metadata = {
                'artist': song.get('artist', playlist.get('artist', 'Unknown')),
                'album': playlist.get('title', 'Unknown Album'),
                'title': song['title'],
                'year': playlist.get('year', '')
            }

            download_queue.put({
                'url': song['url'],
                'metadata': metadata,
                'added_at': datetime.now().isoformat()
            })
            added += 1

        print(f"💿 Playlist: {added}/{len(songs)} chansons ajoutées")

        return jsonify({
            'success': True,
            'added': added,
            'total': len(songs),
            'queue_size': download_queue.qsize()
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cancel', methods=['POST'])
@login_required
def cancel_download():
    """Annule le téléchargement en cours"""
    if not download_status['in_progress']:
        return jsonify({'success': False, 'error': 'Aucun téléchargement en cours'}), 400
    cancel_flag.set()
    return jsonify({'success': True, 'message': 'Annulation demandée'})


@app.route('/api/cleanup', methods=['POST'])
@login_required
def cleanup():
    """Nettoie le dossier temp"""
    deleted = []
    if TEMP_DIR.exists():
        for f in TEMP_DIR.iterdir():
            if f.is_file():
                f.unlink()
                deleted.append(f.name)
    download_status['in_progress'] = False
    download_status['current_download'] = None
    download_status['last_error'] = None
    print(f"🧹 Nettoyage: {len(deleted)} fichiers supprimés")
    return jsonify({'success': True, 'deleted': len(deleted)})


# ============================================
# QUEUE WORKER
# ============================================

def queue_worker():
    """Thread qui traite la queue de téléchargements"""
    print("🔄 Queue worker démarré")

    while True:
        try:
            item = download_queue.get()
            if item is None:
                break

            url = item['url']
            metadata = item['metadata']
            cancel_flag.clear()

            with queue_lock:
                download_status['in_progress'] = True
                download_status['current_download'] = {
                    'url': url,
                    'metadata': metadata,
                    'started_at': datetime.now().isoformat()
                }
                download_status['last_error'] = None

            print(f"\n🎵 Téléchargement: {metadata['artist']} - {metadata['title']}")

            try:
                # Étape 1 : Télécharger
                result = downloader.download(url, metadata)

                if cancel_flag.is_set():
                    raise Exception("Annulé par l'utilisateur")

                if not result['success']:
                    raise Exception(result.get('error', 'Erreur inconnue'))

                # Étape 2 : Organiser
                org_result = organizer.organize(result['file_path'], metadata)

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

                print(f"✅ Terminé: {org_result['final_path']}")

            except Exception as e:
                print(f"❌ Erreur: {e}")
                with queue_lock:
                    download_status['in_progress'] = False
                    download_status['current_download'] = None
                    download_status['last_error'] = {
                        'error': str(e),
                        'metadata': metadata,
                        'timestamp': datetime.now().isoformat()
                    }

            download_queue.task_done()

        except Exception as e:
            print(f"❌ Queue worker error: {e}")
            time.sleep(1)


# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🎵 SongSurf - Dashboard Musical")
    print("=" * 60)
    print(f"📁 Temp:  {TEMP_DIR}")
    print(f"📁 Music: {MUSIC_DIR}")
    print(f"🔐 Auth:  {'✅ Protégé' if DASHBOARD_PASSWORD else '⚠️  OUVERT (définir SONGSURF_PASSWORD)'}")
    print(f"📊 Queue: max {MAX_QUEUE_SIZE}")
    print("=" * 60)
    print("🚀 http://0.0.0.0:8080")
    print("=" * 60 + "\n")

    # Démarrer le worker
    worker = threading.Thread(target=queue_worker, daemon=True)
    worker.start()

    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
