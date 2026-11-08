"""
Porte du portail (AUTH-09), vérifiée par SongSurf lui-même depuis le retrait du
Watcher (SSF-16) : Caddy envoie l'identité (X-User-Name / X-User-Role / X-User-Id)
avec la preuve X-Proxy-Token. CORS limité à l'extension, /logout vers le portail.
Covers: W-14 → W-18, W-22 → W-24 (ex-Watcher), SSF-01 CORS.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import pytest
from unittest.mock import patch

with patch('shutil.which', return_value=None):
    import app as app_mod

_PROXY_SECRET = 'proxy-secret-for-tests'
_UID = '4fac893e-0000-4000-8000-000000000001'
_EXT_ORIGIN = f'chrome-extension://{app_mod.SONGSURF_EXTENSION_ID}'


def _gate_headers(**overrides):
    h = {
        'X-Proxy-Token': _PROXY_SECRET,
        'X-User-Name':   'Revo',
        'X-User-Role':   'Admin',
        'X-User-Id':     _UID,
    }
    h.update(overrides)
    return {k: v for k, v in h.items() if v is not None}


@pytest.fixture()
def gate(monkeypatch):
    monkeypatch.setattr(app_mod, 'DEV_MODE', False)
    monkeypatch.setattr(app_mod, 'SONGSURF_PROXY_SECRET', _PROXY_SECRET)
    monkeypatch.setattr(app_mod, 'REVAUTH_HOME_URL', 'https://portal.example/home/friend')
    app_mod.app.config['TESTING'] = True
    return monkeypatch


@pytest.fixture()
def client(gate):
    return app_mod.app.test_client()


def _user_for(headers=None, cookies=None):
    environ = {}
    if cookies:
        environ['HTTP_COOKIE'] = '; '.join(f'{k}={v}' for k, v in cookies.items())
    with app_mod.app.test_request_context('/', headers=headers or {}, environ_base=environ):
        return app_mod._get_current_user()


# ── W-14 : preuve valide → identité du portail ────────────────────────────────

def test_w14_valid_proof_gives_portal_identity(gate):
    assert _user_for(_gate_headers()) == {
        'sub':   'Revo',    # pseudo exact : affichage, logs, .owner
        'uid':   _UID,      # UUID du portail : clé de stockage
        'role':  'admin',   # minuscules
    }


# ── W-15 : preuve absente ou fausse → X-User-* ignorés ────────────────────────

@pytest.mark.parametrize('proof', [None, '', 'wrong-secret', _PROXY_SECRET + 'x', 'é'])
def test_w15_missing_or_bad_proof_ignores_identity_headers(gate, proof):
    assert _user_for(_gate_headers(**{'X-Proxy-Token': proof})) is None


def test_w15_bad_proof_is_logged(gate, caplog):
    _user_for(_gate_headers(**{'X-Proxy-Token': 'forged'}))
    assert 'X-Proxy-Token invalide' in caplog.text


# ── W-16 : secret non configuré → jamais d'identité ───────────────────────────

@pytest.mark.parametrize('proof', ['', 'anything'])
def test_w16_no_secret_configured_never_trusts_headers(gate, proof):
    gate.setattr(app_mod, 'SONGSURF_PROXY_SECRET', '')
    assert _user_for(_gate_headers(**{'X-Proxy-Token': proof})) is None


# ── W-17 : identité incomplète → refusée ──────────────────────────────────────

@pytest.mark.parametrize('missing', ['X-User-Name', 'X-User-Role'])
def test_w17_incomplete_identity_rejected(gate, missing):
    assert _user_for(_gate_headers(**{missing: None})) is None


def test_w17_blank_name_rejected(gate):
    assert _user_for(_gate_headers(**{'X-User-Name': '   '})) is None


def test_w17_missing_portal_uuid_is_refused_on_routes(client):
    r = client.get('/api/me', headers={**_gate_headers(**{'X-User-Id': None}),
                                       'Accept': 'application/json'})
    assert r.status_code == 401


# ── W-18 : sans preuve → anonyme ──────────────────────────────────────────────

def test_w18_old_jwt_cookie_is_ignored(gate):
    assert _user_for(cookies={'access_token': 'eyJhbGciOiJIUzI1NiJ9.e30.x'}) is None


def test_w18_old_watcher_headers_are_ignored(client):
    # Ancien contrat Watcher → SongSurf (SSF-16) : n'ouvre plus rien.
    r = client.get('/api/me', headers={'X-Watcher-Token': 'anything', 'X-User-Id': 'Revo',
                                       'X-User-Role': 'admin', 'X-User-Portal-Id': _UID,
                                       'Accept': 'application/json'})
    assert r.status_code == 401


def test_w18_valid_proof_opens_the_api(client):
    r = client.get('/api/me', headers=_gate_headers())
    assert r.status_code == 200
    assert r.get_json()['pseudo'] == 'Revo'


# ── W-22 : requête anonyme → jamais de redirection (c'est le rôle de Caddy) ───

def test_w22_anonymous_page_says_use_the_portal(client):
    r = client.get('/', headers=_gate_headers(**{'X-Proxy-Token': None}))
    assert r.status_code == 401
    body = r.get_data(as_text=True)
    assert 'Passe par le portail' in body
    assert 'https://portal.example/home/friend' in body


@pytest.mark.parametrize('headers', [
    {'Accept': 'application/json'},
    {'Origin': _EXT_ORIGIN},
])
def test_w22_anonymous_api_and_extension_get_json_401(client, headers):
    r = client.post('/api/queue-direct', headers=headers)
    assert r.status_code == 401
    assert r.get_json()['success'] is False


def test_w22_token_handoff_is_gone(client):
    r = client.get('/?token=eyJhbGciOiJIUzI1NiJ9.e30.x')
    assert r.status_code == 401
    assert 'Set-Cookie' not in r.headers


# ── W-23 : secret absent → service verrouillé ─────────────────────────────────

def test_w23_no_secret_locks_the_service(client, gate):
    gate.setattr(app_mod, 'SONGSURF_PROXY_SECRET', '')
    assert client.get('/', headers=_gate_headers()).status_code == 401


# ── W-24 : /logout → espace membre du portail, sans cookie à effacer ──────────

def test_w24_logout_redirects_to_portal_without_cookie(client):
    r = client.get('/logout')
    assert r.status_code == 302
    assert r.headers['Location'] == 'https://portal.example/home/friend'
    assert 'Set-Cookie' not in r.headers


# ── DEV_MODE : utilisateur dev local, sans preuve ─────────────────────────────

def test_dev_mode_gives_local_admin(gate):
    gate.setattr(app_mod, 'DEV_MODE', True)
    user = _user_for()
    assert user['role'] == 'admin' and user['sub'] == 'dev'


def test_dev_mode_stores_like_production(gate, tmp_path):
    gate.setattr(app_mod, 'DEV_MODE', True)
    gate.setattr(app_mod, 'BASE_MUSIC_DIR', tmp_path)
    assert app_mod._user_music_dir(_user_for()) == tmp_path.resolve() / 'dev-user-local'


# ── SSF-01 : CORS limité à l'extension SongSurf Clip ──────────────────────────

def test_cors_extension_id_matches_manifest():
    import base64, hashlib, json
    manifest = os.path.join(os.path.dirname(__file__), '..', '..', 'chrome-extension', 'manifest.json')
    with open(manifest, encoding='utf-8') as f:
        key = base64.b64decode(json.load(f)['key'])
    ext_id = ''.join(chr(ord('a') + int(c, 16)) for c in hashlib.sha256(key).hexdigest()[:32])
    assert ext_id == app_mod.SONGSURF_EXTENSION_ID


def test_cors_preflight_allows_songsurf_extension(client):
    r = client.options('/api/queue-direct', headers={'Origin': _EXT_ORIGIN})
    assert r.status_code == 204
    assert r.headers['Access-Control-Allow-Origin'] == _EXT_ORIGIN
    assert r.headers['Access-Control-Allow-Credentials'] == 'true'


def test_cors_headers_on_extension_responses(client):
    r = client.get('/ping', headers={'Origin': _EXT_ORIGIN})
    assert r.headers['Access-Control-Allow-Origin'] == _EXT_ORIGIN
    r = client.post('/api/queue-direct', headers={'Origin': _EXT_ORIGIN})
    assert r.status_code == 401   # le navigateur doit pouvoir lire le refus
    assert r.headers['Access-Control-Allow-Origin'] == _EXT_ORIGIN


@pytest.mark.parametrize('origin', [
    'null',
    'chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'https://evil.com',
])
def test_cors_rejects_other_origins(client, origin):
    r = client.options('/api/queue-direct', headers={'Origin': origin})
    assert r.status_code == 403
    assert 'Access-Control-Allow-Origin' not in r.headers
    r = client.get('/ping', headers={'Origin': origin})
    assert 'Access-Control-Allow-Origin' not in r.headers
