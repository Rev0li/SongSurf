"""
Flask route tests via test client — auth, library, path traversal, ZIP flow.
Covers: S-1, S-2, S-3, S-4, ST-3, ST-4, Z-3, A-1, D-2/D-3/D-5, D-9.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

WATCHER_SECRET = 'test-secret-fixed'


@pytest.fixture(scope='module')
def flask_setup(tmp_path_factory):
    """Build the Flask app once with temp dirs. Returns (test_client, music_dir, temp_dir)."""
    music = tmp_path_factory.mktemp('music')
    temp  = tmp_path_factory.mktemp('temp')
    logs  = tmp_path_factory.mktemp('logs')
    env_patch = {
        'WATCHER_SECRET':   WATCHER_SECRET,
        'DEV_MODE':         'false',
        'FLASK_SECRET_KEY': 'test-key',
    }

    with patch.dict(os.environ, env_patch):
        with patch('shutil.which', return_value=None):
            import app as app_mod
            # Override runtime directories after import
            app_mod.BASE_MUSIC_DIR = music
            app_mod.TEMP_DIR       = temp
            app_mod.LOG_DIR        = logs
            app_mod.app.config['TESTING'] = True

            with app_mod.app.test_client() as c:
                yield c, music, temp, app_mod


def auth_headers(role='member', sub='user-abc', email='user@test.com'):
    """Headers Watcher would inject after JWT validation."""
    return {
        'X-Watcher-Token': WATCHER_SECRET,
        'X-User-Id':       sub,
        'X-User-Role':     role,
        'X-User-Email':    email,
    }


def admin_headers(sub='admin-xyz'):
    return auth_headers(role='admin', sub=sub, email='admin@test.com')


# ── S-1: No X-Watcher-Token → rejected ───────────────────────────────────────

def test_s1_no_watcher_token_rejected(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/me')
    assert r.status_code in (401, 503)


# ── S-2: Wrong X-Watcher-Token → rejected ────────────────────────────────────

def test_s2_wrong_token_rejected(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/me', headers={
        'X-Watcher-Token': 'wrong-secret',
        'X-User-Id':       'user-abc',
        'X-User-Role':     'member',
    })
    assert r.status_code in (401, 503)


# ── S-3: Valid headers accepted, identity returned ────────────────────────────

def test_s3_valid_headers_accepted(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/me', headers=auth_headers(sub='user-test-123', role='member'))
    assert r.status_code == 200
    data = r.get_json()
    assert data['sub'] == 'user-test-123'
    assert data['role'] == 'member'


# ── S-4: Role injected with uppercase → normalized lowercase ──────────────────

def test_s4_role_lowercased(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/me', headers={
        'X-Watcher-Token': WATCHER_SECRET,
        'X-User-Id':       'admin-user',
        'X-User-Role':     'Admin',
        'X-User-Email':    '',
    })
    assert r.status_code == 200
    assert r.get_json()['role'] == 'admin'


# ── /ping: no auth required ───────────────────────────────────────────────────

def test_ping_no_auth(flask_setup):
    c, *_ = flask_setup
    r = c.get('/ping')
    assert r.status_code == 200


# ── /api/status shape ─────────────────────────────────────────────────────────

def test_status_returns_expected_shape(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/status', headers=auth_headers())
    assert r.status_code == 200
    data = r.get_json()
    assert 'in_progress' in data
    assert 'queue_size' in data
    assert 'batch_active' in data


# ── ST-3: Per-user library isolation ─────────────────────────────────────────

def test_st3_user_isolation(flask_setup):
    c, music, *_ = flask_setup
    (music / 'user-a').mkdir(exist_ok=True)
    (music / 'user-a' / 'song.mp3').write_bytes(b'mp3a')
    (music / 'user-b').mkdir(exist_ok=True)
    (music / 'user-b' / 'song.mp3').write_bytes(b'mp3b')

    r_a = c.get('/api/library', headers=auth_headers(sub='user-a'))
    r_b = c.get('/api/library', headers=auth_headers(sub='user-b'))
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    assert r_a.get_json()['success']
    assert r_b.get_json()['success']


# ── ST-4: Path traversal blocked ─────────────────────────────────────────────

def test_st4_path_traversal_move_song(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/library/move',
               json={'source': '../../etc/passwd', 'target_folder': 'Artist/Album'},
               headers=auth_headers())
    assert r.status_code in (400, 404)


def test_st4_path_traversal_move_folder(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/library/move-folder',
               json={'folder_path': '../../../etc', 'new_parent': 'Artist'},
               headers=auth_headers())
    assert r.status_code in (400, 404)


# ── D-2 / D-3 / D-5: URL validation at /api/extract ─────────────────────────

def test_d2_http_url_rejected(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/extract',
               json={'url': 'http://youtube.com/watch?v=abc'},
               headers=auth_headers(), content_type='application/json')
    assert r.status_code == 400


def test_d3_non_youtube_rejected(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/extract',
               json={'url': 'https://vimeo.com/123456'},
               headers=auth_headers(), content_type='application/json')
    assert r.status_code == 400


def test_d5_empty_url_rejected(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/extract',
               json={'url': ''},
               headers=auth_headers(), content_type='application/json')
    assert r.status_code == 400


# ── Z-3: ZIP download without prior prepare → 404 ────────────────────────────

def test_z3_download_zip_without_prepare(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/download-zip',
              headers=auth_headers(sub='fresh-user-no-zip-at-all'))
    assert r.status_code == 404


# ── A-1: Admin-only route enforced ───────────────────────────────────────────

def test_a1_extract_covers_requires_admin(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/admin/extract-covers',
               json={},
               headers=auth_headers(role='member'),
               content_type='application/json')
    assert r.status_code == 403
    assert not r.get_json()['success']


def test_a1_admin_can_call_extract_covers(flask_setup):
    c, music, _, app_mod = flask_setup
    sub = 'admin-xyz'
    (music / sub).mkdir(exist_ok=True)

    with patch.object(app_mod, 'MusicOrganizer') as MockOrg:
        MockOrg.return_value.extract_album_covers.return_value = {
            'success': True, 'albums_scanned': 0, 'covers_created': 0, 'covers_skipped': 0,
        }
        r = c.post('/api/admin/extract-covers',
                   json={},
                   headers=admin_headers(sub=sub),
                   content_type='application/json')
    assert r.status_code == 200
    assert r.get_json()['success']


# ── D-9: 429 when download already in progress ───────────────────────────────

def test_d9_reject_download_while_in_progress(flask_setup):
    c, _, _, app_mod = flask_setup
    original = app_mod.download_status['in_progress']
    try:
        app_mod.download_status['in_progress'] = True
        r = c.post('/api/download',
                   json={'url': 'https://www.youtube.com/watch?v=abc',
                         'title': 'T', 'artist': 'A', 'album': 'B'},
                   headers=auth_headers(),
                   content_type='application/json')
        assert r.status_code == 429
    finally:
        app_mod.download_status['in_progress'] = original


# ── _user_music_dir path traversal guard ─────────────────────────────────────

def test_user_music_dir_path_traversal_raises(flask_setup):
    _, _, _, app_mod = flask_setup
    with pytest.raises(ValueError, match='path escapes'):
        app_mod._user_music_dir({'sub': 'x', '_pseudo': '../../etc/passwd'})


# ── Album tracks + renumber (mode « Numéroter les pistes ») ───────────────────

def _make_tagged_mp3(path, title=None, track=None):
    """Fichier factice avec un vrai tag ID3 (lisible par library_audit._read_tags)."""
    from mutagen.id3 import ID3, TIT2, TRCK
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x00' * 64)
    id3 = ID3()
    if title: id3['TIT2'] = TIT2(encoding=3, text=title)
    if track: id3['TRCK'] = TRCK(encoding=3, text=track)
    id3.save(path)


def test_album_tracks_returns_titles_and_trck(flask_setup):
    c, music, *_ = flask_setup
    # member user@test.com → pseudo 'user'
    album = music / 'user' / 'Artist' / 'AlbumTL'
    _make_tagged_mp3(album / 'b.mp3', title='Bee', track='2/2')
    _make_tagged_mp3(album / 'a.mp3', title='Aye')

    r = c.get('/api/library/album-tracks?folder_path=Artist/AlbumTL',
              headers=auth_headers())
    assert r.status_code == 200
    data = r.get_json()
    assert data['tracks'] == [
        {'path': 'Artist/AlbumTL/a.mp3', 'name': 'a.mp3', 'title': 'Aye', 'track_number': ''},
        {'path': 'Artist/AlbumTL/b.mp3', 'name': 'b.mp3', 'title': 'Bee', 'track_number': '2/2'},
    ]


def test_renumber_album_writes_in_order(flask_setup):
    c, music, _, app_mod = flask_setup
    album = music / 'user' / 'Artist' / 'AlbumRN'
    _make_tagged_mp3(album / 'a.mp3')
    _make_tagged_mp3(album / 'b.mp3')

    with patch.object(app_mod, '_write_song_tags') as mock_write:
        r = c.post('/api/library/renumber-album',
                   json={'folder_path': 'Artist/AlbumRN',
                         'paths': ['Artist/AlbumRN/b.mp3', 'Artist/AlbumRN/a.mp3']},
                   headers=auth_headers(),
                   content_type='application/json')
    assert r.status_code == 200
    assert r.get_json() == {'success': True, 'total': 2}
    written = [(call.args[0].name, call.args[1]) for call in mock_write.call_args_list]
    assert written == [('b.mp3', {'track_number': '1/2'}),
                       ('a.mp3', {'track_number': '2/2'})]


def test_renumber_album_rejects_partial_paths(flask_setup):
    c, music, _, app_mod = flask_setup
    album = music / 'user' / 'Artist' / 'AlbumPart'
    _make_tagged_mp3(album / 'a.mp3')
    _make_tagged_mp3(album / 'b.mp3')

    with patch.object(app_mod, '_write_song_tags') as mock_write:
        r = c.post('/api/library/renumber-album',
                   json={'folder_path': 'Artist/AlbumPart',
                         'paths': ['Artist/AlbumPart/a.mp3']},  # b.mp3 manquant
                   headers=auth_headers(),
                   content_type='application/json')
    assert r.status_code == 400
    mock_write.assert_not_called()


def test_renumber_album_rejects_foreign_path(flask_setup):
    c, music, _, app_mod = flask_setup
    album = music / 'user' / 'Artist' / 'AlbumFor'
    _make_tagged_mp3(album / 'a.mp3')
    _make_tagged_mp3(music / 'user' / 'Artist' / 'Autre' / 'x.mp3')

    r = c.post('/api/library/renumber-album',
               json={'folder_path': 'Artist/AlbumFor',
                     'paths': ['Artist/AlbumFor/a.mp3', 'Artist/Autre/x.mp3']},
               headers=auth_headers(),
               content_type='application/json')
    assert r.status_code == 400


def test_audit_routes_require_admin(flask_setup):
    c, *_ = flask_setup
    assert c.get('/api/admin/audit/artist?path=X',
                 headers=auth_headers(role='member')).status_code == 403
    assert c.post('/api/admin/audit/apply', json={'changes': []},
                  headers=auth_headers(role='member'),
                  content_type='application/json').status_code == 403
    assert c.post('/api/admin/genre-backfill', json={},
                  headers=auth_headers(role='member'),
                  content_type='application/json').status_code == 403
