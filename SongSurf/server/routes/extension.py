"""
Routes de l'extension Chrome : cookies YouTube, aperçu, ajout direct à la file.
"""
import threading

from flask import Blueprint, jsonify, request

from auth.provider import auth_required, get_current_user
from core.config import logger
from core.queue import (downloader, QUEUE_FULL_MSG, _daily_limit_response, _duration, _enqueue_job,
                        _is_valid_youtube_url, _job_owner, _queue_full)
from core.storage import _cookies_missing_response, _user_cookies_file, _user_pseudo

extension_bp = Blueprint('extension', __name__)


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


@extension_bp.route('/api/cookies/update', methods=['POST'])
@auth_required
def update_cookies():
    """Extension Chrome — reçoit les cookies YouTube de l'utilisateur courant pour yt-dlp."""
    try:
        user    = get_current_user()
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


@extension_bp.route('/api/preview', methods=['POST'])
@auth_required
def preview_metadata():
    """
    Extension Chrome — extrait les métadonnées sans effet de bord.
    Utilisé pour la mini-analyse avant confirmation.
    """
    try:
        user     = get_current_user()
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


@extension_bp.route('/api/queue-direct', methods=['POST'])
@auth_required
def queue_direct():
    """
    Extension Chrome — extrait les métadonnées et empile côté serveur (fire-and-forget).
    Aucune dépendance à la page SongSurf : le NAS télécharge même si aucun onglet n'est
    ouvert. La réponse est immédiate ; l'extraction yt-dlp tourne dans un thread.
    """
    try:
        user = get_current_user()
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
