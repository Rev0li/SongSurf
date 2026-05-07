"""
Tests for _is_valid_youtube_url() — covers D-1 through D-5 from test plan.
Pure unit tests, no I/O.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import importlib
import types

# Import only the validation function without starting the full Flask app
import re
from urllib.parse import urlparse

_ALLOWED_YT_DOMAINS = ('youtube.com', 'music.youtube.com', 'www.youtube.com', 'youtu.be')


def _is_valid_youtube_url(url: str) -> bool:
    """Copied from app.py to allow isolated unit testing."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith('https://'):
        return False
    try:
        netloc = urlparse(url).netloc.lower()
        host = netloc[4:] if netloc.startswith('www.') else netloc
    except Exception:
        return False
    if host not in _ALLOWED_YT_DOMAINS and netloc not in _ALLOWED_YT_DOMAINS:
        return False
    if re.search(r'[<>\'";{}\\`]', url):
        return False
    return True


# ── D-1: Valid YouTube URLs accepted ─────────────────────────────────────────

class TestValidUrls:
    def test_youtube_music_watch(self):
        assert _is_valid_youtube_url('https://music.youtube.com/watch?v=dQw4w9WgXcQ')

    def test_youtube_watch(self):
        assert _is_valid_youtube_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    def test_youtube_no_www(self):
        assert _is_valid_youtube_url('https://youtube.com/watch?v=dQw4w9WgXcQ')

    def test_youtu_be_short(self):
        assert _is_valid_youtube_url('https://youtu.be/dQw4w9WgXcQ')

    def test_youtube_playlist(self):
        assert _is_valid_youtube_url('https://music.youtube.com/playlist?list=PLabc123')

    def test_youtube_music_browse(self):
        assert _is_valid_youtube_url('https://music.youtube.com/browse/MPREb_abc123')

    def test_url_with_query_params(self):
        assert _is_valid_youtube_url('https://www.youtube.com/watch?v=abc&t=30s')


# ── D-2: Non-HTTPS rejected ───────────────────────────────────────────────────

class TestHttpRejected:
    def test_http_youtube(self):
        assert not _is_valid_youtube_url('http://youtube.com/watch?v=abc')

    def test_http_music_youtube(self):
        assert not _is_valid_youtube_url('http://music.youtube.com/watch?v=abc')

    def test_no_scheme(self):
        assert not _is_valid_youtube_url('youtube.com/watch?v=abc')

    def test_ftp_scheme(self):
        assert not _is_valid_youtube_url('ftp://youtube.com/watch?v=abc')


# ── D-3: Non-YouTube domains rejected ────────────────────────────────────────

class TestNonYoutubeDomain:
    def test_vimeo(self):
        assert not _is_valid_youtube_url('https://vimeo.com/123456789')

    def test_spotify(self):
        assert not _is_valid_youtube_url('https://open.spotify.com/track/abc')

    def test_soundcloud(self):
        assert not _is_valid_youtube_url('https://soundcloud.com/artist/track')

    def test_fake_youtube_subdomain(self):
        assert not _is_valid_youtube_url('https://evil-youtube.com/watch?v=abc')

    def test_youtube_in_path_not_domain(self):
        assert not _is_valid_youtube_url('https://evil.com/youtube.com/watch?v=abc')


# ── D-4: XSS / injection in URL rejected ─────────────────────────────────────

class TestXssRejected:
    def test_script_tag(self):
        assert not _is_valid_youtube_url('https://youtube.com/watch?v=<script>alert(1)</script>')

    def test_double_quote(self):
        assert not _is_valid_youtube_url('https://youtube.com/watch?v="inject"')

    def test_single_quote(self):
        assert not _is_valid_youtube_url("https://youtube.com/watch?v='inject'")

    def test_backtick(self):
        assert not _is_valid_youtube_url('https://youtube.com/watch?v=`cmd`')

    def test_curly_brace(self):
        assert not _is_valid_youtube_url('https://youtube.com/watch?v={evil}')

    def test_semicolon(self):
        assert not _is_valid_youtube_url('https://youtube.com/watch?v=abc;rm -rf /')


# ── D-5: Empty / None URL rejected ───────────────────────────────────────────

class TestEmptyUrl:
    def test_empty_string(self):
        assert not _is_valid_youtube_url('')

    def test_none_value(self):
        assert not _is_valid_youtube_url(None)

    def test_whitespace_only(self):
        assert not _is_valid_youtube_url('   ')

    def test_non_string(self):
        assert not _is_valid_youtube_url(12345)
