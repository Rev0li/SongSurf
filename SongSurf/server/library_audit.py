"""
Audit métadonnées par artiste + backfill genre de la bibliothèque (admin).

Audit : compare les tags ID3 de tous les albums d'un artiste avec iTunes
(genre, année, artiste album, numéros de piste, cohérence TPE1/TPE2) et
produit des *recommandations* — rien n'est écrit sans validation explicite
de l'admin via /api/admin/audit/apply.

Backfill : complète le TCON des MP3 déjà téléchargés qui n'en ont pas
(la bibliothèque d'avant la Phase 1 genre n'a aucun TCON).

Lecture/écriture via mutagen.id3.ID3 directement (pas besoin de frames
MPEG valides → testable avec des fichiers factices).
"""
import logging
import re
from collections import Counter
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError, TCON

from genre_lookup import lookup_album_info, lookup_album_tracks, lookup_genres
from genre_lookup import _normalize

logger = logging.getLogger(__name__)

_COVER_NAMES = ('cover.jpg', 'cover.jpeg', 'folder.jpg', 'folder.jpeg',
                'folder.png', 'folder.webp')
_ARTIST_PIC_NAMES = ('folder.jpg', 'folder.jpeg', 'folder.png', 'folder.webp',
                     'artist.jpg', 'artist.jpeg', 'artist.png', 'artist.webp')


def _read_tags(path: Path) -> dict:
    """Tags utiles à l'audit. Fichier sans header ID3 → tout vide."""
    try:
        id3 = ID3(path)
    except ID3NoHeaderError:
        id3 = {}
    except Exception as e:
        logger.warning(f"⚠️ audit: lecture ID3 impossible ({path.name}): {e}")
        id3 = {}

    def _texts(frame_id):
        frame = id3.get(frame_id) if id3 else None
        if frame is None or not getattr(frame, 'text', None):
            return []
        return [str(t).strip() for t in frame.text if str(t).strip()]

    def _first(frame_id):
        vals = _texts(frame_id)
        return vals[0] if vals else ''

    return {
        'title':        _first('TIT2'),
        'artists':      _texts('TPE1'),
        'album_artist': _first('TPE2'),
        'album':        _first('TALB'),
        'year':         (_first('TDRC')[:4] or _first('TYER')[:4]),
        'track_number': _first('TRCK'),
        'genres':       _texts('TCON'),
    }


# « (feat. X) », « [avec Y] »… diffèrent souvent entre YouTube et iTunes
_FEAT_PAREN = re.compile(r'\s*[(\[][^)\]]*\b(feat|ft|featuring|avec|with)\b[^)\]]*[)\]]',
                         re.IGNORECASE)


def _normalize_title(title):
    return _normalize(_FEAT_PAREN.sub('', str(title or '')))


def _match_missing_tracks(missing_tracks, itunes_tracks):
    """Associe les titres sans TRCK à la tracklist iTunes.

    Match par titre normalisé (TIT2, sinon nom de fichier), uniquement
    sans ambiguïté : un fichier ↔ une piste iTunes. Retourne {path: piste}.
    """
    by_title = {}
    for it in itunes_tracks:
        key = _normalize_title(it.get('title', ''))
        if key:
            by_title.setdefault(key, []).append(it)

    matches = {}
    claimed = Counter()
    for t in missing_tracks:
        local = _normalize_title(t['title'] or Path(t['name']).stem)
        candidates = by_title.get(local, [])
        if len(candidates) == 1:
            matches[t['path']] = candidates[0]
            claimed[id(candidates[0])] += 1

    # Deux fichiers revendiquent la même piste iTunes → aucun des deux
    return {p: it for p, it in matches.items() if claimed[id(it)] == 1}


def _audit_album(artist_name: str, album_dir: Path, music_dir: Path, itunes: dict,
                 track_lookup=None):
    """Audit d'un album : (tracks, recommendations, warnings).

    Recommandation = {'id', 'field', 'proposed', 'current', 'reason',
                      'changes': [{'path', 'value'}]} — appliquée telle quelle
    par l'endpoint apply si l'admin la coche.
    """
    mp3s = sorted(
        [f for f in album_dir.iterdir() if f.is_file() and f.suffix.lower() == '.mp3'],
        key=lambda p: p.name.lower()
    )
    tracks = []
    for f in mp3s:
        t = _read_tags(f)
        t['path'] = str(f.relative_to(music_dir))
        t['name'] = f.name
        tracks.append(t)

    recs, warns = [], []
    album_rel = str(album_dir.relative_to(music_dir))
    n = len(tracks)
    if n == 0:
        return tracks, recs, warns

    def _rec(field, proposed, current, reason, changes):
        recs.append({
            'id':       f'{field}:{album_rel}:{len(recs)}',
            'field':    field,
            'proposed': proposed,
            'current':  current,
            'reason':   reason,
            'changes':  changes,
        })

    # 1. Genre (TCON) manquant
    missing_genre = [t for t in tracks if not t['genres']]
    if missing_genre:
        if itunes.get('genres'):
            value = '; '.join(itunes['genres'])
            _rec('genre', value,
                 f"manquant sur {len(missing_genre)}/{n} titres",
                 "Genre iTunes de l'album",
                 [{'path': t['path'], 'value': value} for t in missing_genre])
        else:
            warns.append(f"Genre manquant sur {len(missing_genre)}/{n} titres — album introuvable sur iTunes")

    # Genres différents d'un titre à l'autre → signalé, pas de proposition
    genre_sets = {tuple(t['genres']) for t in tracks if t['genres']}
    if len(genre_sets) > 1:
        warns.append('Genres différents selon les titres : '
                     + ' / '.join(sorted('; '.join(g) for g in genre_sets)))

    # 2. Année (TDRC)
    years = [t['year'] for t in tracks if t['year']]
    missing_year = [t for t in tracks if not t['year']]
    distinct_years = sorted(set(years))
    itunes_year = itunes.get('year', '')
    if missing_year and (itunes_year or years):
        value = itunes_year or Counter(years).most_common(1)[0][0]
        source = 'année iTunes' if itunes_year else "année majoritaire de l'album"
        _rec('year', value,
             f"manquante sur {len(missing_year)}/{n} titres",
             f"Année manquante — {source}",
             [{'path': t['path'], 'value': value} for t in missing_year])
    if len(distinct_years) > 1:
        if itunes_year:
            wrong = [t for t in tracks if t['year'] and t['year'] != itunes_year]
            if wrong:
                _rec('year', itunes_year,
                     ' / '.join(distinct_years),
                     "Années incohérentes — alignement sur l'année iTunes",
                     [{'path': t['path'], 'value': itunes_year} for t in wrong])
        else:
            warns.append('Années incohérentes : ' + ' / '.join(distinct_years))

    # 3. Artiste album (TPE2) — le dossier artiste est la vérité de
    #    groupement Jellyfin, pas iTunes.
    bad_aa = [t for t in tracks if t['album_artist'] != artist_name]
    if bad_aa:
        currents = sorted({t['album_artist'] or '∅' for t in bad_aa})
        _rec('album_artist', artist_name,
             ' / '.join(currents),
             'TPE2 doit correspondre au dossier artiste (clé de groupement Jellyfin)',
             [{'path': t['path'], 'value': artist_name} for t in bad_aa])

    # 4. TPE1 manquant
    no_artist = [t for t in tracks if not t['artists']]
    if no_artist:
        _rec('artist', artist_name,
             f"manquant sur {len(no_artist)}/{n} titres",
             'TPE1 manquant — artiste du dossier',
             [{'path': t['path'], 'value': artist_name} for t in no_artist])

    # 5. Cohérence TPE1/TPE2 (featuring mal taggé, etc.) → signalé seulement
    for t in tracks:
        if t['artists'] and t['album_artist'] and t['album_artist'] not in t['artists']:
            warns.append(f"{t['name']} : l'artiste album « {t['album_artist']} » "
                         f"n'apparaît pas dans TPE1 ({'; '.join(t['artists'])})")

    # 6. Numéros de piste (TRCK) — TRCK absent : tentative de match contre
    #    la tracklist officielle iTunes, le reste part en warning.
    no_trck = [t for t in tracks if not t['track_number']]
    matched = {}
    if no_trck and itunes.get('collection_id') and track_lookup:
        itunes_tracks = track_lookup(itunes['collection_id']) or []
        matched = _match_missing_tracks(no_trck, itunes_tracks)
        if matched:
            fallback_total = itunes.get('track_count') or len(itunes_tracks) or n
            changes = sorted(
                ({'path': p, 'value': f"{it['track_number']}/{it.get('track_count') or fallback_total}"}
                 for p, it in matched.items()),
                key=lambda c: int(c['value'].split('/')[0])
            )
            _rec('track_number', ', '.join(c['value'] for c in changes),
                 f"manquant sur {len(no_trck)}/{n} titres",
                 'Position trouvée dans la tracklist iTunes',
                 changes)
    still_missing = [t for t in no_trck if t['path'] not in matched]
    if still_missing:
        warns.append(f"Numéro de piste manquant sur {len(still_missing)}/{n} titres "
                     "(pas de correspondance iTunes — utiliser « Numéroter les pistes » "
                     "dans le panneau album)")
    total = itunes.get('track_count') or n
    bare = [t for t in tracks
            if t['track_number'] and '/' not in t['track_number'] and t['track_number'].isdigit()]
    if bare:
        _rec('track_number', f'n/{total}',
             ', '.join(t['track_number'] for t in bare),
             'TRCK normalisé en « n/total » (tri album Jellyfin)',
             [{'path': t['path'], 'value': f"{int(t['track_number'])}/{total}"} for t in bare])
    nums = [t['track_number'].split('/')[0] for t in tracks if t['track_number']]
    dups = sorted(k for k, c in Counter(nums).items() if c > 1)
    if dups:
        warns.append('Numéros de piste en double : ' + ', '.join(dups))

    # 7. Complétude vs iTunes
    if itunes.get('found') and itunes.get('track_count') and itunes['track_count'] != n:
        warns.append(f"iTunes annonce {itunes['track_count']} titres, l'album en contient {n}")

    # 8. Pochette album
    if not any((album_dir / c).exists() for c in _COVER_NAMES):
        warns.append('Pochette album manquante (cover.jpg)')

    return tracks, recs, warns


def audit_artist(artist_dir: Path, music_dir: Path, album_lookup=None,
                 track_lookup=None) -> dict:
    """Rapport complet pour un artiste : un lookup iTunes par album
    (+ un lookup tracklist par album ayant des TRCK manquants)."""
    album_lookup = album_lookup or lookup_album_info
    track_lookup = track_lookup or lookup_album_tracks
    artist_name = artist_dir.name
    albums = []
    total = 0
    for album_dir in sorted([d for d in artist_dir.iterdir() if d.is_dir()],
                            key=lambda p: p.name.lower()):
        itunes = album_lookup(artist_name, album_dir.name) or {}
        tracks, recs, warns = _audit_album(artist_name, album_dir, music_dir, itunes,
                                           track_lookup=track_lookup)
        if not tracks:
            continue
        total += len(recs)
        albums.append({
            'name':            album_dir.name,
            'path':            str(album_dir.relative_to(music_dir)),
            'track_count':     len(tracks),
            'itunes':          itunes,
            'recommendations': recs,
            'warnings':        warns,
        })

    artist_warnings = []
    if not any((artist_dir / p).exists() for p in _ARTIST_PIC_NAMES):
        artist_warnings.append("Photo artiste manquante (folder.jpg) — Jellyfin n'affichera pas d'image")

    return {
        'artist':                artist_name,
        'path':                  str(artist_dir.relative_to(music_dir)),
        'albums':                albums,
        'artist_warnings':       artist_warnings,
        'total_recommendations': total,
    }


def backfill_genres(music_dir: Path, state: dict, lock, genre_lookup_fn=None):
    """Worker backfill : écrit le TCON manquant sur toute la bibliothèque.

    `state` est partagé avec la route status — mis à jour sous `lock`.
    Artiste/titre/album : tags d'abord, dossiers/nom de fichier en repli.
    Le cache album de lookup_genres limite à ~2 appels HTTP par album.
    """
    genre_lookup_fn = genre_lookup_fn or lookup_genres

    targets = []
    for mp3 in sorted(music_dir.rglob('*.mp3')):
        tags = _read_tags(mp3)
        if tags['genres']:
            continue
        rel = mp3.relative_to(music_dir).parts
        artist = tags['artists'][0] if tags['artists'] else (rel[0] if len(rel) >= 3 else '')
        album = tags['album'] or (rel[-2] if len(rel) >= 2 else '')
        title = tags['title'] or mp3.stem
        if artist and title:
            targets.append((mp3, artist, title, album))

    with lock:
        state.update({'total': len(targets), 'done': 0, 'updated': 0,
                      'failed': 0, 'last_file': ''})

    for mp3, artist, title, album in targets:
        genres = []
        try:
            genres = genre_lookup_fn(artist, title, album)
            if genres:
                try:
                    id3 = ID3(mp3)
                except ID3NoHeaderError:
                    id3 = ID3()
                id3['TCON'] = TCON(encoding=3, text=genres)
                id3.save(mp3)
        except Exception as e:
            logger.warning(f"⚠️ backfill genre ({mp3.name}): {e}")
            with lock:
                state['failed'] += 1
            genres = []
        with lock:
            state['done'] += 1
            if genres:
                state['updated'] += 1
            state['last_file'] = str(mp3.relative_to(music_dir))

    with lock:
        state['status'] = 'done'
    logger.info(f"🎼 Backfill genres terminé : {state['updated']}/{state['total']} fichiers mis à jour")
