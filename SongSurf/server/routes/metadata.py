"""
Routes des infos d'un titre ou d'un album, et de l'assistant « À remplir ».
"""
import re

from flask import Blueprint, jsonify, request

from auth.provider import auth_required, get_current_user
from core.config import logger
from core.storage import _user_music_dir
from core.tags import _album_status, _read_full_meta, _write_song_tags

metadata_bp = Blueprint('metadata', __name__)


@metadata_bp.route('/api/library/song-meta')
@auth_required
def library_song_meta():
    """Full metadata dump for a single MP3 file."""
    try:
        user      = get_current_user()
        music_dir = _user_music_dir(user)
        path      = (request.args.get('path') or '').strip()
        if not path:
            return jsonify({'success': False, 'error': 'path requis'}), 400

        target = (music_dir / path).resolve()
        if not target.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        return jsonify({'success': True, **_read_full_meta(target, music_dir)})
    except Exception as e:
        logger.error(f"❌ /api/library/song-meta: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@metadata_bp.route('/api/library/song-meta/save', methods=['POST'])
@auth_required
def save_song_meta():
    """Writes editable ID3 tags back to an MP3 file."""
    try:
        user      = get_current_user()
        music_dir = _user_music_dir(user)
        data      = request.get_json() or {}
        path      = (data.get('path') or '').strip()
        tags_data = data.get('tags') or {}

        target = (music_dir / path).resolve()
        if not target.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        _write_song_tags(target, tags_data)
        logger.info(f"💾 Tags sauvegardés : {path}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/song-meta/save: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@metadata_bp.route('/api/library/album-tracks')
@auth_required
def library_album_tracks():
    """Tracklist légère d'un album (titre, TRCK, artistes, année, genres) :
    page album, mode « Numéroter » et assistant « À remplir »."""
    try:
        user      = get_current_user()
        music_dir = _user_music_dir(user)
        folder_path = (request.args.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        from library_audit import _read_tags
        items = []
        for f in sorted([p for p in folder.iterdir()
                         if p.is_file() and p.suffix.lower() == '.mp3'],
                        key=lambda p: p.name.lower()):
            tags = _read_tags(f)
            items.append({
                'path':         str(f.relative_to(music_dir)),
                'name':         f.name,
                'title':        tags['title'],
                'track_number': tags['track_number'],
                'artists':      tags['artists'],
                'year':         tags['year'],
                'genres':       tags['genres'],
            })
        return jsonify({'success': True, 'tracks': items})
    except Exception as e:
        logger.error(f"❌ /api/library/album-tracks: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@metadata_bp.route('/api/library/todo')
@auth_required
def library_todo():
    """Albums aux infos incomplètes (année, n° de piste ou genre) de toute la
    bibliothèque de l'utilisateur : bouton et assistant « À remplir » (SSF-13)."""
    try:
        user      = get_current_user()
        music_dir = _user_music_dir(user)
        albums = []
        if music_dir.exists():
            for artist_dir in sorted((d for d in music_dir.iterdir() if d.is_dir()),
                                     key=lambda p: p.name.lower()):
                for album_dir in sorted((d for d in artist_dir.iterdir() if d.is_dir()),
                                        key=lambda p: p.name.lower()):
                    st = _album_status(album_dir, music_dir)
                    if st and not st['complete']:
                        albums.append({**st, 'artist': artist_dir.name,
                                       'artist_path': str(artist_dir.relative_to(music_dir))})
        return jsonify({'success': True, 'albums': albums})
    except Exception as e:
        logger.error(f"❌ /api/library/todo: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@metadata_bp.route('/api/library/album-status')
@auth_required
def library_album_status():
    """Complétude des tags par album d'un artiste (badges de la vue artiste).

    `?folder_path=<dossier artiste>` → par album : nombre de titres sans
    genre / année / numéro de piste.
    """
    try:
        user      = get_current_user()
        music_dir = _user_music_dir(user)
        folder_path = (request.args.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        albums = []
        for album_dir in sorted([d for d in folder.iterdir() if d.is_dir()],
                                key=lambda p: p.name.lower()):
            st = _album_status(album_dir, music_dir)
            if st:
                albums.append(st)
        return jsonify({'success': True, 'albums': albums})
    except Exception as e:
        logger.error(f"❌ /api/library/album-status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


_FORBIDDEN_NAME_CHARS = '<>:"/\\|?*'


def _clean_folder_name(name: str) -> str:
    """Nom de dossier sûr (mêmes caractères interdits que l'organizer)."""
    for ch in _FORBIDDEN_NAME_CHARS:
        name = name.replace(ch, '')
    name = name.strip().rstrip('.')
    return '' if name in ('', '.', '..') else name


@metadata_bp.route('/api/library/album-tags/save', methods=['POST'])
@auth_required
def library_album_tags_save():
    """« Modifier l'album » et « À remplir » (SSF-13) : écrit sur tous les titres
    d'un album les champs fournis parmi `album`, `year`, `genre`.

    Nouveau nom d'album → TALB de chaque titre + dossier renommé (SongSurf et
    Jellyfin restent d'accord). 409 si un album du même nom existe déjà.
    """
    try:
        user      = get_current_user()
        music_dir = _user_music_dir(user)
        data        = request.get_json(silent=True) or {}
        folder_path = (data.get('folder_path') or '').strip()
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        base   = music_dir.resolve()
        folder = (music_dir / folder_path).resolve()
        if folder == base or folder.parent == base or not folder.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        tags = {}
        if 'year' in data:
            year = str(data.get('year') or '').strip()
            if year and not re.fullmatch(r'\d{4}', year):
                return jsonify({'success': False, 'error': 'Année invalide (4 chiffres)'}), 400
            tags['year'] = year
        if 'genre' in data:
            tags['genre'] = str(data.get('genre') or '').strip()

        target = folder
        if 'album' in data:
            new_name = _clean_folder_name(str(data.get('album') or ''))
            if not new_name:
                return jsonify({'success': False, 'error': "Nom d'album invalide"}), 400
            tags['album'] = new_name
            if new_name != folder.name:
                target = folder.parent / new_name
                # Renommage de casse seule (« live » → « Live ») autorisé sur un FS insensible
                if target.exists() and target.resolve() != folder:
                    return jsonify({'success': False, 'error': 'Un album porte déjà ce nom',
                                    'code': 'album_exists'}), 409
                folder.rename(target)

        mp3s = sorted(f for f in target.iterdir() if f.is_file() and f.suffix.lower() == '.mp3')
        updated, errors = 0, []
        for f in mp3s:
            try:
                if tags:
                    _write_song_tags(f, tags)
                updated += 1
            except Exception as e:
                errors.append({'path': str(f.relative_to(base)), 'error': str(e)})

        logger.info(f"💾 Album {folder_path} → {target.name} : {sorted(tags)} sur {updated} titre(s)")
        return jsonify({'success': True, 'path': str(target.relative_to(base)),
                        'updated': updated, 'errors': errors})
    except Exception as e:
        logger.error(f"❌ /api/library/album-tags/save: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
