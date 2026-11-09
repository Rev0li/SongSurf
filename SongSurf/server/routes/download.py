"""
Routes du téléchargement utilisées par le site : statut, analyse, mise en file.
"""
import time

from flask import Blueprint, jsonify, request

from auth.provider import auth_required, get_current_user, is_identified, unauthenticated_response
from core import queue
from core.config import logger
from core.progress import _song_clock, _song_percent
from core.queue import (downloader, download_status, queue_lock, QUEUE_FULL_MSG,
                        _last_completed_by_user, _last_error_by_user,
                        _daily_limit_for, _daily_limit_response, _duration, _enqueue_job,
                        _is_valid_youtube_url, _job_owner, _queue_full, _today)
from core.storage import _cookies_missing_response, _user_cookies_file, _user_key, _user_pseudo

download_bp = Blueprint('download', __name__)


# ── Download status ────────────────────────────────────────────────────────────

@download_bp.route('/api/status')
def get_status():
    current_user = get_current_user()
    if not is_identified(current_user):
        return unauthenticated_response()
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


# ── Extract / Download ─────────────────────────────────────────────────────────

@download_bp.route('/api/extract', methods=['POST'])
@auth_required
def extract_metadata():
    try:
        user = get_current_user()
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


@download_bp.route('/api/download', methods=['POST'])
@auth_required
def start_download():
    try:
        user = get_current_user()
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


@download_bp.route('/api/download-playlist', methods=['POST'])
@auth_required
def download_playlist():
    try:
        user     = get_current_user()
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
