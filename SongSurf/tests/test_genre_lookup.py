"""
Tests for genre_lookup — iTunes Search API wrapper (mocked, no network).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import io
import json
import pytest
from unittest.mock import patch

import genre_lookup
from genre_lookup import lookup_genres, lookup_album_info


@pytest.fixture(autouse=True)
def clear_cache():
    genre_lookup._cache.clear()
    genre_lookup._album_cache.clear()
    yield
    genre_lookup._cache.clear()
    genre_lookup._album_cache.clear()


def _fake_response(results):
    """Simule la réponse urlopen (context manager) de l'API iTunes."""
    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return FakeResp(json.dumps({'results': results}).encode('utf-8'))


def _itunes_result(artist, genre):
    return {'artistName': artist, 'primaryGenreName': genre}


# ── lookup_genres ─────────────────────────────────────────────────────────────

class TestLookupGenres:
    def test_fr_and_en_genres(self):
        responses = {
            'FR': [_itunes_result('Daft Punk', 'Électronique')],
            'US': [_itunes_result('Daft Punk', 'Electronic')],
        }

        def fake_urlopen(req, timeout=None):
            country = 'FR' if 'country=FR' in req.full_url else 'US'
            return _fake_response(responses[country])

        with patch('genre_lookup.urlopen', side_effect=fake_urlopen):
            genres = lookup_genres('Daft Punk', 'Get Lucky', 'Random Access Memories')
        assert genres == ['Électronique', 'Electronic']

    def test_identical_genres_deduplicated(self):
        with patch('genre_lookup.urlopen',
                   side_effect=lambda req, timeout=None: _fake_response(
                       [_itunes_result('Queen', 'Rock')])):
            genres = lookup_genres('Queen', 'Bohemian Rhapsody', 'A Night at the Opera')
        assert genres == ['Rock']

    def test_artist_mismatch_skipped(self):
        # Karaoké/reprise en premier résultat → ignoré, vrai artiste pris ensuite
        results = [
            _itunes_result('Karaoke Hits Band', 'Karaoké'),
            _itunes_result('Stromae', 'Pop francophone'),
        ]
        with patch('genre_lookup.urlopen',
                   side_effect=lambda req, timeout=None: _fake_response(results)):
            genres = lookup_genres('Stromae', 'Alors on danse', 'Cheese')
        assert genres == ['Pop francophone']

    def test_no_match_returns_empty(self):
        with patch('genre_lookup.urlopen',
                   side_effect=lambda req, timeout=None: _fake_response([])):
            assert lookup_genres('Inconnu', 'Titre obscur', 'Album') == []

    def test_network_error_returns_empty(self):
        with patch('genre_lookup.urlopen', side_effect=OSError('timeout')):
            assert lookup_genres('Artist', 'Title', 'Album') == []

    def test_network_error_not_cached(self):
        with patch('genre_lookup.urlopen', side_effect=OSError('timeout')):
            lookup_genres('Artist', 'Title', 'Album')
        assert genre_lookup._cache == {}

    def test_empty_inputs(self):
        assert lookup_genres('', 'Title') == []
        assert lookup_genres('Artist', '') == []

    def test_cache_one_lookup_per_album(self):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            return _fake_response([_itunes_result('IAM', 'Rap français')])

        with patch('genre_lookup.urlopen', side_effect=fake_urlopen):
            first = lookup_genres('IAM', 'Nés sous la même étoile', "L'École du micro d'argent")
            second = lookup_genres('IAM', 'Petit frère', "L'École du micro d'argent")
        assert first == second == ['Rap français']
        # 2 appels (FR + US) pour la 1re piste, 0 pour la 2e (cache album)
        assert len(calls) == 2

    def test_unknown_album_cached_per_title(self):
        def fake_urlopen(req, timeout=None):
            return _fake_response([_itunes_result('Artist', 'Pop')])

        with patch('genre_lookup.urlopen', side_effect=fake_urlopen) as mock:
            lookup_genres('Artist', 'Song One', 'Unknown Album')
            lookup_genres('Artist', 'Song Two', 'Unknown Album')
        # Albums inconnus → clé par titre, pas de collision de cache
        assert len(genre_lookup._cache) == 2


# ── lookup_album_info ─────────────────────────────────────────────────────────

def _itunes_album(artist, album, genre='Rock', year='2016', tracks=12):
    return {
        'artistName':       artist,
        'collectionName':   album,
        'primaryGenreName': genre,
        'releaseDate':      f'{year}-06-03T07:00:00Z',
        'trackCount':       tracks,
    }


class TestLookupAlbumInfo:
    def test_album_found(self):
        responses = {
            'FR': [_itunes_album('Nekfeu', 'Cyborg', 'Rap français', '2016', 14)],
            'US': [_itunes_album('Nekfeu', 'Cyborg', 'Hip-Hop/Rap', '2016', 14)],
        }

        def fake_urlopen(req, timeout=None):
            country = 'FR' if 'country=FR' in req.full_url else 'US'
            return _fake_response(responses[country])

        with patch('genre_lookup.urlopen', side_effect=fake_urlopen):
            info = lookup_album_info('Nekfeu', 'Cyborg')
        assert info['found'] is True
        assert info['genres'] == ['Rap français', 'Hip-Hop/Rap']
        assert info['year'] == '2016'
        assert info['album_artist'] == 'Nekfeu'
        assert info['track_count'] == 14

    def test_deluxe_edition_matches(self):
        # iTunes suffixe « (Deluxe) » → containment souple
        result = _itunes_album('Daft Punk', 'Random Access Memories (Deluxe Edition)')
        with patch('genre_lookup.urlopen',
                   side_effect=lambda req, timeout=None: _fake_response([result])):
            info = lookup_album_info('Daft Punk', 'Random Access Memories')
        assert info['found'] is True

    def test_wrong_artist_skipped(self):
        result = _itunes_album('Tribute Band', 'Cyborg', 'Karaoké')
        with patch('genre_lookup.urlopen',
                   side_effect=lambda req, timeout=None: _fake_response([result])):
            info = lookup_album_info('Nekfeu', 'Cyborg')
        assert info['found'] is False
        assert info['genres'] == []

    def test_network_error_returns_not_found_and_not_cached(self):
        with patch('genre_lookup.urlopen', side_effect=OSError('timeout')):
            info = lookup_album_info('Artist', 'Album')
        assert info['found'] is False
        assert genre_lookup._album_cache == {}

    def test_result_cached(self):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            return _fake_response([_itunes_album('IAM', "L'École du micro d'argent")])

        with patch('genre_lookup.urlopen', side_effect=fake_urlopen):
            first = lookup_album_info('IAM', "L'École du micro d'argent")
            second = lookup_album_info('IAM', "L'École du micro d'argent")
        assert first == second
        assert len(calls) == 2  # FR + US une seule fois

    def test_cached_copy_is_isolated(self):
        with patch('genre_lookup.urlopen',
                   side_effect=lambda req, timeout=None: _fake_response(
                       [_itunes_album('Queen', 'A Night at the Opera')])):
            first = lookup_album_info('Queen', 'A Night at the Opera')
            first['genres'].append('PARASITE')
            second = lookup_album_info('Queen', 'A Night at the Opera')
        assert 'PARASITE' not in second['genres']

    def test_empty_inputs(self):
        assert lookup_album_info('', 'Album')['found'] is False
        assert lookup_album_info('Artist', '')['found'] is False


# ── helpers ───────────────────────────────────────────────────────────────────

class TestArtistMatches:
    def test_exact(self):
        assert genre_lookup._artist_matches('Daft Punk', 'Daft Punk')

    def test_accents_and_case(self):
        assert genre_lookup._artist_matches('Beyoncé', 'beyonce')

    def test_substring(self):
        assert genre_lookup._artist_matches('Stromae', 'Stromae & Orelsan')

    def test_mismatch(self):
        assert not genre_lookup._artist_matches('Queen', 'Karaoke Band')

    def test_empty(self):
        assert not genre_lookup._artist_matches('', 'Queen')
