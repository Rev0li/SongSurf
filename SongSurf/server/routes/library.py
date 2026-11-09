"""
Routes de la bibliothèque : arbre, déplacements, suppressions, pochettes.
"""
import io
import secrets
import shutil
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from mutagen.id3 import APIC
from mutagen.mp3 import MP3

from auth.provider import admin_only_response, auth_required, get_current_user, is_admin
from core.config import logger
from core.storage import _user_music_dir, _user_pseudo
from core.tags import _sync_mp3_tags
from organizer import MusicOrganizer

library_bp = Blueprint('library', __name__)


def _build_library_tree(music_dir: Path) -> dict:
    artists = []
    if not music_dir.exists():
        return {'artists': artists}
    for top in sorted([d for d in music_dir.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
        albums = []
        for album_dir in sorted([d for d in top.iterdir() if d.is_dir()], key=lambda p: p.name.lower()):
            songs = sorted(
                [f for f in album_dir.iterdir() if f.is_file() and f.suffix.lower() == '.mp3'],
                key=lambda p: p.name.lower()
            )
            albums.append({
                'name':  album_dir.name,
                'path':  str(album_dir.relative_to(music_dir)),
                'songs': [{'name': s.name, 'path': str(s.relative_to(music_dir))} for s in songs],
            })
        _PIC_NAMES = ('folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp',
                      'artist.jpg', 'artist.jpeg', 'artist.png', 'artist.webp')
        has_picture = any((top / n).exists() for n in _PIC_NAMES)
        artists.append({'name': top.name, 'path': str(top.relative_to(music_dir)), 'albums': albums, 'has_picture': has_picture})
    return {'artists': artists}


@library_bp.route('/api/library')
@auth_required
def library_tree():
    try:
        user = get_current_user()
        tree = _build_library_tree(_user_music_dir(user))
        return jsonify({'success': True, **tree})
    except Exception as e:
        logger.error(f"❌ /api/library: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@library_bp.route('/api/library/move', methods=['POST'])
@auth_required
def library_move_song():
    try:
        user      = get_current_user()
        music_dir = _user_music_dir(user)
        data          = request.get_json() or {}
        source        = (data.get('source') or '').strip()
        target_folder = (data.get('target_folder') or '').strip()
        if not source or not target_folder:
            return jsonify({'success': False, 'error': 'source/target_folder requis'}), 400

        src     = (music_dir / source).resolve()
        dst_dir = (music_dir / target_folder).resolve()
        base    = music_dir.resolve()

        if not src.is_relative_to(base) or not dst_dir.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not src.exists() or src.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier source invalide'}), 404

        dst_dir.mkdir(parents=True, exist_ok=True)
        target = dst_dir / src.name
        i = 1
        while target.exists():
            target = dst_dir / f"{src.stem} ({i}){src.suffix}"
            i += 1

        src_parts  = src.relative_to(base).parts
        old_artist = src_parts[0] if len(src_parts) == 3 else None
        shutil.move(str(src), str(target))
        _sync_mp3_tags(target, music_dir, old_artist=old_artist)
        return jsonify({'success': True, 'final_path': str(target.relative_to(music_dir))})
    except Exception as e:
        logger.error(f"❌ /api/library/move: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@library_bp.route('/api/library/move-folder', methods=['POST'])
@auth_required
def library_move_folder():
    """Move an album folder to a different artist folder."""
    try:
        user      = get_current_user()
        music_dir = _user_music_dir(user)
        data        = request.get_json() or {}
        folder_path = (data.get('folder_path') or '').strip()
        new_parent  = (data.get('new_parent') or '').strip()
        if not folder_path or not new_parent:
            return jsonify({'success': False, 'error': 'folder_path/new_parent requis'}), 400

        src        = (music_dir / folder_path).resolve()
        dst_parent = (music_dir / new_parent).resolve()
        base       = music_dir.resolve()

        if not src.is_relative_to(base) or not dst_parent.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not src.exists() or not src.is_dir():
            return jsonify({'success': False, 'error': 'Dossier source introuvable'}), 404
        if not dst_parent.exists() or not dst_parent.is_dir():
            return jsonify({'success': False, 'error': 'Dossier cible introuvable'}), 404
        if src.parent == dst_parent:
            return jsonify({'success': False, 'error': 'Album déjà dans cet artiste'}), 400

        dst = dst_parent / src.name
        if dst.exists():
            for item in list(src.iterdir()):
                target = dst / item.name
                if target.exists():
                    counter = 1
                    while target.exists():
                        if item.is_dir():
                            target = dst / f"{item.name} ({counter})"
                        else:
                            target = dst / f"{item.stem} ({counter}){item.suffix}"
                        counter += 1
                shutil.move(str(item), str(target))
            src.rmdir()
        else:
            shutil.move(str(src), str(dst))

        old_parent = src.parent
        if old_parent != base and old_parent.exists() and not any(old_parent.iterdir()):
            old_parent.rmdir()

        old_artist = old_parent.name if old_parent != base else None
        for mp3 in dst.rglob('*.mp3'):
            _sync_mp3_tags(mp3, music_dir, old_artist=old_artist)

        return jsonify({'success': True, 'new_path': str(dst.relative_to(music_dir))})
    except Exception as e:
        logger.error(f"❌ /api/library/move-folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@library_bp.route('/api/library/delete-folder', methods=['POST'])
@auth_required
def library_delete_folder():
    """Delete an artist or album folder — admin only (the admin library is permanent)."""
    try:
        user = get_current_user()
        if user.get('role') != 'admin':
            return jsonify({'success': False, 'error': 'Admin requis'}), 403
        music_dir   = _user_music_dir(user)
        data        = request.get_json() or {}
        folder_path = (data.get('folder_path') or '').strip().strip('/')
        if not folder_path:
            return jsonify({'success': False, 'error': 'folder_path requis'}), 400

        folder = (music_dir / folder_path).resolve()
        base   = music_dir.resolve()
        if folder == base or not folder.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        deleted_songs = len(list(folder.rglob('*.mp3')))
        shutil.rmtree(folder)

        # Album supprimé → retire le dossier artiste s'il est devenu vide
        parent = folder.parent
        if parent != base and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

        logger.info(f"🗑️ Dossier supprimé: {folder_path} ({deleted_songs} titre(s)) par {_user_pseudo(user)}")
        return jsonify({'success': True, 'deleted_songs': deleted_songs})
    except Exception as e:
        logger.error(f"❌ /api/library/delete-folder: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Les URLs d'images sont versionnées côté frontend (?t=<version>, incrémentée
# uniquement à l'upload d'une pochette) : le navigateur peut donc mettre les
# réponses en cache sans risque de servir une image périmée.
_IMAGE_CACHE_CONTROL = 'private, max-age=86400'


def _image_response(path_or_buffer, mime):
    resp = send_file(path_or_buffer, mimetype=mime)
    resp.headers['Cache-Control'] = _IMAGE_CACHE_CONTROL
    return resp


@library_bp.route('/api/library/folder-cover')
@auth_required
def library_folder_cover():
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
            return '', 204

        for name, mime in (
            ('cover.jpg', 'image/jpeg'), ('cover.jpeg', 'image/jpeg'),
            ('folder.jpg', 'image/jpeg'), ('folder.jpeg', 'image/jpeg'),
            ('folder.png', 'image/png'),  ('folder.webp', 'image/webp'),
            ('artist.jpg', 'image/jpeg'), ('artist.jpeg', 'image/jpeg'),
            ('artist.png', 'image/png'),  ('artist.webp', 'image/webp'),
        ):
            p = folder / name
            if p.exists():
                return _image_response(p, mime)

        mp3s = sorted(folder.rglob('*.mp3'), key=lambda p: p.name.lower())
        if not mp3s:
            return '', 204

        audio = MP3(mp3s[0])
        tags  = getattr(audio, 'tags', None)
        if tags:
            for frame in tags.values():
                if isinstance(frame, APIC) and getattr(frame, 'data', None):
                    # Persiste l'extraction en cover.jpg (dossier album uniquement,
                    # pas un dossier artiste) : les requêtes suivantes servent le
                    # fichier au lieu de re-parser le MP3 à chaque affichage.
                    if mp3s[0].parent == folder:
                        jpeg = MusicOrganizer(music_dir)._convert_image_bytes_to_jpeg(frame.data)
                        if jpeg:
                            try:
                                cover = folder / 'cover.jpg'
                                tmp   = folder / f'.cover-{secrets.token_hex(4)}.tmp'
                                tmp.write_bytes(jpeg)
                                tmp.replace(cover)  # rename atomique : jamais de fichier tronqué servi
                                return _image_response(cover, 'image/jpeg')
                            except OSError:
                                pass
                    return _image_response(io.BytesIO(frame.data), frame.mime or 'image/jpeg')
        return '', 204
    except Exception as e:
        logger.error(f"❌ /api/library/folder-cover: {e}")
        return '', 204


@library_bp.route('/api/library/artist-picture')
@auth_required
def library_artist_picture():
    """Artist picture: looks for folder.jpg first, then artist.jpg (legacy fallback)."""
    try:
        user        = get_current_user()
        music_dir   = _user_music_dir(user)
        folder_path = (request.args.get('folder_path') or '').strip()
        folder      = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return '', 204
        if not folder.exists() or not folder.is_dir():
            return '', 204
        for name, mime in (
            ('folder.jpg', 'image/jpeg'), ('folder.jpeg', 'image/jpeg'),
            ('folder.png', 'image/png'),  ('folder.webp', 'image/webp'),
            ('artist.jpg', 'image/jpeg'), ('artist.jpeg', 'image/jpeg'),
            ('artist.png', 'image/png'),  ('artist.webp', 'image/webp'),
        ):
            p = folder / name
            if p.exists():
                return _image_response(p, mime)
        return '', 204
    except Exception:
        return '', 204


@library_bp.route('/api/library/artist-cover/upload', methods=['POST'])
@auth_required
def upload_artist_cover():
    """Saves uploaded image as artist.jpg in the artist folder."""
    try:
        user        = get_current_user()
        music_dir   = _user_music_dir(user)
        folder_path = (request.form.get('folder_path') or '').strip()
        file        = request.files.get('image')
        if not folder_path or not file:
            return jsonify({'success': False, 'error': 'folder_path et image requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        mime = file.content_type or 'image/jpeg'
        ext  = '.jpg' if 'jpeg' in mime or 'jpg' in mime else '.png'
        with open(folder / f'folder{ext}', 'wb') as f:
            f.write(file.read())

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/artist-cover/upload: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@library_bp.route('/api/library/album-cover/upload', methods=['POST'])
@auth_required
def upload_album_cover():
    """Saves uploaded image as cover.jpg in the album folder (no MP3 embedding)."""
    try:
        user        = get_current_user()
        music_dir   = _user_music_dir(user)
        folder_path = (request.form.get('folder_path') or '').strip()
        file        = request.files.get('image')
        if not folder_path or not file:
            return jsonify({'success': False, 'error': 'folder_path et image requis'}), 400

        folder = (music_dir / folder_path).resolve()
        if not folder.is_relative_to(music_dir.resolve()):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not folder.exists() or not folder.is_dir():
            return jsonify({'success': False, 'error': 'Dossier introuvable'}), 404

        mime = file.content_type or 'image/jpeg'
        ext  = '.jpg' if 'jpeg' in mime or 'jpg' in mime else '.png'
        with open(folder / f'cover{ext}', 'wb') as f:
            f.write(file.read())

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"❌ /api/library/album-cover/upload: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@library_bp.route('/api/library/delete-song', methods=['POST'])
@auth_required
def library_delete_song():
    """Supprime un titre — admin uniquement (SSF-13). Album devenu sans MP3 →
    dossier retiré (pochette comprise), puis l'artiste s'il est vide."""
    try:
        user = get_current_user()
        if not is_admin(user):
            return admin_only_response()
        music_dir = _user_music_dir(user)
        path      = ((request.get_json(silent=True) or {}).get('path') or '').strip()
        if not path:
            return jsonify({'success': False, 'error': 'path requis'}), 400

        base   = music_dir.resolve()
        target = (music_dir / path).resolve()
        if not target.is_relative_to(base):
            return jsonify({'success': False, 'error': 'Chemin invalide'}), 400
        if not target.exists() or not target.is_file() or target.suffix.lower() != '.mp3':
            return jsonify({'success': False, 'error': 'Fichier MP3 introuvable'}), 404

        target.unlink()
        album = target.parent
        removed_album = False
        if album != base and not any(f.suffix.lower() == '.mp3' for f in album.rglob('*') if f.is_file()):
            shutil.rmtree(album)
            removed_album = True
            artist = album.parent
            if artist != base and artist.exists() and not any(artist.iterdir()):
                artist.rmdir()

        logger.info(f"🗑️ Titre supprimé : {path} par {_user_pseudo(user)}")
        return jsonify({'success': True, 'removed_album': removed_album})
    except Exception as e:
        logger.error(f"❌ /api/library/delete-song: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
