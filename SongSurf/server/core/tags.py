"""
Lecture et écriture des tags ID3 des MP3 de la bibliothèque.
"""
import logging
import threading
from pathlib import Path

logger = logging.getLogger('songsurf')

def _retarget_artists(artists: list[str], old_artist: str | None, new_artist: str) -> list[str]:
    """TPE1 après un déplacement : seul l'artiste principal change, les featurings restent.

    Même artiste (déplacement entre ses albums) → TPE1 inchangé. Sinon l'ancien
    artiste est remplacé là où il apparaît, à défaut le premier de la liste.
    """
    if not artists:
        return [new_artist]
    if not old_artist or old_artist == new_artist:
        return list(artists)
    if old_artist in artists:
        out = [new_artist if a == old_artist else a for a in artists]
    else:
        out = [new_artist, *artists[1:]]
    return list(dict.fromkeys(out))  # dédoublonne en gardant l'ordre


def _sync_mp3_tags(file_path: Path, music_dir: Path, old_artist: str | None = None) -> None:
    """Met les tags d'un MP3 déplacé en accord avec son nouveau dossier (SSF-13).

    Structure assumed:
      Artist/Album/song.mp3  →  TALB = Album, TPE2 = Artist, TPE1 : artiste
                                principal remplacé (featurings gardés)
      Album/song.mp3         →  TALB = Album  (playlist mode)
    `old_artist` = dossier artiste d'origine (None si inconnu).
    """
    if file_path.suffix.lower() != '.mp3':
        return
    try:
        rel   = file_path.relative_to(music_dir)
        parts = rel.parts  # ('Artist','Album','song.mp3') or ('Album','song.mp3')
        if len(parts) == 3:
            artist, album = parts[0], parts[1]
        elif len(parts) == 2:
            artist, album = None, parts[0]
        else:
            return
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TPE1, TPE2, TALB
        audio = MP3(file_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        if artist:
            current = [str(a).strip() for a in (audio.tags['TPE1'].text if 'TPE1' in audio.tags else [])
                       if str(a).strip()]
            audio.tags['TPE1'] = TPE1(encoding=3, text=_retarget_artists(current, old_artist, artist))
            audio.tags['TPE2'] = TPE2(encoding=3, text=artist)
        audio.tags['TALB'] = TALB(encoding=3, text=album)
        audio.save()
    except Exception as e:
        logger.warning(f"⚠️ sync_mp3_tags({file_path.name}): {e}")


# Champs acceptés par l'éditeur et l'audit (clés de _FRAME_MAP + comment)
_EDITABLE_FIELDS = {
    'title', 'artist', 'album_artist', 'album', 'year', 'track_number',
    'disc_number', 'genre', 'composer', 'copyright', 'publisher', 'bpm',
    'key', 'language', 'isrc', 'encoded_by', 'comment',
}


def _write_song_tags(target: Path, tags_data: dict) -> None:
    """Writes editable ID3 frames to an MP3 (shared: metadata editor + audit apply)."""
    from mutagen.mp3 import MP3 as _MP3
    from mutagen.id3 import (ID3 as _ID3, TIT2, TPE1, TPE2, TALB, TDRC,
                              TRCK, TPOS, TCON, TCOM, TCOP, TPUB, TBPM,
                              TKEY, TLAN, TSRC, TENC, COMM)
    _FRAME_MAP = {
        'title':        TIT2, 'artist':       TPE1, 'album_artist': TPE2,
        'album':        TALB, 'year':         TDRC, 'track_number': TRCK,
        'disc_number':  TPOS, 'genre':        TCON, 'composer':     TCOM,
        'copyright':    TCOP, 'publisher':    TPUB, 'bpm':          TBPM,
        'key':          TKEY, 'language':     TLAN, 'isrc':         TSRC,
        'encoded_by':   TENC,
    }
    # Champs multi-valeurs : « A; B » → valeurs ID3v2.4 null-séparées.
    # album_artist (TPE2) reste single : c'est la clé de groupement Jellyfin.
    _MULTI_VALUE_FIELDS = {'artist', 'genre', 'composer'}

    audio = _MP3(target, ID3=_ID3)
    if audio.tags is None:
        audio.add_tags()

    for field, FrameClass in _FRAME_MAP.items():
        if field not in tags_data:
            continue
        v = str(tags_data[field]).strip()
        key = FrameClass.__name__
        if v:
            if field in _MULTI_VALUE_FIELDS:
                values = [s.strip() for s in v.split(';') if s.strip()] or [v]
            else:
                values = [v]
            audio.tags[key] = FrameClass(encoding=3, text=values)
        else:
            audio.tags.delall(key)

    # Handle comment separately (needs lang)
    if 'comment' in tags_data:
        audio.tags.delall('COMM')
        v = str(tags_data['comment']).strip()
        if v:
            audio.tags.add(COMM(encoding=3, lang='eng', desc='', text=[v]))

    audio.save()


def _read_full_meta(file_path: Path, music_dir: Path) -> dict:
    """Returns every readable piece of metadata from an MP3 file."""
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3

    result = {
        'path':      str(file_path.relative_to(music_dir)),
        'file_name': file_path.name,
        'file_size': file_path.stat().st_size,
        'file_size_mb': round(file_path.stat().st_size / (1024 * 1024), 2),
    }

    try:
        audio = MP3(file_path, ID3=ID3)
        info  = audio.info

        _COVER_NAMES = ('cover.jpg', 'cover.jpeg', 'folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp')
        _ARTIST_PIC_NAMES = (
            'folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp',
            'artist.jpg', 'artist.jpeg', 'artist.png', 'artist.webp',
        )

        tags = audio.tags or {}

        # encoder_settings from TSSE lives in audio, not ID3
        tsse = tags.get('TSSE')
        encoder_settings = None
        if tsse:
            try:
                encoder_settings = str(tsse.text[0]) if hasattr(tsse, 'text') else str(tsse)
            except Exception:
                pass

        result['audio'] = {
            'duration_s':      round(info.length, 1),
            'duration_fmt':    f"{int(info.length)//60}:{int(info.length)%60:02d}",
            'bitrate_kbps':    getattr(info, 'bitrate', 0) // 1000,
            'sample_rate':     getattr(info, 'sample_rate', 0),
            'channels':        getattr(info, 'channels', 0),
            'mode':            str(getattr(info, 'mode', '')),
            'encoder_settings': encoder_settings,
        }

        # Map ID3 text frames (TSSE excluded — handled above)
        _FRAME_LABELS = {
            'TIT2': 'title',          'TPE1': 'artist',
            'TPE2': 'album_artist',   'TPE3': 'conductor',
            'TALB': 'album',          'TDRC': 'year',
            'TRCK': 'track_number',   'TPOS': 'disc_number',
            'TCON': 'genre',          'TCOM': 'composer',
            'TCOP': 'copyright',      'TPUB': 'publisher',
            'TBPM': 'bpm',            'TKEY': 'key',
            'TLAN': 'language',       'TENC': 'encoded_by',
            'TSRC': 'isrc',           'TLEN': 'length_ms',
            'COMM': 'comment',        'USLT': 'lyrics_text',
        }
        id3 = {}
        for frame_id, label in _FRAME_LABELS.items():
            frame = tags.get(frame_id)
            if frame is not None:
                try:
                    if hasattr(frame, 'text'):
                        # Multi-valeurs (TPE1 null-séparé, etc.) → « A; B »
                        id3[label] = '; '.join(str(t) for t in frame.text)
                    else:
                        id3[label] = str(frame)
                except Exception:
                    pass

        # TYER fallback for ID3v2.3 files that use TYER instead of TDRC
        if not id3.get('year'):
            tyer = tags.get('TYER')
            if tyer is not None:
                try:
                    id3['year'] = str(tyer.text[0]).strip()[:4]
                except Exception:
                    pass

        # APIC (embedded cover)
        id3['has_embedded_cover'] = any(k.startswith('APIC') for k in tags.keys())

        # TXXX (custom tags — MusicBrainz IDs, ReplayGain, etc.)
        custom = {}
        for k, v in tags.items():
            if k.startswith('TXXX'):
                try:
                    custom[str(v.desc)] = str(v.text[0])
                except Exception:
                    pass
        if custom:
            id3['custom_tags'] = custom

        result['id3'] = id3

        # External cover in album folder
        covers = [n for n in _COVER_NAMES if (file_path.parent / n).exists()]
        result['cover_files']    = covers
        result['has_album_cover'] = len(covers) > 0

        # Artist picture in artist root folder (only for Artist/Album/song.mp3 structure)
        rel_parts = file_path.relative_to(music_dir).parts
        artist_pics = []
        if len(rel_parts) >= 3:
            artist_folder = music_dir / rel_parts[0]
            artist_pics   = [n for n in _ARTIST_PIC_NAMES if (artist_folder / n).exists()]
        result['artist_picture_files'] = artist_pics

    except Exception as e:
        result['error'] = str(e)

    return result


# Complétude d'un album, mise en cache tant que ses MP3 ne changent pas
# (signature = noms + mtime + taille) : l'écriture d'un tag invalide l'entrée.
_album_status_cache: dict[str, tuple] = {}


_album_status_lock = threading.Lock()


def _album_status(album_dir: Path, music_dir: Path) -> dict | None:
    """{path, name, tracks, missing{genre,year,track_number}, genres, complete} — None sans MP3."""
    try:
        mp3s = sorted(f for f in album_dir.iterdir() if f.is_file() and f.suffix.lower() == '.mp3')
    except OSError:
        return None
    if not mp3s:
        return None
    sig = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in mp3s)
    key = str(album_dir)
    with _album_status_lock:
        hit = _album_status_cache.get(key)
    if hit and hit[0] == sig:
        result = hit[1]
    else:
        from library_audit import _read_tags
        missing = {'genre': 0, 'year': 0, 'track_number': 0}
        genres  = set()
        for f in mp3s:
            tags = _read_tags(f)
            if not tags['genres']:
                missing['genre'] += 1
            genres.update(tags['genres'])
            if not tags['year']:
                missing['year'] += 1
            if not tags['track_number']:
                missing['track_number'] += 1
        result = {'tracks': len(mp3s), 'missing': missing, 'genres': sorted(genres),
                  'complete': not any(missing.values())}
        with _album_status_lock:
            _album_status_cache[key] = (sig, result)
    return {'path': str(album_dir.relative_to(music_dir)), 'name': album_dir.name, **result}
