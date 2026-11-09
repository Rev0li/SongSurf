"""
Outils réservés à l'admin : numérotation, genre d'artiste, audit iTunes, journal.
"""
from flask import Blueprint, jsonify, request

from auth.provider import admin_only_response, auth_required, get_current_user, is_admin
from core import config
from core.config import logger
from core.storage import _user_music_dir
from core.tags import _EDITABLE_FIELDS, _write_song_tags

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/api/admin/dl-logs')
@auth_required
def api_admin_dl_logs():
    user = get_current_user()
    if user.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Admin requis'}), 403

    pseudo = (request.args.get('pseudo') or '').strip().lower()
    # `limit=all` : historique complet (fiches par membre du portail) ;
    # sinon 1..500, 100 par défaut ou si la valeur est illisible.
    raw_limit = (request.args.get('limit') or '100').strip().lower()
    if raw_limit == 'all':
        limit = None
    else:
        try:
            limit = min(max(1, int(raw_limit)), 500)
        except ValueError:
            limit = 100

    log_path = config.LOG_DIR / 'downloads.log'
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
    return jsonify({'success': True, 'entries': entries if limit is None else entries[:limit],
                    'total': len(entries)})


@admin_bp.route('/api/library/audit/artist')
@auth_required
def library_audit_artist():
    """Rapport iTunes + cohérence ID3 pour tous les albums d'un artiste.
    Outil expert : admin uniquement (SSF-13)."""
    try:
        user = get_current_user()
        if not is_admin(user):
            return admin_only_response()
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
        logger.error(f"❌ /api/library/audit/artist: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/library/audit/apply', methods=['POST'])
@auth_required
def library_audit_apply():
    """Applique les recommandations cochées : [{path, field, value}].
    Outil expert : admin uniquement (SSF-13)."""
    try:
        user = get_current_user()
        if not is_admin(user):
            return admin_only_response()
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
        logger.error(f"❌ /api/library/audit/apply: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/library/renumber-album', methods=['POST'])
@auth_required
def library_renumber_album():
    """Réécrit TRCK `i/total` sur tout un album, dans l'ordre fourni.

    `paths` doit couvrir exactement les MP3 du dossier : garantit une
    numérotation 1..N cohérente (pas de trous ni de doublons).
    Outil expert : admin uniquement (SSF-13).
    """
    try:
        user      = get_current_user()
        if not is_admin(user):
            return admin_only_response()
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


@admin_bp.route('/api/library/set-artist-genre', methods=['POST'])
@auth_required
def library_set_artist_genre():
    """Écrit TCON sur tous les MP3 d'un dossier artiste (tous ses albums).

    `genre` accepte plusieurs valeurs séparées par « ; » (frame multi-valeurs,
    même convention que l'éditeur de métadonnées). Écrase le genre existant.
    Outil expert : admin uniquement (SSF-13).
    """
    try:
        user      = get_current_user()
        if not is_admin(user):
            return admin_only_response()
        music_dir = _user_music_dir(user)
        data        = request.get_json(silent=True) or {}
        folder_path = (data.get('folder_path') or '').strip()
        genre       = str(data.get('genre') or '').strip()
        if not folder_path or not genre:
            return jsonify({'success': False, 'error': 'folder_path et genre requis'}), 400

        base   = music_dir.resolve()
        folder = (music_dir / folder_path).resolve()
        if folder == base or not folder.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        mp3s = sorted(f for f in folder.rglob('*')
                      if f.is_file() and f.suffix.lower() == '.mp3')
        updated, errors = 0, []
        for f in mp3s:
            try:
                _write_song_tags(f, {'genre': genre})
                updated += 1
            except Exception as e:
                errors.append({'path': str(f.relative_to(base)), 'error': str(e)})

        logger.info(f"🎼 Genre « {genre} » appliqué à {updated} titre(s) : {folder_path}")
        return jsonify({'success': True, 'updated': updated, 'errors': errors})
    except Exception as e:
        logger.error(f"❌ /api/library/set-artist-genre: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
