"""
Flask route tests via test client — auth, library, path traversal, ZIP flow.
Covers: S-1, S-2, S-3, S-4, ST-1, ST-2, ST-3, ST-4, Z-3, Z-5, A-1, D-2/D-3/D-5, D-9.
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
    cookies = tmp_path_factory.mktemp('cookies')
    env_patch = {
        'WATCHER_SECRET':    WATCHER_SECRET,
        'DEV_MODE':          'false',
        'FLASK_SECRET_KEY':  'test-key',
        'YTDLP_COOKIES_DIR': str(cookies),
    }

    with patch.dict(os.environ, env_patch):
        with patch('shutil.which', return_value=None):
            import app as app_mod
            # Override runtime directories after import
            app_mod.BASE_MUSIC_DIR = music
            app_mod.TEMP_DIR       = temp
            app_mod.LOG_DIR        = logs
            app_mod.COOKIES_DIR    = cookies
            app_mod.app.config['TESTING'] = True

            with app_mod.app.test_client() as c:
                yield c, music, temp, app_mod


def auth_headers(role='member', sub='user-abc', email='user@test.com'):
    """Headers Watcher would inject after the portal gate."""
    return {
        'X-Watcher-Token': WATCHER_SECRET,
        'X-User-Id':       sub,
        'X-User-Role':     role,
        'X-User-Email':    email,
    }


def admin_headers(sub='admin-xyz'):
    return auth_headers(role='admin', sub=sub, email='admin@test.com')


_NETSCAPE = ('# Netscape HTTP Cookie File\n'
             '.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tvalue\n')


def give_cookies(app_mod, pseudo='user'):
    """Écrit un fichier cookies pour <pseudo> (par défaut auth_headers() → 'user')."""
    f = app_mod.COOKIES_DIR / f'{pseudo}.txt'
    f.write_text(_NETSCAPE)
    return f


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


# ── Static assets from build root (fonts, help images) served without auth ────

def test_static_root_assets_served_no_auth(flask_setup, tmp_path):
    c, _m, _t, app_mod = flask_setup
    build = tmp_path / 'build'
    (build / 'help').mkdir(parents=True)
    (build / 'help' / 'download-1.png').write_bytes(b'\x89PNG\r\n\x1a\n fake')
    with patch.object(app_mod, '_FRONTEND_BUILD', build.resolve()):
        # Real file → served, no auth needed
        r = c.get('/help/download-1.png')
        assert r.status_code == 200
        assert r.data.startswith(b'\x89PNG')
        # Unknown path → 404 (not the SPA, not a 500)
        assert c.get('/help/nope.png').status_code == 404


def test_static_root_assets_no_traversal(flask_setup, tmp_path):
    c, _m, _t, app_mod = flask_setup
    build = tmp_path / 'build2'
    build.mkdir()
    (tmp_path / 'secret.txt').write_text('nope')
    with patch.object(app_mod, '_FRONTEND_BUILD', build.resolve()):
        r = c.get('/%2e%2e/secret.txt')
        assert r.status_code in (400, 404)


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


# ── D-9: la file serveur empile même si un download est en cours ──────────────
# (correction du bug « ça bloque si on n'est pas sur la page Téléchargement » :
#  le worker draine séquentiellement, donc on accepte d'empiler.)

def test_d9_accepts_download_while_in_progress(flask_setup):
    c, _, _, app_mod = flask_setup
    give_cookies(app_mod)
    original = app_mod.download_status['in_progress']
    try:
        app_mod.download_status['in_progress'] = True
        r = c.post('/api/download',
                   json={'url': 'https://www.youtube.com/watch?v=abc',
                         'title': 'T', 'artist': 'A', 'album': 'B'},
                   headers=auth_headers(),
                   content_type='application/json')
        assert r.status_code == 200
        assert r.get_json()['success'] is True
    finally:
        app_mod.download_status['in_progress'] = original
        # purge le job ajouté pour ne pas polluer les autres tests
        try:
            while True:
                app_mod.job_queue.get_nowait()
        except Exception:
            pass
        app_mod._pending_songs = 0


def test_d9_rejects_when_queue_full(flask_setup):
    c, _, _, app_mod = flask_setup
    give_cookies(app_mod)
    import queue as _q
    try:
        # Sature la file de jobs jusqu'à maxsize
        while True:
            try:
                app_mod.job_queue.put_nowait({'songs': []})
            except _q.Full:
                break
        r = c.post('/api/download',
                   json={'url': 'https://www.youtube.com/watch?v=abc',
                         'title': 'T', 'artist': 'A', 'album': 'B'},
                   headers=auth_headers(),
                   content_type='application/json')
        assert r.status_code == 429
    finally:
        try:
            while True:
                app_mod.job_queue.get_nowait()
        except Exception:
            pass
        app_mod._pending_songs = 0


# ── Cookies / vidéos restreintes par âge (bug 5) ──────────────────────────────

def test_cookie_error_detection_and_friendly_message(flask_setup):
    _, _, _, app_mod = flask_setup
    yt_err = ("ERROR: [youtube] HocWhDnvyhA: Sign in to confirm your age. "
              "This video may be inappropriate for some users. Use --cookies-from-browser")
    assert app_mod._is_cookie_error(yt_err) is True
    friendly = app_mod._friendly_download_error(yt_err)
    assert 'cookies' in friendly.lower()
    assert friendly != yt_err  # message reformulé, pas l'erreur brute


def test_non_cookie_error_passes_through(flask_setup):
    _, _, _, app_mod = flask_setup
    other = 'HTTP Error 404: Not Found'
    assert app_mod._is_cookie_error(other) is False
    assert app_mod._friendly_download_error(other) == other


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


# ── Genre artiste (TCON réécrit sur tous les albums) ─────────────────────────

def _make_real_mp3(path):
    """MP3 minimal avec de vraies frames MPEG : mutagen.MP3() doit pouvoir l'ouvrir
    (contrairement à _make_tagged_mp3, réservé aux routes qui ne lisent que l'ID3)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = b'\xff\xfb\x90\x00' + b'\x00' * 413  # MPEG-1 Layer III 128kbps 44.1kHz
    path.write_bytes(frame * 4)


def test_set_artist_genre_writes_all_albums(flask_setup):
    c, music, _, app_mod = flask_setup
    artist = music / 'user' / 'ArtistG'
    _make_real_mp3(artist / 'Al1' / 'a.mp3')
    _make_real_mp3(artist / 'Al1' / 'b.mp3')
    _make_real_mp3(artist / 'Al2' / 'c.mp3')
    (artist / 'Al1' / 'cover.jpg').write_bytes(b'x')  # ignoré (pas un MP3)

    r = c.post('/api/library/set-artist-genre',
               json={'folder_path': 'ArtistG', 'genre': 'Rock; Pop'},
               headers=auth_headers(),
               content_type='application/json')
    assert r.status_code == 200
    data = r.get_json()
    assert data['updated'] == 3 and data['errors'] == []

    from mutagen.id3 import ID3
    for rel in ('Al1/a.mp3', 'Al1/b.mp3', 'Al2/c.mp3'):
        assert [str(t) for t in ID3(artist / rel)['TCON'].text] == ['Rock', 'Pop']


def test_set_artist_genre_requires_genre(flask_setup):
    c, music, _, app_mod = flask_setup
    _make_tagged_mp3(music / 'user' / 'ArtistGE' / 'Al' / 'a.mp3')

    r = c.post('/api/library/set-artist-genre',
               json={'folder_path': 'ArtistGE', 'genre': '  '},
               headers=auth_headers(),
               content_type='application/json')
    assert r.status_code == 400


def test_set_artist_genre_rejects_music_root_and_escape(flask_setup):
    c, *_ = flask_setup
    for bad in ('.', '../autre'):
        r = c.post('/api/library/set-artist-genre',
                   json={'folder_path': bad, 'genre': 'Rock'},
                   headers=auth_headers(),
                   content_type='application/json')
        assert r.status_code == 400, bad


def test_me_returns_pseudo(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/me', headers=auth_headers(email='oliver.k@test.com'))
    assert r.get_json()['pseudo'] == 'oliver.k'
    r = c.get('/api/me', headers=admin_headers())
    assert r.get_json()['pseudo'] == 'rev0admin'


def test_album_status_counts_missing_tags(flask_setup):
    from mutagen.id3 import ID3, TCON, TDRC
    c, music, *_ = flask_setup
    artist = music / 'user' / 'ArtistST'
    _make_tagged_mp3(artist / 'Complet' / 'a.mp3', title='A', track='1/1')
    f = artist / 'Complet' / 'a.mp3'
    id3 = ID3(f)
    id3['TCON'] = TCON(encoding=3, text=['Rap'])
    id3['TDRC'] = TDRC(encoding=3, text='2016')
    id3.save(f)
    _make_tagged_mp3(artist / 'Trous' / 'b.mp3', title='B')  # ni genre, ni année, ni TRCK

    r = c.get('/api/library/album-status?folder_path=ArtistST',
              headers=auth_headers())
    assert r.status_code == 200
    albums = {a['name']: a for a in r.get_json()['albums']}
    assert albums['Complet']['complete'] is True
    assert albums['Trous']['complete'] is False
    assert albums['Trous']['missing'] == {'genre': 1, 'year': 1, 'track_number': 1}


def test_audit_routes_open_to_members(flask_setup):
    """Le scan iTunes (audit) est accessible à tous les membres, sur leur
    propre bibliothèque — pas seulement à l'admin."""
    c, *_ = flask_setup
    # Pas de 403 : la route accepte le membre (404 car l'artiste n'existe pas).
    assert c.get('/api/library/audit/artist?path=Nope',
                 headers=auth_headers(role='member')).status_code != 403
    # Apply avec une liste vide : pas de 403, traité normalement (200).
    r = c.post('/api/library/audit/apply', json={'changes': []},
               headers=auth_headers(role='member'),
               content_type='application/json')
    assert r.status_code == 200


def test_genre_backfill_still_admin_only(flask_setup):
    c, *_ = flask_setup
    assert c.post('/api/admin/genre-backfill', json={},
                  headers=auth_headers(role='member'),
                  content_type='application/json').status_code == 403


# ── Suppression de dossier (admin) ────────────────────────────────────────────

def test_delete_folder_requires_admin(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/library/delete-folder',
               json={'folder_path': 'Artist/Album'},
               headers=auth_headers(role='member'),
               content_type='application/json')
    assert r.status_code == 403


def test_delete_album_folder_and_empty_parent(flask_setup):
    c, music, *_ = flask_setup
    album = music / 'rev0admin' / 'ArtistDel' / 'AlbumDel'
    album.mkdir(parents=True)
    (album / 'a.mp3').write_bytes(b'mp3')
    (album / 'b.mp3').write_bytes(b'mp3')
    (album / 'cover.jpg').write_bytes(b'jpg')

    r = c.post('/api/library/delete-folder',
               json={'folder_path': 'ArtistDel/AlbumDel'},
               headers=admin_headers(),
               content_type='application/json')
    assert r.status_code == 200
    assert r.get_json()['deleted_songs'] == 2
    assert not album.exists()
    # Dernier album → le dossier artiste vide est retiré aussi
    assert not (music / 'rev0admin' / 'ArtistDel').exists()


def test_delete_artist_folder_keeps_siblings(flask_setup):
    c, music, *_ = flask_setup
    artist = music / 'rev0admin' / 'ArtistDel2'
    (artist / 'Album1').mkdir(parents=True)
    (artist / 'Album1' / 'a.mp3').write_bytes(b'mp3')
    other = music / 'rev0admin' / 'ArtistKeep'
    other.mkdir(parents=True)

    r = c.post('/api/library/delete-folder',
               json={'folder_path': 'ArtistDel2'},
               headers=admin_headers(),
               content_type='application/json')
    assert r.status_code == 200
    assert not artist.exists()
    assert other.exists()


def test_delete_folder_rejects_root_and_traversal(flask_setup):
    c, music, *_ = flask_setup
    (music / 'rev0admin').mkdir(exist_ok=True)
    # Racine de la bibliothèque
    r = c.post('/api/library/delete-folder',
               json={'folder_path': ''},
               headers=admin_headers(), content_type='application/json')
    assert r.status_code == 400
    r = c.post('/api/library/delete-folder',
               json={'folder_path': '.'},
               headers=admin_headers(), content_type='application/json')
    assert r.status_code == 400
    # Traversal hors bibliothèque
    r = c.post('/api/library/delete-folder',
               json={'folder_path': '../../etc'},
               headers=admin_headers(), content_type='application/json')
    assert r.status_code in (400, 404)


def test_delete_folder_missing_dir_404(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/library/delete-folder',
               json={'folder_path': 'NopeArtist/NopeAlbum'},
               headers=admin_headers(), content_type='application/json')
    assert r.status_code == 404


# ── Images: cache HTTP + persistance de l'extraction APIC ────────────────────
# Les URLs d'images sont versionnées côté frontend (?t=<version>) : le serveur
# doit renvoyer un Cache-Control pour que le navigateur garde les pochettes.

def _tiny_png_bytes():
    from PIL import Image
    import io as _io
    buf = _io.BytesIO()
    Image.new('RGB', (4, 4), (200, 30, 30)).save(buf, format='PNG')
    return buf.getvalue()


def test_folder_cover_file_served_with_cache_header(flask_setup):
    c, music, *_ = flask_setup
    album = music / 'user' / 'ArtistC' / 'AlbumFile'
    album.mkdir(parents=True)
    (album / 'cover.jpg').write_bytes(b'\xff\xd8\xff\xdbjpegdata')

    r = c.get('/api/library/folder-cover?folder_path=ArtistC/AlbumFile',
              headers=auth_headers())
    assert r.status_code == 200
    assert r.headers['Cache-Control'] == 'private, max-age=86400'


def test_folder_cover_apic_extraction_persists_cover_jpg(flask_setup):
    c, music, *_ = flask_setup
    album = music / 'user' / 'ArtistC' / 'AlbumApic'
    _make_real_mp3(album / 'a.mp3')
    from mutagen.id3 import ID3, APIC
    id3 = ID3()
    id3['APIC'] = APIC(encoding=3, mime='image/png', type=3, desc='',
                       data=_tiny_png_bytes())
    id3.save(album / 'a.mp3')

    r = c.get('/api/library/folder-cover?folder_path=ArtistC/AlbumApic',
              headers=auth_headers())
    assert r.status_code == 200
    assert r.headers['Cache-Control'] == 'private, max-age=86400'
    assert r.data[:3] == b'\xff\xd8\xff'  # converti en JPEG
    # L'extraction est persistée : les requêtes suivantes servent le fichier
    # sans re-parser le MP3
    cover = album / 'cover.jpg'
    assert cover.exists() and cover.read_bytes()[:3] == b'\xff\xd8\xff'


def test_folder_cover_no_cover_still_204(flask_setup):
    c, music, *_ = flask_setup
    album = music / 'user' / 'ArtistC' / 'AlbumBare'
    _make_real_mp3(album / 'a.mp3')  # aucun APIC

    r = c.get('/api/library/folder-cover?folder_path=ArtistC/AlbumBare',
              headers=auth_headers())
    assert r.status_code == 204
    assert not (album / 'cover.jpg').exists()


def test_artist_picture_served_with_cache_header(flask_setup):
    c, music, *_ = flask_setup
    artist = music / 'user' / 'ArtistPic'
    artist.mkdir(parents=True)
    (artist / 'folder.jpg').write_bytes(b'\xff\xd8\xffjpeg')

    r = c.get('/api/library/artist-picture?folder_path=ArtistPic',
              headers=auth_headers())
    assert r.status_code == 200
    assert r.headers['Cache-Control'] == 'private, max-age=86400'


# ── SSF-01 : cookies par utilisateur, taille max, cloisonnement /api/status ───

def _drain_queue(app_mod):
    try:
        while True:
            app_mod.job_queue.get_nowait()
    except Exception:
        pass
    app_mod._pending_songs = 0
    app_mod._pending_queue.clear()


def test_ssf01_download_blocked_without_cookies(flask_setup):
    c, *_ = flask_setup
    for path, body in [
        ('/api/download', {'url': 'https://www.youtube.com/watch?v=abc', 'title': 'T'}),
        ('/api/download-playlist', {'playlist_metadata': {'songs': [{'url': 'u', 'title': 't'}]}}),
        ('/api/queue-direct', {'url': 'https://music.youtube.com/watch?v=abc'}),
        ('/api/preview', {'url': 'https://music.youtube.com/watch?v=abc'}),
        ('/api/extract', {'url': 'https://music.youtube.com/watch?v=abc'}),
    ]:
        r = c.post(path, json=body, headers=auth_headers(sub='nocookie', email='nocookie@test.com'))
        assert r.status_code == 403, path
        data = r.get_json()
        assert data['code'] == 'cookies_missing'
        assert 'extension' in data['error']


def test_ssf01_no_fallback_on_admin_cookies(flask_setup):
    c, _, _, app_mod = flask_setup
    give_cookies(app_mod, pseudo=app_mod.ADMIN_PSEUDO)
    r = c.post('/api/download', json={'url': 'https://www.youtube.com/watch?v=abc'},
               headers=auth_headers(sub='member2', email='member2@test.com'))
    assert r.status_code == 403


def test_ssf01_cookies_update_is_per_user(flask_setup):
    c, _, _, app_mod = flask_setup
    r = c.post('/api/cookies/update', json={'cookies': _NETSCAPE},
               headers=auth_headers(sub='alice', email='alice@test.com'))
    assert r.status_code == 200
    data = r.get_json()
    assert data['pseudo'] == 'alice' and data['count'] == 1
    f = app_mod.COOKIES_DIR / 'alice.txt'
    assert f.is_file()
    assert (f.stat().st_mode & 0o777) == 0o600
    # Un autre membre n'en profite pas
    assert not (app_mod.COOKIES_DIR / 'bob.txt').exists()
    r = c.get('/api/status', headers=auth_headers(sub='bob', email='bob@test.com'))
    assert r.get_json()['cookies_present'] is False
    r = c.get('/api/status', headers=auth_headers(sub='alice', email='alice@test.com'))
    assert r.get_json()['cookies_present'] is True


def test_ssf01_cookies_update_rejects_bad_format(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/cookies/update', json={'cookies': 'not a cookie file'},
               headers=auth_headers(sub='carol', email='carol@test.com'))
    assert r.status_code == 400


def test_ssf01_netscape_validation():
    import app as app_mod
    assert app_mod._is_netscape_cookies(_NETSCAPE)
    assert app_mod._is_netscape_cookies('#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tA\tb')
    assert not app_mod._is_netscape_cookies('# only comments\n')
    assert not app_mod._is_netscape_cookies('a\tb\tc')


def test_ssf01_request_too_large(flask_setup):
    c, _, _, app_mod = flask_setup
    big = 'x' * (app_mod.MAX_REQUEST_MB * 1024 * 1024 + 1)
    r = c.post('/api/cookies/update', data=big, headers={**auth_headers(), 'Content-Type': 'application/json'})
    assert r.status_code == 413
    assert '20 Mo' in r.get_json()['error']


def test_ssf01_status_isolated_between_members(flask_setup):
    c, _, _, app_mod = flask_setup
    with app_mod.queue_lock:
        app_mod._last_completed_by_user['alice'] = {'file_path': '/secret/alice.mp3', 'timestamp': 't1'}
        app_mod._last_error_by_user['alice'] = {'error': 'boom', 'timestamp': 't2'}
        app_mod.download_status['current_download'] = {
            'url': 'u', 'metadata': {'title': 'Secret'}, 'user_sub': 'alice'}
    try:
        bob = c.get('/api/status', headers=auth_headers(sub='bob', email='bob@test.com')).get_json()
        assert bob['last_completed'] is None
        assert bob['last_error'] is None
        assert bob['current_download'] is None
        assert bob['is_mine'] is False

        alice = c.get('/api/status', headers=auth_headers(sub='alice', email='alice@test.com')).get_json()
        assert alice['last_completed']['file_path'] == '/secret/alice.mp3'
        assert alice['last_error']['error'] == 'boom'
        assert alice['current_download']['metadata']['title'] == 'Secret'
        assert alice['is_mine'] is True
    finally:
        with app_mod.queue_lock:
            app_mod._last_completed_by_user.clear()
            app_mod._last_error_by_user.clear()
            app_mod.download_status['current_download'] = None


def test_ssf01_worker_uses_owner_cookies(flask_setup):
    _, music, _, app_mod = flask_setup
    f = give_cookies(app_mod, pseudo='dave')
    item = {'url': 'https://www.youtube.com/watch?v=abc',
            'metadata': {'artist': 'A', 'album': 'B', 'title': 'T'},
            'user_sub': 'dave-sub', 'user_pseudo': 'dave', 'user_role': 'member'}
    with patch.object(app_mod.downloader, 'download',
                      return_value={'success': False, 'error': 'x'}) as dl:
        app_mod._process_song(item)
    assert dl.call_args.kwargs['cookiefile'] == str(f.resolve())
    assert app_mod._last_error_by_user['dave-sub']['error'] == 'x'
    app_mod._last_error_by_user.clear()


def test_ssf01_worker_fails_cleanly_when_cookies_removed(flask_setup):
    _, _, _, app_mod = flask_setup
    item = {'url': 'https://www.youtube.com/watch?v=abc',
            'metadata': {'artist': 'A', 'album': 'B', 'title': 'T'},
            'user_sub': 'erin-sub', 'user_pseudo': 'erin', 'user_role': 'member'}
    with patch.object(app_mod.downloader, 'download') as dl:
        app_mod._process_song(item)
    dl.assert_not_called()
    assert 'Cookies YouTube manquants' in app_mod._last_error_by_user['erin-sub']['error']
    app_mod._last_error_by_user.clear()


def test_ssf01_legacy_cookies_migrated_to_admin(flask_setup, tmp_path):
    _, _, _, app_mod = flask_setup
    legacy = tmp_path / 'cookies.txt'
    legacy.write_text(_NETSCAPE)
    target = app_mod.COOKIES_DIR / f'{app_mod.ADMIN_PSEUDO}.txt'
    target.unlink(missing_ok=True)
    with patch.object(app_mod, '_LEGACY_COOKIES_FILE', legacy):
        app_mod._migrate_legacy_cookies()
    assert target.read_text() == _NETSCAPE
    assert not legacy.exists()


# ── SSF-02 : arrêt propre ─────────────────────────────────────────────────────

def test_ssf02_cleanup_temp_leftovers(flask_setup, tmp_path):
    _, _, _, app_mod = flask_setup
    for name in ('a.part', 'b.ytdl', 'c.temp.mp3', 'd.webm.part-Frag3', 'done.mp3'):
        (tmp_path / name).touch()
    with patch.object(app_mod.downloader, 'temp_dir', tmp_path):
        app_mod._cleanup_temp_leftovers()
    assert sorted(f.name for f in tmp_path.iterdir()) == ['done.mp3']


def test_ssf02_sigterm_removes_current_song_files_and_exits_0(flask_setup, tmp_path):
    _, _, _, app_mod = flask_setup
    meta = {'artist': 'Art', 'title': 'Song'}
    prefix = app_mod.downloader._temp_filename_from_metadata(meta)
    (tmp_path / f'{prefix}.webm.part').touch()
    (tmp_path / f'{prefix}.temp.mp3').touch()
    (tmp_path / 'Other - Track.mp3').touch()
    with app_mod.queue_lock:
        app_mod.download_status['current_download'] = {'metadata': meta, 'user_sub': 'x'}
    try:
        with patch.object(app_mod.downloader, 'temp_dir', tmp_path):
            with pytest.raises(SystemExit) as exc:
                app_mod._on_sigterm(15, None)
        assert exc.value.code == 0
        assert [f.name for f in tmp_path.iterdir()] == ['Other - Track.mp3']
    finally:
        with app_mod.queue_lock:
            app_mod.download_status['current_download'] = None


def test_ssf02_sigterm_idle_exits_0(flask_setup):
    _, _, _, app_mod = flask_setup
    with pytest.raises(SystemExit) as exc:
        app_mod._on_sigterm(15, None)
    assert exc.value.code == 0


# ── SSF-10 : export ZIP désactivé pour la bibliothèque admin ──────────────────

def test_ssf10_admin_zip_disabled(flask_setup):
    c, music, _, app_mod = flask_setup
    song = music / app_mod.ADMIN_PSEUDO / 'Artist' / 'Album' / 'Song.mp3'
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b'ID3')
    try:
        r = c.post('/api/prepare-zip', headers=admin_headers())
        assert r.status_code == 403
        assert r.get_json()['code'] == 'zip_disabled'
        assert c.get('/api/download-zip', headers=admin_headers()).status_code == 403
        assert song.exists()
    finally:
        song.unlink(missing_ok=True)


def test_ssf10_zip_refused_on_admin_dir_whatever_the_role(flask_setup, tmp_path):
    # La règle porte aussi sur le dossier : même un ZIP déjà préparé ne vide jamais le dossier admin.
    c, music, _, app_mod = flask_setup
    keep = music / app_mod.ADMIN_PSEUDO / 'keep.mp3'
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_bytes(b'ID3')
    stale_zip = tmp_path / 'stale.zip'
    stale_zip.write_bytes(b'PK')
    h = auth_headers(sub='member-ssf10')
    try:
        with patch.object(app_mod, '_user_music_dir', return_value=keep.parent):
            assert c.post('/api/prepare-zip', headers=h).status_code == 403
            with app_mod.user_zip_lock:
                app_mod.user_zip_state['member-ssf10'] = {
                    'zip_path': str(stale_zip), 'count': 1, 'size_mb': 0}
            assert c.get('/api/download-zip', headers=h).status_code == 403
        assert keep.exists()
    finally:
        with app_mod.user_zip_lock:
            app_mod.user_zip_state.pop('member-ssf10', None)
        keep.unlink(missing_ok=True)


def test_ssf10_member_zip_still_purges_member_library(flask_setup):
    c, music, _, _ = flask_setup
    h = auth_headers(sub='member-zip-ok', email='zipper@test.com')
    song = music / 'zipper' / 'Artist' / 'Album' / 'Song.mp3'
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b'ID3')
    r = c.post('/api/prepare-zip', headers=h)
    assert r.status_code == 200 and r.get_json()['count'] == 1
    r = c.get('/api/download-zip', headers=h)
    assert r.status_code == 200
    r.get_data()                     # consomme le stream → nettoyage post-export
    assert not (music / 'zipper').exists()
