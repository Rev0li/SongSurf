"""
Worker de téléchargement : traite la file titre par titre, messages d'erreur
cookies, arrêt propre.
"""
import glob
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from genre_lookup import lookup_genres
from organizer import MusicOrganizer
from core import queue
from core.config import activity_logger, dl_logger
from core.progress import _song_clock, _expected_song_seconds, _learn_song_timing
from core.queue import (downloader, download_status, queue_lock, _queue_wakeup,
                        _last_completed_by_user, _last_error_by_user,
                        _start_or_extend_batch, _today)
from core.storage import _user_cookies_file, _user_music_dir, COOKIES_MISSING_MSG

import events_client

logger = logging.getLogger('songsurf')

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


def _cookies_diagnostic(cookies_file: Path) -> str:
    """État du fichier cookies pour les logs : présence + nb d'entrées + âge."""
    try:
        if not cookies_file.is_file():
            return f"cookies ABSENTS ({cookies_file.name})"
        age_days = (time.time() - cookies_file.stat().st_mtime) / 86400
        n = sum(1 for l in cookies_file.read_text(encoding='utf-8', errors='ignore').splitlines()
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

def _batch_progress_after_song():
    """Sous queue_lock : incrémente batch_done et clôture le batch si tout est fini."""
    download_status['batch_done'] = int(download_status.get('batch_done', 0)) + 1
    if (download_status['batch_done'] >= download_status.get('batch_total', 0)
            and queue.store.pending_count() == 0):
        download_status['batch_active'] = False


def _process_song(item):
    """Traite un titre : download → organize → tags, met à jour download_status.

    Toujours non bloquant pour la suite de la file : toute erreur est capturée et
    batch_done est incrémenté dans tous les cas, pour que le batch puisse se clôturer.
    """
    url         = item['url']
    metadata    = item['metadata']
    user_key    = item['user_key']
    user_pseudo = item.get('user_pseudo', '')
    owner       = {'uid': user_key, 'sub': user_pseudo, 'role': item.get('user_role', 'member')}
    cookies_file = _user_cookies_file(owner)

    with queue_lock:
        # Progression remise à zéro AVANT de passer en cours : sinon /api/status voit
        # encore le « completed / 100 % » du titre précédent et la barre fait un bond
        # d'un titre entier en avant, puis recule quand le téléchargement démarre.
        downloader.progress.reset()
        _song_clock['started']  = time.monotonic()
        _song_clock['expected'] = _expected_song_seconds(item.get('duration'))
        download_status.update({
            'in_progress':      True,
            'current_download': {
                'url': url, 'metadata': metadata,
                'user_key': user_key, 'user_pseudo': user_pseudo,
                'started_at': datetime.now().isoformat()
            },
        })
        _last_error_by_user.pop(user_key, None)

    logger.info(f"🎵 {metadata['artist']} - {metadata['title']} [{user_pseudo or user_key[:8]}]")

    try:
        music_dir = _user_music_dir(owner)
        org       = MusicOrganizer(music_dir)

        # Court-circuit doublon : si le titre est déjà en bibliothèque,
        # on ne télécharge même pas (économie de bande passante / quota).
        if org.target_exists(metadata):
            logger.info(f"⏭️ Doublon ignoré (pas de download): {metadata.get('artist')} - {metadata.get('title')}")
            org_result = {'success': True, 'skipped': True, 'final_path': ''}
        else:
            # Cookies supprimés entre la mise en file et le téléchargement.
            if not cookies_file.is_file():
                raise Exception(COOKIES_MISSING_MSG)
            result = downloader.download(url, metadata, cookiefile=str(cookies_file))

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
            try:
                _learn_song_timing(time.monotonic() - _song_clock['started'], item.get('duration'))
            except Exception as e:  # jamais bloquant
                logger.warning(f"⚠️ Estimation de durée non mise à jour : {e}")

        downloader.progress.phase   = 'completed'
        downloader.progress.percent = 100
        _skipped = bool(org_result.get('skipped'))

        with queue_lock:
            download_status['in_progress']    = False
            download_status['current_download'] = None
            _last_completed_by_user[user_key] = {
                'success':   True,
                'skipped':   _skipped,
                'file_path': org_result.get('final_path', ''),
                'metadata':  metadata,
                'timestamp': datetime.now().isoformat(),
            }
            _batch_progress_after_song()

        # Un doublon ignoré ne compte pas comme téléchargement (quota, logs, events).
        if _skipped:
            logger.info(f"✅ Doublon ignoré : {metadata.get('artist')} - {metadata.get('title')}")
        else:
            logger.info(f"✅ {org_result['final_path']}")
            _label = user_pseudo or user_key[:8]
            activity_logger.info(f"🎵 DOWNLOAD | {_label} | {metadata['artist']} - {metadata['title']}")
            dl_logger.info(f"{_label} | {metadata['artist']} | {metadata.get('album', '')} | {metadata['title']}")
            events_client.emit(
                'download_success',
                pseudo=_label,
                artist=metadata.get('artist', ''),
                album=metadata.get('album', ''),
                title=metadata.get('title', ''),
            )
            queue.store.daily_increment(user_key, _today())

    except Exception as e:
        err_msg  = str(e)
        friendly = _friendly_download_error(err_msg)
        if _is_cookie_error(err_msg):
            logger.warning(f"🍪 Échec lié aux cookies/âge — {_cookies_diagnostic(cookies_file)}")
        logger.error(f"❌ {err_msg}")
        with queue_lock:
            download_status['in_progress']    = False
            download_status['current_download'] = None
            _last_error_by_user[user_key] = {
                'error': friendly, 'metadata': metadata, 'url': url,  # url : « Réessayer » (SSF-13)
                'timestamp': datetime.now().isoformat(),
            }
            _batch_progress_after_song()
        events_client.emit(
            'download_failed',
            pseudo=user_pseudo or user_key[:8],
            artist=(metadata or {}).get('artist', ''),
            album=(metadata or {}).get('album', ''),
            title=(metadata or {}).get('title', ''),
            detail={'error': err_msg[:300]},
        )


def _worker_step() -> bool:
    """Traite le prochain titre de la file (round-robin). False si la file est vide.

    Le titre ne quitte la file qu'une fois traité : un arrêt pendant son
    téléchargement le laisse « en cours », il repasse en attente au redémarrage.
    """
    claimed = queue.store.claim_next()
    if claimed is None:
        return False
    item_id, item = claimed
    try:
        _process_song(item)
    except Exception as e:
        logger.error(f"❌ Worker error (titre): {e}")
    finally:
        queue.store.finish(item_id)
    return True


def _resume_pending_batch() -> None:
    """Au boot : une file reprise depuis SQLite rouvre un batch pour la barre de progression."""
    pending = queue.store.pending_count()
    if pending:
        _start_or_extend_batch(pending)
        logger.info(f"♻️ File reprise après redémarrage : {pending} titre(s) en attente")


def queue_worker():
    logger.info("🔄 Queue worker démarré")
    while True:
        try:
            if not _worker_step():
                _queue_wakeup.wait(timeout=1.0)
                _queue_wakeup.clear()
        except Exception as e:
            logger.error(f"❌ Worker error: {e}")
            time.sleep(1)


# ── Arrêt propre ───────────────────────────────────────────────────────────────

# Fichiers intermédiaires yt-dlp/ffmpeg laissés par un arrêt brutal (jamais un MP3 fini).
_TEMP_LEFTOVER_PATTERNS = ('*.part', '*.ytdl', '*.temp.*', '*.part-Frag*')


def _cleanup_temp_leftovers() -> None:
    """Au boot : supprime les restes d'un téléchargement interrompu dans config.TEMP_DIR."""
    removed = 0
    for pattern in _TEMP_LEFTOVER_PATTERNS:
        for f in downloader.temp_dir.glob(pattern):
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    if removed:
        logger.info(f"🧹 {removed} fichier(s) temporaire(s) incomplet(s) supprimé(s)")


def _on_sigterm(signum, _frame):
    """docker stop : supprime les fichiers du titre en cours (incomplets) puis exit 0.

    SongSurf tourne en continu : ce cas ne se présente que sur un stop manuel
    ou un redéploiement. Le titre interrompu reste dans la file et sera repris.
    """
    with queue_lock:
        current = download_status.get('current_download')
    if current:
        prefix = downloader._temp_filename_from_metadata(current.get('metadata') or {})
        for f in downloader.temp_dir.glob(f'{glob.escape(prefix)}*'):
            f.unlink(missing_ok=True)
        logger.warning(f"🛑 Arrêt pendant un téléchargement — fichiers temporaires de « {prefix} » supprimés")
    logger.info(f"🛑 Signal {signum} reçu — arrêt propre")
    sys.exit(0)
