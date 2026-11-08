"""
Flask route tests via test client — auth, library, path traversal, ZIP flow.
Covers: S-1, S-2, S-3, S-4, ST-1, ST-2, ST-3, ST-4, Z-3, Z-5, D-2/D-3/D-5, D-9.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

PROXY_SECRET = 'proxy-secret-for-tests'


@pytest.fixture(scope='module')
def flask_setup(tmp_path_factory):
    """Build the Flask app once with temp dirs. Returns (test_client, music_dir, temp_dir)."""
    music = tmp_path_factory.mktemp('music')
    temp  = tmp_path_factory.mktemp('temp')
    logs  = tmp_path_factory.mktemp('logs')
    cookies = tmp_path_factory.mktemp('cookies')
    state   = tmp_path_factory.mktemp('state')
    env_patch = {
        'SONGSURF_PROXY_SECRET': PROXY_SECRET,
        'DEV_MODE':           'false',
        'FLASK_SECRET_KEY':   'test-key',
        'YTDLP_COOKIES_DIR':  str(cookies),
        'SONGSURF_STATE_DIR': str(state),
    }

    with patch.dict(os.environ, env_patch):
        with patch('shutil.which', return_value=None):
            import app as app_mod
            # Override runtime directories after import
            app_mod.BASE_MUSIC_DIR = music
            app_mod.TEMP_DIR       = temp
            app_mod.LOG_DIR        = logs
            app_mod.COOKIES_DIR    = cookies
            app_mod.store          = app_mod.StateStore(state / 'songsurf.db')
            app_mod.SONGSURF_PROXY_SECRET = PROXY_SECRET
            app_mod.DEV_MODE = False
            app_mod.app.config['TESTING'] = True

            with app_mod.app.test_client() as c:
                yield c, music, temp, app_mod


def uid_for(sub):
    """UUID du portail factice, stable par pseudo (= nom du dossier utilisateur)."""
    return f'uid-0000-{sub}'


USER_DIR  = uid_for('user-abc')    # dossier de auth_headers() par défaut
ADMIN_DIR = uid_for('admin-xyz')   # dossier de admin_headers() par défaut


def auth_headers(role='member', sub='user-abc', uid=None):
    """Headers Caddy sends after the portal gate (forward_auth + proof)."""
    return {
        'X-Proxy-Token': PROXY_SECRET,
        'X-User-Name':   sub,
        'X-User-Role':   role,
        'X-User-Id':     uid if uid is not None else uid_for(sub),
    }


def admin_headers(sub='admin-xyz'):
    return auth_headers(role='admin', sub=sub)


_NETSCAPE = ('# Netscape HTTP Cookie File\n'
             '.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tvalue\n')


def give_cookies(app_mod, key=USER_DIR):
    """Écrit un fichier cookies pour la clé <key> (par défaut celle de auth_headers())."""
    f = app_mod.COOKIES_DIR / f'{key}.txt'
    f.write_text(_NETSCAPE)
    return f


# ── S-1: No X-Proxy-Token → rejected ─────────────────────────────────────────

def test_s1_no_proxy_token_rejected(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/me')
    assert r.status_code == 401


# ── S-2: Wrong X-Proxy-Token → rejected ──────────────────────────────────────

def test_s2_wrong_token_rejected(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/me', headers={**auth_headers(), 'X-Proxy-Token': 'wrong-secret'})
    assert r.status_code == 401


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
    r = c.get('/api/me', headers={**auth_headers(sub='admin-user'), 'X-User-Role': 'Admin'})
    assert r.status_code == 200
    assert r.get_json()['role'] == 'admin'


# ── SSF-03 : sans UUID du portail valide, pas de clé de stockage → refus ─────

def test_ssf03_missing_or_invalid_portal_id_rejected(flask_setup):
    c, *_ = flask_setup
    for uid in ('', '../../etc', 'court', 'a b c d e f g h'):
        r = c.get('/api/me', headers={**auth_headers(), 'X-User-Id': uid,
                                      'Accept': 'application/json'})
        assert r.status_code == 401, uid


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
    for sub in ('user-a', 'user-b'):
        song = music / uid_for(sub) / f'Art-{sub}' / 'Alb' / 'song.mp3'
        song.parent.mkdir(parents=True, exist_ok=True)
        song.write_bytes(b'mp3')

    r_a = c.get('/api/library', headers=auth_headers(sub='user-a')).get_json()
    r_b = c.get('/api/library', headers=auth_headers(sub='user-b')).get_json()
    assert r_a['success'] and r_b['success']
    assert [a['name'] for a in r_a['artists']] == ['Art-user-a']
    assert [a['name'] for a in r_b['artists']] == ['Art-user-b']


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
        _drain_queue(app_mod)   # ne pas polluer les autres tests


def test_d9_rejects_when_queue_full(flask_setup):
    c, _, _, app_mod = flask_setup
    give_cookies(app_mod)
    try:
        # Sature les jobs de l'utilisateur jusqu'à MAX_PENDING_JOBS
        for _ in range(app_mod.MAX_PENDING_JOBS):
            app_mod.store.enqueue_job(USER_DIR, [{'url': 'u'}])
        body = {'url': 'https://www.youtube.com/watch?v=abc', 'title': 'T', 'artist': 'A', 'album': 'B'}
        r = c.post('/api/download', json=body, headers=auth_headers(),
                   content_type='application/json')
        assert r.status_code == 429
        # La limite est par utilisateur : un autre membre peut encore empiler
        give_cookies(app_mod, uid_for('other-member'))
        r = c.post('/api/download', json=body, headers=auth_headers(sub='other-member'),
                   content_type='application/json')
        assert r.status_code == 200
    finally:
        _drain_queue(app_mod)


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

def test_user_music_dir_rejects_invalid_uid(flask_setup):
    _, _, _, app_mod = flask_setup
    for bad in ('../../etc/passwd', '..', '', 'short', 'a/b-cdefghij', 'x' * 65):
        with pytest.raises(ValueError, match='invalide'):
            app_mod._user_music_dir({'sub': 'x', 'uid': bad})


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
    album = music / USER_DIR / 'Artist' / 'AlbumTL'
    _make_tagged_mp3(album / 'b.mp3', title='Bee', track='2/2')
    _make_tagged_mp3(album / 'a.mp3', title='Aye')

    r = c.get('/api/library/album-tracks?folder_path=Artist/AlbumTL',
              headers=auth_headers())
    assert r.status_code == 200
    data = r.get_json()
    assert data['tracks'] == [
        {'path': 'Artist/AlbumTL/a.mp3', 'name': 'a.mp3', 'title': 'Aye', 'track_number': '',
         'artists': [], 'year': '', 'genres': []},
        {'path': 'Artist/AlbumTL/b.mp3', 'name': 'b.mp3', 'title': 'Bee', 'track_number': '2/2',
         'artists': [], 'year': '', 'genres': []},
    ]


def test_renumber_album_writes_in_order(flask_setup):
    c, music, _, app_mod = flask_setup
    album = music / ADMIN_DIR / 'Artist' / 'AlbumRN'
    _make_tagged_mp3(album / 'a.mp3')
    _make_tagged_mp3(album / 'b.mp3')

    with patch.object(app_mod, '_write_song_tags') as mock_write:
        r = c.post('/api/library/renumber-album',
                   json={'folder_path': 'Artist/AlbumRN',
                         'paths': ['Artist/AlbumRN/b.mp3', 'Artist/AlbumRN/a.mp3']},
                   headers=admin_headers(),
                   content_type='application/json')
    assert r.status_code == 200
    assert r.get_json() == {'success': True, 'total': 2}
    written = [(call.args[0].name, call.args[1]) for call in mock_write.call_args_list]
    assert written == [('b.mp3', {'track_number': '1/2'}),
                       ('a.mp3', {'track_number': '2/2'})]


def test_renumber_album_rejects_partial_paths(flask_setup):
    c, music, _, app_mod = flask_setup
    album = music / ADMIN_DIR / 'Artist' / 'AlbumPart'
    _make_tagged_mp3(album / 'a.mp3')
    _make_tagged_mp3(album / 'b.mp3')

    with patch.object(app_mod, '_write_song_tags') as mock_write:
        r = c.post('/api/library/renumber-album',
                   json={'folder_path': 'Artist/AlbumPart',
                         'paths': ['Artist/AlbumPart/a.mp3']},  # b.mp3 manquant
                   headers=admin_headers(),
                   content_type='application/json')
    assert r.status_code == 400
    mock_write.assert_not_called()


def test_renumber_album_rejects_foreign_path(flask_setup):
    c, music, _, app_mod = flask_setup
    album = music / ADMIN_DIR / 'Artist' / 'AlbumFor'
    _make_tagged_mp3(album / 'a.mp3')
    _make_tagged_mp3(music / ADMIN_DIR / 'Artist' / 'Autre' / 'x.mp3')

    r = c.post('/api/library/renumber-album',
               json={'folder_path': 'Artist/AlbumFor',
                     'paths': ['Artist/AlbumFor/a.mp3', 'Artist/Autre/x.mp3']},
               headers=admin_headers(),
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
    artist = music / ADMIN_DIR / 'ArtistG'
    _make_real_mp3(artist / 'Al1' / 'a.mp3')
    _make_real_mp3(artist / 'Al1' / 'b.mp3')
    _make_real_mp3(artist / 'Al2' / 'c.mp3')
    (artist / 'Al1' / 'cover.jpg').write_bytes(b'x')  # ignoré (pas un MP3)

    r = c.post('/api/library/set-artist-genre',
               json={'folder_path': 'ArtistG', 'genre': 'Rock; Pop'},
               headers=admin_headers(),
               content_type='application/json')
    assert r.status_code == 200
    data = r.get_json()
    assert data['updated'] == 3 and data['errors'] == []

    from mutagen.id3 import ID3
    for rel in ('Al1/a.mp3', 'Al1/b.mp3', 'Al2/c.mp3'):
        assert [str(t) for t in ID3(artist / rel)['TCON'].text] == ['Rock', 'Pop']


def test_set_artist_genre_requires_genre(flask_setup):
    c, music, _, app_mod = flask_setup
    _make_tagged_mp3(music / ADMIN_DIR / 'ArtistGE' / 'Al' / 'a.mp3')

    r = c.post('/api/library/set-artist-genre',
               json={'folder_path': 'ArtistGE', 'genre': '  '},
               headers=admin_headers(),
               content_type='application/json')
    assert r.status_code == 400


def test_set_artist_genre_rejects_music_root_and_escape(flask_setup):
    c, *_ = flask_setup
    for bad in ('.', '../autre'):
        r = c.post('/api/library/set-artist-genre',
                   json={'folder_path': bad, 'genre': 'Rock'},
                   headers=admin_headers(),
                   content_type='application/json')
        assert r.status_code == 400, bad


def test_me_returns_pseudo(flask_setup):
    c, *_ = flask_setup
    r = c.get('/api/me', headers=auth_headers(sub='Oliver.K', uid='3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f'))
    assert r.get_json()['pseudo'] == 'Oliver.K'   # pseudo exact, plus de dérivation
    assert r.get_json()['uid'] == '3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f'
    r = c.get('/api/me', headers=admin_headers())
    assert r.get_json()['pseudo'] == 'admin-xyz'


def test_album_status_counts_missing_tags(flask_setup):
    from mutagen.id3 import ID3, TCON, TDRC
    c, music, *_ = flask_setup
    artist = music / USER_DIR / 'ArtistST'
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


def test_ssf13_expert_tools_admin_only(flask_setup):
    """SSF-13 : audit iTunes, numérotation et genre de l'artiste = mode expert,
    réservé à l'admin (403 pour un membre, rien n'est écrit)."""
    c, music, _, app_mod = flask_setup
    _make_tagged_mp3(music / USER_DIR / 'ArtistEx' / 'Al' / 'a.mp3')
    member = auth_headers(role='member')
    with patch.object(app_mod, '_write_song_tags') as mock_write:
        calls = [
            c.get('/api/library/audit/artist?path=ArtistEx', headers=member),
            c.post('/api/library/audit/apply', json={'changes': [
                {'path': 'ArtistEx/Al/a.mp3', 'field': 'year', 'value': '2001'}]}, headers=member),
            c.post('/api/library/renumber-album', json={
                'folder_path': 'ArtistEx/Al', 'paths': ['ArtistEx/Al/a.mp3']}, headers=member),
            c.post('/api/library/set-artist-genre', json={
                'folder_path': 'ArtistEx', 'genre': 'Rock'}, headers=member),
        ]
    assert [r.status_code for r in calls] == [403] * 4
    assert all(r.get_json()['code'] == 'admin_only' for r in calls)
    mock_write.assert_not_called()
    # L'admin, lui, passe (404 : artiste absent de sa bibliothèque ; apply vide → 200)
    assert c.get('/api/library/audit/artist?path=Nope', headers=admin_headers()).status_code == 404
    assert c.post('/api/library/audit/apply', json={'changes': []},
                  headers=admin_headers()).status_code == 200


# ── SSF-13 : déplacement (tags), album entier, « À remplir », suppression ───

def _tags(path):
    from mutagen.id3 import ID3
    id3 = ID3(path)
    return {k: [str(v) for v in id3[k].text] for k in ('TPE1', 'TPE2', 'TALB', 'TDRC', 'TCON') if k in id3}


def _real_mp3_with(path, **frames):
    from mutagen.id3 import ID3
    import mutagen.id3 as m
    _make_real_mp3(path)
    id3 = ID3()
    for key, text in frames.items():
        id3[key] = getattr(m, key)(encoding=3, text=text)
    id3.save(path)


def test_ssf13_retarget_artists_keeps_featurings(flask_setup):
    *_, app_mod = flask_setup
    f = app_mod._retarget_artists
    assert f(['A', 'Feat'], 'A', 'B') == ['B', 'Feat']
    assert f(['A', 'Feat'], 'A', 'A') == ['A', 'Feat']            # même artiste : inchangé
    assert f(['Feat', 'A'], 'A', 'B') == ['Feat', 'B']             # ancien artiste remplacé là où il est
    assert f(['X', 'Feat'], 'A', 'B') == ['B', 'Feat']             # absent → le premier
    assert f(['B', 'A'], 'A', 'B') == ['B']                        # dédoublonné
    assert f([], 'A', 'B') == ['B']


def test_ssf13_move_song_keeps_featurings_and_sets_album_artist(flask_setup):
    c, music, *_ = flask_setup
    root = music / USER_DIR
    _real_mp3_with(root / 'Orel' / 'Al1' / 's.mp3', TPE1=['Orel', 'Stromae'], TPE2='Orel', TALB='Al1')
    (root / 'Justice' / 'Cross').mkdir(parents=True)
    r = c.post('/api/library/move', json={'source': 'Orel/Al1/s.mp3', 'target_folder': 'Justice/Cross'},
               headers=auth_headers())
    assert r.status_code == 200
    tags = _tags(root / 'Justice' / 'Cross' / 's.mp3')
    assert tags['TPE1'] == ['Justice', 'Stromae']
    assert tags['TPE2'] == ['Justice'] and tags['TALB'] == ['Cross']


def test_ssf13_move_song_same_artist_keeps_tpe1(flask_setup):
    c, music, *_ = flask_setup
    root = music / USER_DIR
    _real_mp3_with(root / 'Daft' / 'Disc' / 's.mp3', TPE1=['Pharrell', 'Daft'], TALB='Disc')
    (root / 'Daft' / 'RAM').mkdir(parents=True)
    r = c.post('/api/library/move', json={'source': 'Daft/Disc/s.mp3', 'target_folder': 'Daft/RAM'},
               headers=auth_headers())
    assert r.status_code == 200
    tags = _tags(root / 'Daft' / 'RAM' / 's.mp3')
    assert tags['TPE1'] == ['Pharrell', 'Daft'] and tags['TALB'] == ['RAM'] and tags['TPE2'] == ['Daft']


def test_ssf13_move_folder_retargets_artist(flask_setup):
    c, music, *_ = flask_setup
    root = music / USER_DIR
    _real_mp3_with(root / 'Old' / 'Alb' / 's.mp3', TPE1=['Old', 'Guest'], TPE2='Old', TALB='Alb')
    (root / 'New').mkdir(parents=True)
    _real_mp3_with(root / 'New' / 'Other' / 'x.mp3', TPE1='New')
    r = c.post('/api/library/move-folder', json={'folder_path': 'Old/Alb', 'new_parent': 'New'},
               headers=auth_headers())
    assert r.status_code == 200
    tags = _tags(root / 'New' / 'Alb' / 's.mp3')
    assert tags['TPE1'] == ['New', 'Guest'] and tags['TPE2'] == ['New']


def test_ssf13_album_tags_save_writes_all_and_renames(flask_setup):
    c, music, *_ = flask_setup
    root = music / USER_DIR
    for n in ('a', 'b'):
        _real_mp3_with(root / 'ArtAT' / 'Old name' / f'{n}.mp3', TALB='Old name')
    r = c.post('/api/library/album-tags/save', headers=auth_headers(), json={
        'folder_path': 'ArtAT/Old name', 'album': 'New: name', 'year': '2017', 'genre': 'Hip-Hop/Rap; French Rap'})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data['path'] == 'ArtAT/New name' and data['updated'] == 2 and data['errors'] == []
    assert not (root / 'ArtAT' / 'Old name').exists()
    for n in ('a', 'b'):
        tags = _tags(root / 'ArtAT' / 'New name' / f'{n}.mp3')
        assert tags['TALB'] == ['New name'] and tags['TDRC'] == ['2017']
        assert tags['TCON'] == ['Hip-Hop/Rap', 'French Rap']


def test_ssf13_album_tags_save_partial_and_errors(flask_setup):
    c, music, *_ = flask_setup
    root = music / USER_DIR
    _real_mp3_with(root / 'ArtAP' / 'Al' / 'a.mp3', TALB='Al', TCON='Rock')
    (root / 'ArtAP' / 'Taken').mkdir()
    h = auth_headers()
    # Année seule : genre et nom inchangés
    r = c.post('/api/library/album-tags/save', headers=h, json={'folder_path': 'ArtAP/Al', 'year': '1999'})
    assert r.status_code == 200 and r.get_json()['path'] == 'ArtAP/Al'
    assert _tags(root / 'ArtAP' / 'Al' / 'a.mp3')['TCON'] == ['Rock']
    assert c.post('/api/library/album-tags/save', headers=h,
                  json={'folder_path': 'ArtAP/Al', 'year': '99'}).status_code == 400
    r = c.post('/api/library/album-tags/save', headers=h, json={'folder_path': 'ArtAP/Al', 'album': 'Taken'})
    assert r.status_code == 409 and r.get_json()['code'] == 'album_exists'
    for bad in ('ArtAP', '.', '../x'):   # dossier artiste, racine, évasion
        assert c.post('/api/library/album-tags/save', headers=h,
                      json={'folder_path': bad, 'year': '2000'}).status_code == 400, bad
    assert c.post('/api/library/album-tags/save', headers=h,
                  json={'folder_path': 'ArtAP/Al', 'album': ' / '}).status_code == 400


def test_ssf13_todo_lists_incomplete_albums(flask_setup):
    c, *_ = flask_setup
    other = auth_headers(sub='todo-user')
    music = flask_setup[1] / uid_for('todo-user')
    _make_tagged_mp3(music / 'Art' / 'Complet' / 'a.mp3', title='A', track='1/1')
    from mutagen.id3 import ID3, TCON, TDRC
    f = music / 'Art' / 'Complet' / 'a.mp3'
    id3 = ID3(f); id3['TCON'] = TCON(encoding=3, text=['Pop']); id3['TDRC'] = TDRC(encoding=3, text='2001'); id3.save(f)
    _make_tagged_mp3(music / 'Art' / 'Trous' / 'b.mp3', title='B', track='1/1')
    r = c.get('/api/library/todo', headers=other)
    assert r.status_code == 200
    albums = r.get_json()['albums']
    assert [a['path'] for a in albums] == ['Art/Trous']
    assert albums[0]['artist'] == 'Art' and albums[0]['missing'] == {'genre': 1, 'year': 1, 'track_number': 0}
    # Le cache suit les écritures : une fois complété, l'album disparaît de la liste
    f = music / 'Art' / 'Trous' / 'b.mp3'
    id3 = ID3(f); id3['TCON'] = TCON(encoding=3, text=['Pop']); id3['TDRC'] = TDRC(encoding=3, text='2001'); id3.save(f)
    import os, time
    os.utime(f, ns=(time.time_ns(), time.time_ns() + 10_000_000))
    assert c.get('/api/library/todo', headers=other).get_json()['albums'] == []


def test_ssf13_delete_song_admin_only_and_cleans_empty_album(flask_setup):
    c, music, _, app_mod = flask_setup
    _make_tagged_mp3(music / USER_DIR / 'ArtDS' / 'Al' / 'a.mp3')
    assert c.post('/api/library/delete-song', json={'path': 'ArtDS/Al/a.mp3'},
                  headers=auth_headers()).status_code == 403
    assert (music / USER_DIR / 'ArtDS' / 'Al' / 'a.mp3').exists()

    root = music / ADMIN_DIR
    _make_tagged_mp3(root / 'ArtDS' / 'Al' / 'a.mp3')
    _make_tagged_mp3(root / 'ArtDS' / 'Al' / 'b.mp3')
    (root / 'ArtDS' / 'Al' / 'cover.jpg').write_bytes(b'x')
    r = c.post('/api/library/delete-song', json={'path': 'ArtDS/Al/a.mp3'}, headers=admin_headers())
    assert r.get_json() == {'success': True, 'removed_album': False}
    r = c.post('/api/library/delete-song', json={'path': 'ArtDS/Al/b.mp3'}, headers=admin_headers())
    assert r.get_json() == {'success': True, 'removed_album': True}
    assert not (root / 'ArtDS').exists()   # album (pochette comprise) puis artiste vide retirés
    for bad in ('../x.mp3', 'ArtDS/Al/nope.mp3'):
        assert c.post('/api/library/delete-song', json={'path': bad},
                      headers=admin_headers()).status_code in (400, 404), bad


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
    album = music / ADMIN_DIR / 'ArtistDel' / 'AlbumDel'
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
    assert not (music / ADMIN_DIR / 'ArtistDel').exists()


def test_delete_artist_folder_keeps_siblings(flask_setup):
    c, music, *_ = flask_setup
    artist = music / ADMIN_DIR / 'ArtistDel2'
    (artist / 'Album1').mkdir(parents=True)
    (artist / 'Album1' / 'a.mp3').write_bytes(b'mp3')
    other = music / ADMIN_DIR / 'ArtistKeep'
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
    (music / ADMIN_DIR).mkdir(exist_ok=True)
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
    album = music / USER_DIR / 'ArtistC' / 'AlbumFile'
    album.mkdir(parents=True)
    (album / 'cover.jpg').write_bytes(b'\xff\xd8\xff\xdbjpegdata')

    r = c.get('/api/library/folder-cover?folder_path=ArtistC/AlbumFile',
              headers=auth_headers())
    assert r.status_code == 200
    assert r.headers['Cache-Control'] == 'private, max-age=86400'


def test_folder_cover_apic_extraction_persists_cover_jpg(flask_setup):
    c, music, *_ = flask_setup
    album = music / USER_DIR / 'ArtistC' / 'AlbumApic'
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
    album = music / USER_DIR / 'ArtistC' / 'AlbumBare'
    _make_real_mp3(album / 'a.mp3')  # aucun APIC

    r = c.get('/api/library/folder-cover?folder_path=ArtistC/AlbumBare',
              headers=auth_headers())
    assert r.status_code == 204
    assert not (album / 'cover.jpg').exists()


def test_artist_picture_served_with_cache_header(flask_setup):
    c, music, *_ = flask_setup
    artist = music / USER_DIR / 'ArtistPic'
    artist.mkdir(parents=True)
    (artist / 'folder.jpg').write_bytes(b'\xff\xd8\xffjpeg')

    r = c.get('/api/library/artist-picture?folder_path=ArtistPic',
              headers=auth_headers())
    assert r.status_code == 200
    assert r.headers['Cache-Control'] == 'private, max-age=86400'


# ── SSF-01 : cookies par utilisateur, taille max, cloisonnement /api/status ───

def _drain_queue(app_mod):
    while (claimed := app_mod.store.claim_next()) is not None:
        app_mod.store.finish(claimed[0])
    with app_mod.queue_lock:
        app_mod.download_status.update(batch_active=False, batch_total=0, batch_done=0)


def test_ssf01_download_blocked_without_cookies(flask_setup):
    c, *_ = flask_setup
    for path, body in [
        ('/api/download', {'url': 'https://www.youtube.com/watch?v=abc', 'title': 'T'}),
        ('/api/download-playlist', {'playlist_metadata': {'songs': [{'url': 'u', 'title': 't'}]}}),
        ('/api/queue-direct', {'url': 'https://music.youtube.com/watch?v=abc'}),
        ('/api/preview', {'url': 'https://music.youtube.com/watch?v=abc'}),
        ('/api/extract', {'url': 'https://music.youtube.com/watch?v=abc'}),
    ]:
        r = c.post(path, json=body, headers=auth_headers(sub='nocookie'))
        assert r.status_code == 403, path
        data = r.get_json()
        assert data['code'] == 'cookies_missing'
        assert 'extension' in data['error']


def test_ssf01_no_fallback_on_admin_cookies(flask_setup):
    c, _, _, app_mod = flask_setup
    give_cookies(app_mod, ADMIN_DIR)
    r = c.post('/api/download', json={'url': 'https://www.youtube.com/watch?v=abc'},
               headers=auth_headers(sub='member2'))
    assert r.status_code == 403


def test_ssf01_cookies_update_is_per_user(flask_setup):
    c, _, _, app_mod = flask_setup
    r = c.post('/api/cookies/update', json={'cookies': _NETSCAPE},
               headers=auth_headers(sub='alice'))
    assert r.status_code == 200
    data = r.get_json()
    assert data['pseudo'] == 'alice' and data['count'] == 1
    f = app_mod.COOKIES_DIR / f"{uid_for('alice')}.txt"
    assert f.is_file()
    assert (f.stat().st_mode & 0o777) == 0o600
    # Un autre membre n'en profite pas
    assert not (app_mod.COOKIES_DIR / f"{uid_for('bob')}.txt").exists()
    r = c.get('/api/status', headers=auth_headers(sub='bob'))
    assert r.get_json()['cookies_present'] is False
    r = c.get('/api/status', headers=auth_headers(sub='alice'))
    assert r.get_json()['cookies_present'] is True


def test_ssf01_cookies_update_rejects_bad_format(flask_setup):
    c, *_ = flask_setup
    r = c.post('/api/cookies/update', json={'cookies': 'not a cookie file'},
               headers=auth_headers(sub='carol'))
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
    alice_key = uid_for('alice')
    with app_mod.queue_lock:
        app_mod._last_completed_by_user[alice_key] = {'file_path': '/secret/alice.mp3', 'timestamp': 't1'}
        app_mod._last_error_by_user[alice_key] = {'error': 'boom', 'timestamp': 't2'}
        app_mod.download_status['current_download'] = {
            'url': 'u', 'metadata': {'title': 'Secret'}, 'user_key': alice_key, 'user_pseudo': 'alice'}
    try:
        bob = c.get('/api/status', headers=auth_headers(sub='bob')).get_json()
        assert bob['last_completed'] is None
        assert bob['last_error'] is None
        assert bob['current_download'] is None
        assert bob['is_mine'] is False
        assert bob['worker']['owner'] is None and bob['worker']['current'] is None

        alice = c.get('/api/status', headers=auth_headers(sub='alice')).get_json()
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
    f = give_cookies(app_mod, uid_for('dave'))
    item = {'url': 'https://www.youtube.com/watch?v=abc',
            'metadata': {'artist': 'A', 'album': 'B', 'title': 'T'},
            'user_key': uid_for('dave'), 'user_pseudo': 'dave', 'user_role': 'member'}
    with patch.object(app_mod.downloader, 'download',
                      return_value={'success': False, 'error': 'x'}) as dl:
        app_mod._process_song(item)
    assert dl.call_args.kwargs['cookiefile'] == str(f.resolve())
    assert app_mod._last_error_by_user[uid_for('dave')]['error'] == 'x'
    app_mod._last_error_by_user.clear()


def test_ssf01_worker_fails_cleanly_when_cookies_removed(flask_setup):
    _, _, _, app_mod = flask_setup
    item = {'url': 'https://www.youtube.com/watch?v=abc',
            'metadata': {'artist': 'A', 'album': 'B', 'title': 'T'},
            'user_key': uid_for('erin'), 'user_pseudo': 'erin', 'user_role': 'member'}
    with patch.object(app_mod.downloader, 'download') as dl:
        app_mod._process_song(item)
    dl.assert_not_called()
    assert 'Cookies YouTube manquants' in app_mod._last_error_by_user[uid_for('erin')]['error']
    app_mod._last_error_by_user.clear()


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
        app_mod.download_status['current_download'] = {'metadata': meta, 'user_key': 'x'}
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

def _wait_zip(c, headers, timeout=5.0):
    """Polling de /api/zip-status jusqu'à ready/error (la construction est en thread)."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = c.get('/api/zip-status', headers=headers).get_json()
        if data['status'] in ('ready', 'error'):
            return data
        time.sleep(0.02)
    raise AssertionError('ZIP jamais prêt')


def test_ssf10_admin_zip_disabled(flask_setup):
    c, music, _, app_mod = flask_setup
    song = music / ADMIN_DIR / 'Artist' / 'Album' / 'Song.mp3'
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
    # La règle porte aussi sur le dossier : même un ZIP déjà préparé ne vide jamais
    # un dossier protégé (ici simulé comme point de montage, cas de la bibliothèque admin).
    c, music, _, app_mod = flask_setup
    keep = music / ADMIN_DIR / 'keep.mp3'
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_bytes(b'ID3')
    stale_zip = tmp_path / 'stale.zip'
    stale_zip.write_bytes(b'PK')
    sub = 'member-ssf10'
    h = auth_headers(sub=sub)
    try:
        with patch.object(app_mod, '_user_music_dir', return_value=keep.parent), \
             patch.object(app_mod, '_is_mount_point', side_effect=lambda p: p == keep.parent.resolve()):
            assert c.post('/api/prepare-zip', headers=h).status_code == 403
            app_mod.store.zip_set(uid_for(sub), status='ready', zip_path=str(stale_zip), total=1)
            assert c.get('/api/download-zip', headers=h).status_code == 403
        assert keep.exists()
    finally:
        app_mod.store.zip_delete(uid_for(sub))
        keep.unlink(missing_ok=True)


def test_ssf10_member_zip_still_purges_member_library(flask_setup):
    c, music, _, app_mod = flask_setup
    h = auth_headers(sub='zipper')
    lib = music / uid_for('zipper')
    song = lib / 'Artist' / 'Album' / 'Song.mp3'
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b'ID3')
    r = c.post('/api/prepare-zip', headers=h)
    assert r.status_code == 202 and r.get_json()['total'] == 1
    assert _wait_zip(c, h)['status'] == 'ready'
    r = c.get('/api/download-zip', headers=h)
    assert r.status_code == 200
    r.get_data()                     # consomme le stream → nettoyage post-export
    assert not lib.exists()
    assert c.get('/api/zip-status', headers=h).get_json()['status'] == 'idle'


# ── SSF-03 : file persistante round-robin, quota par utilisateur, worker, ZIP ──

def _queued_song(sub, title):
    return {'url': f'https://www.youtube.com/watch?v={title}',
            'metadata': {'artist': 'A', 'album': 'B', 'title': title},
            'user_key': uid_for(sub), 'user_pseudo': sub, 'user_role': 'member',
            'added_at': 't'}


def test_ssf03_worker_alternates_between_members(flask_setup):
    _, _, _, app_mod = flask_setup
    _drain_queue(app_mod)
    alice = {'uid': uid_for('alice'), 'sub': 'alice', 'role': 'member'}
    bob   = {'uid': uid_for('bob'),   'sub': 'bob',   'role': 'member'}
    app_mod._enqueue_job(alice, [_queued_song('alice', t) for t in ('a1', 'a2', 'a3')])
    app_mod._enqueue_job(bob,   [_queued_song('bob', 'b1')])
    seen = []
    with patch.object(app_mod, '_process_song', side_effect=lambda it: seen.append(it['metadata']['title'])):
        while app_mod._worker_step():
            pass
    assert seen == ['a1', 'b1', 'a2', 'a3']
    assert app_mod.store.pending_count() == 0
    _drain_queue(app_mod)


def test_ssf03_daily_quota_per_member_admin_unlimited(flask_setup):
    c, _, _, app_mod = flask_setup
    _drain_queue(app_mod)
    today = app_mod._today()
    for sub in ('quota-a', 'quota-b'):
        give_cookies(app_mod, uid_for(sub))
    give_cookies(app_mod, ADMIN_DIR)
    body = {'url': 'https://www.youtube.com/watch?v=abc', 'title': 'T', 'artist': 'A', 'album': 'B'}
    try:
        with patch.object(app_mod, 'DAILY_DOWNLOAD_LIMIT', 2):
            app_mod.store.daily_increment(uid_for('quota-a'), today)
            app_mod.store.daily_increment(uid_for('quota-a'), today)
            app_mod.store.daily_increment(ADMIN_DIR, today)
            app_mod.store.daily_increment(ADMIN_DIR, today)
            r = c.post('/api/download', json=body, headers=auth_headers(sub='quota-a'))
            assert r.status_code == 429 and r.get_json()['code'] == 'daily_limit'
            r = c.post('/api/queue-direct', json={'url': body['url']}, headers=auth_headers(sub='quota-a'))
            assert r.status_code == 429                      # l'extension aussi
            assert c.post('/api/download', json=body, headers=auth_headers(sub='quota-b')).status_code == 200
            assert c.post('/api/download', json=body, headers=admin_headers()).status_code == 200
            st = c.get('/api/status', headers=auth_headers(sub='quota-a')).get_json()
            assert st['daily_count'] == 2 and st['daily_limit'] == 2
            assert c.get('/api/status', headers=admin_headers()).get_json()['daily_limit'] == 0
    finally:
        _drain_queue(app_mod)


def test_ssf03_status_tells_who_uses_the_worker(flask_setup):
    c, _, _, app_mod = flask_setup
    _drain_queue(app_mod)
    bob = {'uid': uid_for('bob'), 'sub': 'bob', 'role': 'member'}
    app_mod._enqueue_job(bob, [_queued_song('bob', 'b1')])
    with app_mod.queue_lock:
        app_mod.download_status['in_progress'] = True
        app_mod.download_status['current_download'] = {
            'url': 'u', 'metadata': {'artist': 'Art', 'title': 'Secret'},
            'user_key': uid_for('alice'), 'user_pseudo': 'alice'}
    try:
        with patch.object(app_mod.downloader, 'get_progress', return_value={'phase': 'downloading', 'percent': 10}):
            member = c.get('/api/status', headers=auth_headers(sub='bob')).get_json()
            admin  = c.get('/api/status', headers=admin_headers()).get_json()
            idle   = c.get('/api/status', headers=auth_headers(sub='carol')).get_json()
        # Membre : « un autre membre », le titre en cours + 0 titre avant le sien
        assert member['is_mine'] is False and member['current_download'] is None
        assert member['worker'] == {'songs_before_mine': 1, 'owner': None, 'current': None}
        assert [p['title'] for p in member['pending']] == ['b1']
        # Admin : pseudo + titre en cours
        assert admin['worker']['owner'] == 'alice'
        assert admin['worker']['current'] == {'artist': 'Art', 'title': 'Secret'}
        assert admin['current_download'] is None
        # Membre sans titre en file : rien à attendre
        assert idle['worker']['songs_before_mine'] is None and idle['pending'] == []
    finally:
        with app_mod.queue_lock:
            app_mod.download_status['in_progress'] = False
            app_mod.download_status['current_download'] = None
        _drain_queue(app_mod)


def test_ssf16_proof_without_identity_gets_nothing(flask_setup):
    # Plus de sonde du Watcher (SSF-16) : la preuve seule n'ouvre pas /api/status.
    c, *_ = flask_setup
    r = c.get('/api/status', headers={'X-Proxy-Token': PROXY_SECRET, 'Accept': 'application/json'})
    assert r.status_code == 401


def test_ssf03_owner_file_holds_pseudo(flask_setup):
    c, music, _, _ = flask_setup
    uid = '9b1d6c2e-0f4a-4c3b-8e7d-5a6b7c8d9e0f'
    c.get('/api/library', headers=auth_headers(sub='Zoe.M', uid=uid))
    owner = music / uid / '.owner'
    assert owner.read_text(encoding='utf-8') == 'Zoe.M\n'
    assert c.get('/api/library', headers=auth_headers(sub='Zoe.M', uid=uid)).get_json()['artists'] == []


def test_ssf03_zip_status_idle_when_ready_file_vanished(flask_setup, tmp_path):
    c, _, _, app_mod = flask_setup
    key = uid_for('ghost')
    app_mod.store.zip_set(key, status='ready', zip_path=str(tmp_path / 'gone.zip'), total=1)
    r = c.get('/api/zip-status', headers=auth_headers(sub='ghost')).get_json()
    assert r['status'] == 'idle'
    assert app_mod.store.zip_get(key) is None


def test_ssf03_zip_build_survives_as_ready(flask_setup):
    c, music, _, app_mod = flask_setup
    h = auth_headers(sub='keeper')
    song = music / uid_for('keeper') / 'Art' / 'Alb' / 'Song.mp3'
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b'ID3')
    try:
        assert c.post('/api/prepare-zip', headers=h).status_code == 202
        ready = _wait_zip(c, h)
        assert ready['status'] == 'ready' and ready['count'] == 1
        assert ready['download_url'] == '/api/download-zip'
        assert 'zip_path' not in ready                    # jamais le chemin serveur
        # Un 2e prepare pendant que c'est prêt relance une construction propre
        assert c.post('/api/prepare-zip', headers=h).status_code == 202
        assert _wait_zip(c, h)['status'] == 'ready'
    finally:
        app_mod._zip_path(uid_for('keeper')).unlink(missing_ok=True)
        app_mod.store.zip_delete(uid_for('keeper'))


def test_ssf03_progress_reset_when_a_song_starts(flask_setup):
    # Le titre précédent laisse « completed / 100 % » : si on passe en cours sans
    # remettre à zéro, /api/status annonce le nouveau titre fini (bond de la barre).
    _, _, _, app_mod = flask_setup
    give_cookies(app_mod, uid_for('prog'))
    app_mod.downloader.progress.phase = 'completed'
    app_mod.downloader.progress.percent = 100
    seen = {}

    def fake_download(*_a, **_k):
        seen.update(app_mod.downloader.get_progress())
        return {'success': False, 'error': 'stop'}

    with patch.object(app_mod.downloader, 'download', side_effect=fake_download):
        app_mod._process_song(_queued_song('prog', 'p1'))
    assert seen['phase'] == 'idle' and seen['percent'] == 0
    app_mod._last_error_by_user.clear()


# ── SSF-14 : export ZIP interrompu → bibliothèque conservée ───────────────────

def test_ssf14_interrupted_zip_keeps_library_and_ready_zip(flask_setup):
    import os as _os
    c, music, _, app_mod = flask_setup
    h = auth_headers(sub='mobile')
    lib = music / uid_for('mobile')
    song = lib / 'Art' / 'Alb' / 'Song.mp3'
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(_os.urandom(300_000))           # incompressible → plusieurs blocs de 64 Ko
    try:
        assert c.post('/api/prepare-zip', headers=h).status_code == 202
        assert _wait_zip(c, h)['status'] == 'ready'
        r = c.get('/api/download-zip', headers=h, buffered=False)
        assert r.status_code == 200
        next(iter(r.response))                         # un seul bloc reçu…
        r.close()                                      # … puis connexion coupée
        assert song.is_file()                          # bibliothèque intacte
        assert c.get('/api/zip-status', headers=h).get_json()['status'] == 'ready'
        # Nouvelle tentative complète : là seulement, la bibliothèque est vidée
        r = c.get('/api/download-zip', headers=h)
        r.get_data()
        assert not lib.exists()
    finally:
        app_mod._zip_path(uid_for('mobile')).unlink(missing_ok=True)
        app_mod.store.zip_delete(uid_for('mobile'))


# ── Journal des téléchargements (admin) : limite, historique complet ─────────

def _write_dl_log(app_mod, n):
    lines = [f'2026-10-{(i % 28) + 1:02d} 12:00:00 | alice | Artiste {i % 3} | Album {i % 5} | Titre {i}'
             for i in range(n)]
    (app_mod.LOG_DIR / 'downloads.log').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def test_dl_logs_limit_all_returns_full_history(flask_setup):
    c, _, _, app_mod = flask_setup
    _write_dl_log(app_mod, 620)
    r = c.get('/api/admin/dl-logs?limit=all', headers=admin_headers())
    d = r.get_json()
    assert r.status_code == 200 and d['total'] == 620 and len(d['entries']) == 620
    assert d['entries'][0]['title'] == 'Titre 619'  # plus récent d'abord


def test_dl_logs_limit_capped_and_lenient(flask_setup):
    c, _, _, app_mod = flask_setup
    _write_dl_log(app_mod, 620)
    assert len(c.get('/api/admin/dl-logs?limit=9999', headers=admin_headers()).get_json()['entries']) == 500
    r = c.get('/api/admin/dl-logs?limit=abc', headers=admin_headers())
    assert r.status_code == 200 and len(r.get_json()['entries']) == 100


def test_dl_logs_admin_only(flask_setup):
    c, *_ = flask_setup
    assert c.get('/api/admin/dl-logs?limit=all', headers=auth_headers()).status_code == 403


def test_ssf13_spa_pages_served_with_auth(flask_setup, tmp_path):
    """/library et /metadata rendent l'appli (rechargement sur mobile), derrière l'auth."""
    c, _, _, app_mod = flask_setup
    build = tmp_path / 'build'
    build.mkdir()
    (build / 'index.html').write_text('<html>spa</html>')
    with patch.object(app_mod, '_FRONTEND_BUILD', build):
        for route in ('/library', '/metadata'):
            r = c.get(route)                       # sans identité : jamais l'appli
            assert r.status_code == 401 and b'spa' not in r.data, route
            r = c.get(route, headers=auth_headers())
            assert r.status_code == 200 and b'spa' in r.data, route


def test_ssf13_song_percent_moves_smoothly_and_never_goes_back(flask_setup):
    _, _, _, app_mod = flask_setup
    sp = app_mod._song_percent
    # Conversion longue : l'avancement suit le temps au lieu de rester figé
    assert sp('converting', 50, 2, 20) == 30.0          # plancher de la conversion
    assert 40 < sp('converting', 50, 10, 20) < 50
    assert sp('converting', 50, 1000, 20) == 92.0       # plafond tant que FFmpeg tourne
    assert sp('downloading', 100, 0, 20) == 30.0        # vrai avancement du téléchargement
    assert sp('downloading', 0, 100, 20) == 45.0        # plafond du téléchargement
    assert sp('organizing', 0, 0, 20) == 90.0
    assert sp('completed', 0, 0, 20) == 100.0
    # Plus long que prévu : approche lente de 99 %, sans jamais l'atteindre
    assert 90 < sp('organizing', 0, 30, 20) < 99
    # Monotone dans le temps et quand la phase avance
    steps = [('downloading', 0, 0), ('downloading', 60, 2), ('downloading', 100, 3), ('converting', 100, 3),
             ('converting', 100, 12), ('converting', 100, 25), ('organizing', 100, 25), ('organizing', 100, 40),
             ('completed', 100, 41)]
    values = [sp(phase, raw, t, 20) for phase, raw, t in steps]
    assert values == sorted(values)


def test_ssf13_song_timing_is_learned_per_audio_second(flask_setup):
    _, _, _, app_mod = flask_setup
    for key in ('song_rate', 'song_secs'):
        app_mod.store.meta_set(key, '0')                 # 0 = valeur par défaut
    assert app_mod._expected_song_seconds(0) == app_mod.SONG_SECS_DEFAULT
    assert app_mod._expected_song_seconds(200) == pytest.approx(200 * app_mod.SONG_RATE_DEFAULT)
    app_mod._learn_song_timing(40, 200)                  # 0,2 s par s d'audio
    rate = 0.08 + 0.3 * (0.2 - 0.08)
    assert app_mod._expected_song_seconds(200) == pytest.approx(200 * rate, rel=1e-3)
    assert app_mod._expected_song_seconds('?') == pytest.approx(20 + 0.3 * (40 - 20), rel=1e-3)
    for key in ('song_rate', 'song_secs'):
        app_mod.store.meta_set(key, '0')


def test_ssf13_status_has_one_progress_line_per_album(flask_setup):
    c, _, _, app_mod = flask_setup
    _drain_queue(app_mod)
    bob = {'uid': uid_for('bob'), 'sub': 'bob', 'role': 'member'}
    album = [_queued_song('bob', f'b{i}') for i in range(3)]
    for song in album:
        song['metadata']['album'] = 'Disque'
    app_mod._enqueue_job(bob, album)
    app_mod._enqueue_job(bob, [_queued_song('bob', 'solo')])
    claimed = app_mod.store.claim_next()                 # b0 en cours
    with app_mod.queue_lock:
        app_mod.download_status['in_progress'] = True
        app_mod.download_status['current_download'] = {
            'url': 'u', 'metadata': claimed[1]['metadata'], 'user_key': uid_for('bob'), 'user_pseudo': 'bob'}
    app_mod._song_clock.update(started=app_mod.time.monotonic() - 10, expected=20.0)
    try:
        with patch.object(app_mod.downloader, 'get_progress', return_value={'phase': 'converting', 'percent': 50}):
            st = c.get('/api/status', headers=auth_headers(sub='bob')).get_json()
            other = c.get('/api/status', headers=auth_headers(sub='carol')).get_json()
        assert 40 < st['current_percent'] < 50              # plus de palier figé à 55 %
        assert [(j['album'], j['total'], j['remaining'], j['active']) for j in st['jobs']] == [
            ('Disque', 3, 3, True), (st['jobs'][1]['album'], 1, 1, False)]
        assert other['jobs'] == []                          # jamais la file d'un autre membre
    finally:
        with app_mod.queue_lock:
            app_mod.download_status['in_progress'] = False
            app_mod.download_status['current_download'] = None
        app_mod.store.finish(claimed[0])
        _drain_queue(app_mod)


def test_ssf13_queued_items_keep_song_duration(flask_setup):
    c, _, _, app_mod = flask_setup
    _drain_queue(app_mod)
    give_cookies(app_mod, uid_for('dur'))
    try:
        r = c.post('/api/download-playlist', headers=auth_headers(sub='dur'), json={'playlist_metadata': {
            'title': 'A', 'artist': 'X', 'songs': [
                {'url': 'https://www.youtube.com/watch?v=aaaaaaaaaaa', 'title': 't1', 'duration': 181},
                {'url': 'https://www.youtube.com/watch?v=bbbbbbbbbbb', 'title': 't2'}]}})
        assert r.status_code == 200
        items = []
        while (claimed := app_mod.store.claim_next()) is not None:
            items.append(claimed[1])
            app_mod.store.finish(claimed[0])
        assert [i['duration'] for i in items] == [181, 0]
        assert app_mod._duration('12.7') == 12 and app_mod._duration('abc') == 0
    finally:
        _drain_queue(app_mod)
