"""
Shared pytest fixtures for SongSurf test suite.
"""
import sys
import os
import time
import pytest

# Ensure server/ and watcher/ are importable without installing as packages
SERVER_DIR = os.path.join(os.path.dirname(__file__), '..', 'server')
WATCHER_DIR = os.path.join(os.path.dirname(__file__), '..', 'watcher')
sys.path.insert(0, os.path.abspath(SERVER_DIR))
sys.path.insert(0, os.path.abspath(WATCHER_DIR))

# Set env vars before any module import so Flask reads them
os.environ.setdefault('DEV_MODE', 'false')
os.environ.setdefault('WATCHER_SECRET', 'test-secret-fixed')
os.environ.setdefault('FLASK_SECRET_KEY', 'test-flask-key')
os.environ.setdefault('FLASK_PORT', '8082')

# Point music/temp dirs to a temp path (overridden per-test where needed)
import tempfile
_TMP = tempfile.mkdtemp(prefix='songsurf_test_')
os.environ.setdefault('MUSIC_BASE_DIR', _TMP)


@pytest.fixture
def tmp_music_dir(tmp_path):
    """A temporary music base directory."""
    d = tmp_path / 'music'
    d.mkdir()
    return d


@pytest.fixture
def tmp_temp_dir(tmp_path):
    """A temporary staging directory."""
    d = tmp_path / 'temp'
    d.mkdir()
    return d
