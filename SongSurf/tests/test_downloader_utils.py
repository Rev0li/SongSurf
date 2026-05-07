"""
Tests for YouTubeDownloader utility methods (pure logic, no network/yt-dlp calls).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import pytest
from unittest.mock import patch


# Import utility methods without triggering yt-dlp network calls
@pytest.fixture(scope='module')
def downloader(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('dl')
    # Patch ffmpeg detection so it doesn't fail in CI
    with patch('shutil.which', return_value=None):
        from downloader import YouTubeDownloader
        return YouTubeDownloader(tmp / 'temp', tmp / 'music')


# ── _normalize_url ────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_music_youtube_converted(self, downloader):
        url = 'https://music.youtube.com/watch?v=dQw4w9WgXcQ'
        assert downloader._normalize_url(url) == 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

    def test_music_youtube_with_extra_params(self, downloader):
        url = 'https://music.youtube.com/watch?v=abc123&list=PLabc'
        result = downloader._normalize_url(url)
        assert result == 'https://www.youtube.com/watch?v=abc123'

    def test_regular_youtube_unchanged(self, downloader):
        url = 'https://www.youtube.com/watch?v=abc123'
        assert downloader._normalize_url(url) == url

    def test_youtu_be_unchanged(self, downloader):
        url = 'https://youtu.be/abc123'
        assert downloader._normalize_url(url) == url


# ── _detect_type ──────────────────────────────────────────────────────────────

class TestDetectType:
    def test_watch_url_is_song(self, downloader):
        assert downloader._detect_type('https://www.youtube.com/watch?v=abc') == 'song'

    def test_playlist_url_detected(self, downloader):
        assert downloader._detect_type('https://music.youtube.com/playlist?list=PLabc') == 'playlist'

    def test_browse_url_is_playlist(self, downloader):
        assert downloader._detect_type('https://music.youtube.com/browse/MPREb_abc123') == 'playlist'

    def test_video_with_list_is_song(self, downloader):
        # Has both v= and list=, v= takes precedence
        assert downloader._detect_type('https://www.youtube.com/watch?v=abc&list=PLxyz') == 'song'

    def test_empty_url_defaults_to_song(self, downloader):
        assert downloader._detect_type('') == 'song'


# ── _primary_artist ───────────────────────────────────────────────────────────

class TestPrimaryArtist:
    def test_single_artist(self, downloader):
        assert downloader._primary_artist('Daft Punk') == 'Daft Punk'

    def test_topic_suffix_stripped(self, downloader):
        assert downloader._primary_artist('Daft Punk - Topic') == 'Daft Punk'

    def test_comma_separated_keeps_first(self, downloader):
        assert downloader._primary_artist('Artist A, Artist B') == 'Artist A'

    def test_ampersand_keeps_first(self, downloader):
        assert downloader._primary_artist('Jay-Z & Kanye West') == 'Jay-Z'

    def test_pipe_separator_keeps_first(self, downloader):
        assert downloader._primary_artist('Artist A | Artist B') == 'Artist A'

    def test_and_keyword_keeps_first(self, downloader):
        assert downloader._primary_artist('Simon and Garfunkel') == 'Simon'

    def test_none_input(self, downloader):
        assert downloader._primary_artist(None) == 'Unknown Artist'

    def test_empty_string(self, downloader):
        assert downloader._primary_artist('') == 'Unknown Artist'

    def test_whitespace_only(self, downloader):
        assert downloader._primary_artist('  ') == 'Unknown Artist'


# ── _clean_filename ───────────────────────────────────────────────────────────

class TestCleanFilename:
    def test_clean_name_unchanged(self, downloader):
        assert downloader._clean_filename('Normal Song Name') == 'Normal Song Name'

    def test_colon_removed(self, downloader):
        assert downloader._clean_filename('Title: Subtitle') == 'Title Subtitle'

    def test_slash_removed(self, downloader):
        assert downloader._clean_filename('AC/DC') == 'ACDC'

    def test_question_mark_removed(self, downloader):
        assert downloader._clean_filename('Who Are You?') == 'Who Are You'

    def test_asterisk_removed(self, downloader):
        assert downloader._clean_filename('Guns N* Roses') == 'Guns N Roses'

    def test_all_forbidden_chars(self, downloader):
        result = downloader._clean_filename('<>:"/\\|?*')
        assert result == ''

    def test_trailing_whitespace_stripped(self, downloader):
        assert downloader._clean_filename('  Spaces  ') == 'Spaces'
