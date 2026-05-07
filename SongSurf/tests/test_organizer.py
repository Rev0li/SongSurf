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

    def test_playlist_mode_flat_structure(self, organizer, tmp_path):
        src = tmp_path / 'source.mp3'
        self._make_mp3(src)

        with patch.object(organizer, '_update_tags'), \
             patch.object(organizer, '_ensure_album_cover'), \
             patch.object(organizer, '_find_thumbnail', return_value=None):
            result = organizer.organize(str(src), {
                'artist': 'Artist',
                'album':  'MyPlaylist',
                'title':  'Song',
                'year':   '',
            }, playlist_mode=True)

        assert result['success']
        final = organizer.music_dir / 'MyPlaylist' / 'Song.mp3'
        assert final.exists()

    def test_duplicate_gets_counter_suffix(self, organizer, tmp_path):
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
        assert r1['final_path'] != r2['final_path']
        assert '(1)' in r2['final_path']

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
