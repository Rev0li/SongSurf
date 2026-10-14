"""
Tests for MusicOrganizer — featuring detection, filename cleaning, organize logic.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import shutil
import pytest
from unittest.mock import patch


@pytest.fixture
def organizer(tmp_music_dir):
    with patch('shutil.which', return_value=None):
        from organizer import MusicOrganizer
        return MusicOrganizer(tmp_music_dir)


# ── detect_featuring ──────────────────────────────────────────────────────────

class TestDetectFeaturing:
    def test_no_feat(self, organizer):
        r = organizer.detect_featuring('Bohemian Rhapsody', 'Queen')
        assert not r['has_feat']
        assert r['feat_artists'] == []
        assert r['clean_title'] == 'Bohemian Rhapsody'
        assert r['main_artist'] == 'Queen'

    def test_feat_parentheses(self, organizer):
        r = organizer.detect_featuring('Song (feat. Drake)', 'Artist')
        assert r['has_feat']
        assert 'Drake' in r['feat_artists']
        assert 'feat.' not in r['clean_title']

    def test_ft_parentheses(self, organizer):
        r = organizer.detect_featuring('Track (ft. Eminem)', 'Rapper')
        assert r['has_feat']
        assert 'Eminem' in r['feat_artists']

    def test_featuring_full_word(self, organizer):
        r = organizer.detect_featuring('Song (featuring Jay-Z)', 'Artist')
        assert r['has_feat']
        assert 'Jay-Z' in r['feat_artists']

    def test_square_bracket_feat(self, organizer):
        r = organizer.detect_featuring('Title [feat. Billie]', 'Someone')
        assert r['has_feat']
        assert 'Billie' in r['feat_artists']

    def test_multiple_feat_artists(self, organizer):
        r = organizer.detect_featuring('Song (feat. A & B)', 'Main')
        assert r['has_feat']
        assert len(r['feat_artists']) == 2

    def test_main_artist_unchanged(self, organizer):
        r = organizer.detect_featuring('Song (feat. Guest)', 'Main Artist')
        assert r['main_artist'] == 'Main Artist'


# ── _clean_filename ───────────────────────────────────────────────────────────

class TestOrganizerCleanFilename:
    def test_forbidden_chars_removed(self, organizer):
        assert organizer._clean_filename('A<B>C:D"E/F\\G|H?I*J') == 'ABCDEFGHIJ'

    def test_unicode_preserved(self, organizer):
        assert organizer._clean_filename('Beyoncé') == 'Beyoncé'

    def test_empty_input(self, organizer):
        assert organizer._clean_filename('') == ''


# ── organize — file placement ─────────────────────────────────────────────────

class TestOrganizeFilePlacement:
    def _make_mp3(self, path):
        """Create a minimal dummy mp3 file (not a real MP3, just bytes)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\xff\xfb\x90\x00' + b'\x00' * 128)

    def test_normal_mode_creates_artist_album_structure(self, organizer, tmp_path):
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)

        with patch.object(organizer, '_update_tags'), \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            result = organizer.organize(str(src), {
                'artist': 'TestArtist',
                'album':  'TestAlbum',
                'title':  'TestSong',
                'year':   '2024',
            })

        assert result['success']
        final = organizer.music_dir / 'TestArtist' / 'TestAlbum' / 'TestSong.mp3'
        assert final.exists()

    def test_track_number_passed_to_tags(self, organizer, tmp_path):
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)

        with patch.object(organizer, '_update_tags') as mock_tags, \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            result = organizer.organize(str(src), {
                'artist':       'Artist',
                'album':        'Album',
                'title':        'Song',
                'year':         '2024',
                'track_number': 3,
                'track_total':  12,
            })

        assert result['success']
        tags = mock_tags.call_args[0][1]
        assert tags['track_number'] == 3
        assert tags['track_total'] == 12

    def test_album_artist_passed_to_tags(self, organizer, tmp_path):
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)

        with patch.object(organizer, '_update_tags') as mock_tags, \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            result = organizer.organize(str(src), {
                'artist':       'Artist',
                'album_artist': 'AlbumArtist',
                'album':        'Album',
                'title':        'Song',
                'year':         '',
            })

        assert result['success']
        tags = mock_tags.call_args[0][1]
        assert tags['album_artist'] == 'AlbumArtist'

    def test_multi_artists_passed_to_tags(self, organizer, tmp_path):
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)

        with patch.object(organizer, '_update_tags') as mock_tags, \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            result = organizer.organize(str(src), {
                'artist':  'ArtisteA',
                'artists': ['ArtisteA', 'ArtisteB'],
                'album':   'Album',
                'title':   'Song',
                'year':    '',
            })

        assert result['success']
        tags = mock_tags.call_args[0][1]
        assert tags['artists'] == ['ArtisteA', 'ArtisteB']
        # Le dossier reste celui de l'artiste principal
        assert (organizer.music_dir / 'ArtisteA' / 'Album' / 'Song.mp3').exists()

    def test_feat_artists_merged_into_tpe1_list(self, organizer, tmp_path):
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)

        with patch.object(organizer, '_update_tags') as mock_tags, \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            result = organizer.organize(str(src), {
                'artist': 'Main',
                'album':  'Album',
                'title':  'Song (feat. Guest)',
                'year':   '',
            })

        assert result['success']
        tags = mock_tags.call_args[0][1]
        assert tags['artists'] == ['Main', 'Guest']

    def test_track_number_absent_defaults_empty(self, organizer, tmp_path):
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)

        with patch.object(organizer, '_update_tags') as mock_tags, \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            result = organizer.organize(str(src), {
                'artist': 'Artist', 'album': 'Album', 'title': 'Song', 'year': '',
            })

        assert result['success']
        tags = mock_tags.call_args[0][1]
        assert tags['track_number'] == ''

    def test_duplicate_is_skipped(self, organizer, tmp_path):
        def make_and_organize(i):
            src = tmp_path / f'source_{i}.mp3'
            self._make_mp3(src)
            with patch.object(organizer, '_update_tags'), \
                 patch.object(organizer, '_ensure_album_cover'), \
                 patch.object(organizer, '_find_thumbnail', return_value=None):
                return organizer.organize(str(src), {
                    'artist': 'Dup', 'album': 'Album', 'title': 'Song', 'year': '',
                })

        r1 = make_and_organize(1)
        r2 = make_and_organize(2)
        assert r1['success'] and r2['success']
        # Le doublon est ignoré : même chemin, flag skipped, pas de suffixe « (1) ».
        assert r1['final_path'] == r2['final_path']
        assert r2.get('skipped') is True
        assert not r1.get('skipped')
        album_dir = organizer.music_dir / 'Dup' / 'Album'
        assert sorted(p.name for p in album_dir.glob('*.mp3')) == ['Song.mp3']

    def test_target_exists_detects_existing_title(self, organizer, tmp_path):
        meta = {'artist': 'TE', 'album': 'Alb', 'title': 'Trk', 'year': ''}
        assert organizer.target_exists(meta) is False
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)
        with patch.object(organizer, '_update_tags'), \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            organizer.organize(str(src), meta)
        # Une fois organisé, le doublon est détecté en amont (court-circuit worker).
        assert organizer.target_exists(meta) is True

    def test_target_exists_accounts_for_featuring(self, organizer, tmp_path):
        # compute_target doit refléter le suffixe « (feat. …) » comme organize().
        meta = {'artist': 'Main', 'album': 'Alb', 'title': 'Song (feat. Guest)', 'year': ''}
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)
        with patch.object(organizer, '_update_tags'), \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            organizer.organize(str(src), meta)
        assert organizer.target_exists(meta) is True

    def test_missing_file_returns_failure(self, organizer):
        result = organizer.organize('/nonexistent/path/song.mp3', {
            'artist': 'A', 'album': 'B', 'title': 'C', 'year': '',
        })
        assert not result['success']
        assert 'error' in result

    def test_temp_file_cleaned_up_after_organize(self, organizer, tmp_path):
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)

        with patch.object(organizer, '_update_tags'), \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            organizer.organize(str(src), {
                'artist': 'A', 'album': 'B', 'title': 'C', 'year': '',
            })

        assert not src.exists()


# ── Recalage casse/accents (évite les doublons d'artiste/album côté Jellyfin) ──

class TestCanonicalNaming:
    def _make_mp3(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\xff\xfb\x90\x00' + b'\x00' * 128)

    def _organize(self, organizer, tmp_path, name, metadata):
        src = tmp_path / f'{name}.mp3'
        self._make_mp3(src)
        with patch.object(organizer, '_update_tags') as mock_tags, \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            result = organizer.organize(str(src), metadata)
        return result, mock_tags

    def test_artist_casing_reuses_existing_folder(self, organizer, tmp_path):
        # Premier téléchargement : crée le dossier "Drake".
        self._organize(organizer, tmp_path, 's1', {
            'artist': 'Drake', 'album': 'Alb', 'title': 'First', 'year': '',
        })
        # Deuxième téléchargement, même artiste mais casse différente venant
        # de yt-dlp : doit atterrir dans le dossier "Drake" existant, pas "drake".
        result, mock_tags = self._organize(organizer, tmp_path, 's2', {
            'artist': 'drake', 'album': 'Alb', 'title': 'Second', 'year': '',
        })
        assert result['success']
        assert (organizer.music_dir / 'Drake' / 'Alb' / 'Second.mp3').exists()
        assert not (organizer.music_dir / 'drake').exists()
        assert mock_tags.call_args[0][1]['artist'] == 'Drake'

    def test_artist_accents_reuse_existing_folder(self, organizer, tmp_path):
        self._organize(organizer, tmp_path, 's1', {
            'artist': 'Stromae', 'album': 'Alb', 'title': 'First', 'year': '',
        })
        result, _ = self._organize(organizer, tmp_path, 's2', {
            'artist': 'Strômae', 'album': 'Alb', 'title': 'Second', 'year': '',
        })
        assert result['success']
        assert (organizer.music_dir / 'Stromae' / 'Alb' / 'Second.mp3').exists()

    def test_album_casing_reuses_existing_folder_within_artist(self, organizer, tmp_path):
        self._organize(organizer, tmp_path, 's1', {
            'artist': 'Artist', 'album': 'Greatest Hits', 'title': 'First', 'year': '',
        })
        result, _ = self._organize(organizer, tmp_path, 's2', {
            'artist': 'Artist', 'album': 'greatest hits', 'title': 'Second', 'year': '',
        })
        assert result['success']
        assert (organizer.music_dir / 'Artist' / 'Greatest Hits' / 'Second.mp3').exists()

    def test_no_existing_match_keeps_candidate_as_is(self, organizer, tmp_path):
        result, mock_tags = self._organize(organizer, tmp_path, 's1', {
            'artist': 'NewArtist', 'album': 'NewAlbum', 'title': 'Song', 'year': '',
        })
        assert result['success']
        assert (organizer.music_dir / 'NewArtist' / 'NewAlbum' / 'Song.mp3').exists()
        assert mock_tags.call_args[0][1]['artist'] == 'NewArtist'

    def test_featuring_artist_canonicalized_against_existing_folder(self, organizer, tmp_path):
        # "Travis Scott" a déjà son propre dossier (téléchargement précédent en
        # tant qu'artiste principal).
        self._organize(organizer, tmp_path, 's1', {
            'artist': 'Travis Scott', 'album': 'Solo', 'title': 'Song', 'year': '',
        })
        # Featuring avec une casse différente dans le titre du deuxième morceau.
        result, mock_tags = self._organize(organizer, tmp_path, 's2', {
            'artist': 'Drake', 'album': 'Alb', 'title': 'Collab (feat. travis scott)', 'year': '',
        })
        assert result['success']
        assert mock_tags.call_args[0][1]['artists'] == ['Drake', 'Travis Scott']
