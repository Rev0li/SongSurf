"""
File de téléchargement : état partagé, quota journalier, mise en file.
"""
import logging
import re
import threading
from datetime import datetime

from flask import jsonify

from downloader import YouTubeDownloader
from state_store import StateStore
from core import config
from core.storage import _user_key, _user_pseudo

logger = logging.getLogger('songsurf')

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


# ── Downloader (global, uses config.TEMP_DIR for staging) ────────────────────────────

downloader = YouTubeDownloader(config.TEMP_DIR, config.BASE_MUSIC_DIR)

# ── Download queue (persistante, round-robin entre utilisateurs) ─────────────────
# La file vit dans SQLite (state_store) : un redémarrage en plein batch reprend là
# où il s'était arrêté. Un album = un job, un titre seul = un job d'une piste ; le
# worker prend les titres un par un, chaque utilisateur à tour de rôle, pour que
# deux membres en parallèle avancent tous les deux. Le serveur est propriétaire de
# la file : elle continue à se vider même si le navigateur quitte la page.
MAX_PENDING_JOBS = 100          # nombre max d'albums/titres en attente, par utilisateur
queue_lock  = threading.Lock()  # download_status + _last_*_by_user
_queue_wakeup = threading.Event()

store = StateStore(config.STATE_DIR / 'songsurf.db')

download_status = {
    'in_progress': False,
    'current_download': None,
    'progress': None,
    'queue_size': 0,
    'batch_active': False,
    'batch_total': 0,
    'batch_done': 0,
    'batch_percent': 0,
}

# Dernier succès / dernière erreur, rangés par clé utilisateur : /api/status ne renvoie
# que ceux de l'appelant (jamais le titre ou le chemin d'un autre membre). Sous queue_lock.
_last_completed_by_user = {}
_last_error_by_user     = {}

QUEUE_FULL_MSG = 'File pleine, réessaie dans un instant.'


# ── Daily download quota (par utilisateur, admin illimité) ─────────────────────

def _today() -> str:
    return datetime.now().date().isoformat()


def _daily_limit_for(user: dict) -> int:
    """Quota du jour de l'utilisateur ; 0 = illimité (admin, ou limite désactivée)."""
    if user.get('role') == 'admin':
        return 0
    return max(0, config.DAILY_DOWNLOAD_LIMIT)


def _daily_limit_reached(user: dict) -> bool:
    limit = _daily_limit_for(user)
    return limit > 0 and store.daily_count(_user_key(user), _today()) >= limit


def _daily_limit_response(user: dict):
    """429 si le quota du jour est atteint, sinon None."""
    if not _daily_limit_reached(user):
        return None
    limit = _daily_limit_for(user)
    return jsonify({'success': False, 'error': f'Limite journalière atteinte ({limit} titres/jour).',
                    'code': 'daily_limit'}), 429


def _queue_full(user: dict) -> bool:
    return store.pending_jobs(_user_key(user)) >= MAX_PENDING_JOBS


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


def _job_owner(user: dict) -> dict:
    """Champs propriétaire recopiés dans chaque titre de la file."""
    return {
        'user_key':    _user_key(user),
        'user_pseudo': _user_pseudo(user),
        'user_role':   user.get('role', 'member'),
        'added_at':    datetime.now().isoformat(),
    }


def _duration(value) -> int:
    """Durée d'un titre en secondes (0 si inconnue) : sert à estimer son avancement."""
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _enqueue_job(user: dict, songs):
    """Empile un job (liste de titres) de `user` dans la file persistante.

    L'appelant vérifie _queue_full() avant (→ 429).
    """
    if not songs:
        return 0
    added = store.enqueue_job(_user_key(user), list(songs))
    _start_or_extend_batch(added)
    _queue_wakeup.set()
    return added
