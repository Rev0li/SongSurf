"""
Genre lookup via l'API iTunes Search (gratuite, sans clé API).

Utilisé par le queue worker pour enrichir les téléchargements admin :
recherche artiste + titre sur les storefronts FR et US, retourne les
genres dédupliqués (nom français d'abord, anglais ensuite).

Échec silencieux par design : erreur réseau, timeout ou absence de
résultat → liste vide. Le download n'est jamais bloqué, et le genre
reste éditable à la main via l'éditeur de métadonnées.
"""
import json
import logging
import threading
import unicodedata
from urllib.parse import urlencode
from urllib.request import urlopen, Request

logger = logging.getLogger(__name__)

ITUNES_SEARCH_URL = 'https://itunes.apple.com/search'
TIMEOUT_SECONDS = 4
# FR d'abord → le genre en français arrive en tête du TCON.
COUNTRIES = ('FR', 'US')

# Cache mémoire (artiste, album) → genres : un album de N pistes ne coûte
# qu'un seul lookup (2 appels HTTP), et on reste loin du rate-limit iTunes.
_cache = {}
_album_cache = {}  # (artiste, album) → info album (audit / backfill)
_cache_lock = threading.Lock()


def _normalize(text):
    """Minuscules sans accents — pour comparer noms d'artistes et clés de cache."""
    text = unicodedata.normalize('NFKD', str(text or ''))
    return ''.join(c for c in text if not unicodedata.combining(c)).lower().strip()


def _artist_matches(expected, candidate):
    """Match souple : évite les faux positifs (reprises, karaoké, tributes)."""
    e, c = _normalize(expected), _normalize(candidate)
    return bool(e) and bool(c) and (e in c or c in e)


def _album_matches(expected, candidate):
    """iTunes suffixe souvent « (Deluxe Edition) » etc. → containment souple."""
    e, c = _normalize(expected), _normalize(candidate)
    return bool(e) and bool(c) and (e in c or c in e)


def _search_genre(artist, title, country):
    """Un appel iTunes Search → primaryGenreName du premier résultat plausible."""
    params = urlencode({
        'term':    f'{artist} {title}',
        'media':   'music',
        'entity':  'song',
        'limit':   5,
        'country': country,
    })
    req = Request(f'{ITUNES_SEARCH_URL}?{params}',
                  headers={'User-Agent': 'SongSurf/1.0'})
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    for result in data.get('results', []):
        if _artist_matches(artist, result.get('artistName', '')):
            genre = (result.get('primaryGenreName') or '').strip()
            if genre:
                return genre
    return ''


def lookup_genres(artist, title, album=''):
    """
    Retourne la liste des genres pour un titre, ex. ['Rap français', 'Hip-Hop/Rap'],
    dédupliquée (un seul élément si FR et US donnent le même nom), ou [] si rien.
    """
    artist = str(artist or '').strip()
    title = str(title or '').strip()
    if not artist or not title:
        return []

    album_key = _normalize(album)
    if album_key in ('', 'unknown album'):
        album_key = _normalize(title)
    cache_key = (_normalize(artist), album_key)

    with _cache_lock:
        if cache_key in _cache:
            return list(_cache[cache_key])

    genres = []
    reachable = False
    for country in COUNTRIES:
        try:
            genre = _search_genre(artist, title, country)
            reachable = True
        except Exception as e:
            logger.warning(f"⚠️ iTunes lookup ({country}) échoué pour {artist} - {title}: {e}")
            continue
        if genre and _normalize(genre) not in [_normalize(g) for g in genres]:
            genres.append(genre)

    # Ne pas mémoriser un échec purement réseau : la prochaine piste retentera.
    if reachable:
        with _cache_lock:
            _cache[cache_key] = list(genres)

    if genres:
        logger.info(f"🎼 Genre iTunes: {artist} - {title} → {genres}")
    return genres


def _search_album(artist, album, country):
    """Un appel iTunes Search (entity=album) → premier résultat plausible ou None."""
    params = urlencode({
        'term':    f'{artist} {album}',
        'media':   'music',
        'entity':  'album',
        'limit':   5,
        'country': country,
    })
    req = Request(f'{ITUNES_SEARCH_URL}?{params}',
                  headers={'User-Agent': 'SongSurf/1.0'})
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    for result in data.get('results', []):
        if (_artist_matches(artist, result.get('artistName', ''))
                and _album_matches(album, result.get('collectionName', ''))):
            return result
    return None


def lookup_album_info(artist, album):
    """
    Recherche l'album sur iTunes (FR puis US) pour l'audit métadonnées :

        {'found': bool, 'genres': [...], 'year': 'YYYY',
         'album_artist': str, 'track_count': int}

    Même contrat que lookup_genres : jamais d'exception, cache mémoire,
    échec réseau non mémorisé.
    """
    artist = str(artist or '').strip()
    album = str(album or '').strip()
    info = {'found': False, 'genres': [], 'year': '', 'album_artist': '', 'track_count': 0}
    if not artist or not album:
        return info

    cache_key = (_normalize(artist), _normalize(album))
    with _cache_lock:
        if cache_key in _album_cache:
            cached = _album_cache[cache_key]
            return {**cached, 'genres': list(cached['genres'])}

    reachable = False
    for country in COUNTRIES:
        try:
            result = _search_album(artist, album, country)
            reachable = True
        except Exception as e:
            logger.warning(f"⚠️ iTunes album lookup ({country}) échoué pour {artist} - {album}: {e}")
            continue
        if not result:
            continue
        info['found'] = True
        genre = (result.get('primaryGenreName') or '').strip()
        if genre and _normalize(genre) not in [_normalize(g) for g in info['genres']]:
            info['genres'].append(genre)
        if not info['year']:
            info['year'] = str(result.get('releaseDate') or '')[:4]
        if not info['album_artist']:
            info['album_artist'] = (result.get('artistName') or '').strip()
        if not info['track_count']:
            try:
                info['track_count'] = int(result.get('trackCount') or 0)
            except (TypeError, ValueError):
                pass

    if reachable:
        with _cache_lock:
            _album_cache[cache_key] = {**info, 'genres': list(info['genres'])}

    if info['found']:
        logger.info(f"🎼 Album iTunes: {artist} - {album} → {info['genres']}, {info['year']}")
    return info
