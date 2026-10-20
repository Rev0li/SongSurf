"""
Tests porte du portail (AUTH-09) : identité posée par Caddy avec la preuve
X-Proxy-Token (SSF-11), seul mode d'accès en prod depuis le retrait du JWT (SSF-12).
Covers: W-14 → W-19, W-22 → W-24.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'watcher'))

import pytest
import watcher

_PROXY_SECRET = 'proxy-secret-for-tests'


def _gate_headers(**overrides):
    h = {
        'X-Proxy-Token': _PROXY_SECRET,
        'X-User-Name':   'Revo',
        'X-User-Role':   'Admin',
        'X-User-Id':     '4fac893e-0000-4000-8000-000000000001',
    }
    h.update(overrides)
    return {k: v for k, v in h.items() if v is not None}


@pytest.fixture()
def gate(monkeypatch):
    monkeypatch.setattr(watcher, 'DEV_MODE', False)
    monkeypatch.setattr(watcher, 'SONGSURF_PROXY_SECRET', _PROXY_SECRET)
    monkeypatch.setattr(watcher, 'REVAUTH_HOME_URL', 'https://portal.example/home/friend')
    return monkeypatch


def _user_for(headers=None, cookies=None):
    environ = {}
    if cookies:
        environ['HTTP_COOKIE'] = '; '.join(f'{k}={v}' for k, v in cookies.items())
    with watcher.app.test_request_context('/', headers=headers or {}, environ_base=environ):
        return watcher._get_user_from_request()


# ── W-14 : preuve valide → identité du portail ────────────────────────────────

def test_w14_valid_proof_gives_portal_identity(gate):
    user = _user_for(_gate_headers())
    assert user == {
        'sub':   'Revo',            # pseudo exact : identité SongSurf (dossiers, événements)
        'role':  'admin',           # minuscules
        'email': '',
        'uid':   '4fac893e-0000-4000-8000-000000000001',
    }


# ── W-15 : preuve absente ou fausse → X-User-* ignorés ────────────────────────

@pytest.mark.parametrize('proof', [None, '', 'wrong-secret', _PROXY_SECRET + 'x', 'é'])
def test_w15_missing_or_bad_proof_ignores_identity_headers(gate, proof):
    assert _user_for(_gate_headers(**{'X-Proxy-Token': proof})) is None


def test_w15_bad_proof_is_logged(gate, caplog):
    _user_for(_gate_headers(**{'X-Proxy-Token': 'forged'}))
    assert 'X-Proxy-Token invalide' in caplog.text


# ── W-16 : secret non configuré → porte ignorée ───────────────────────────────

@pytest.mark.parametrize('proof', ['', 'anything'])
def test_w16_no_secret_configured_never_trusts_headers(gate, proof):
    gate.setattr(watcher, 'SONGSURF_PROXY_SECRET', '')
    assert _user_for(_gate_headers(**{'X-Proxy-Token': proof})) is None


# ── W-17 : identité incomplète → refusée ──────────────────────────────────────

@pytest.mark.parametrize('missing', ['X-User-Name', 'X-User-Role'])
def test_w17_incomplete_identity_rejected(gate, missing):
    assert _user_for(_gate_headers(**{missing: None})) is None


def test_w17_blank_name_rejected(gate):
    assert _user_for(_gate_headers(**{'X-User-Name': '   '})) is None


# ── W-18 : sans preuve → anonyme (le JWT n'existe plus, SSF-12) ──────────────

def test_w18_old_jwt_cookie_is_ignored(gate):
    assert _user_for(cookies={'access_token': 'eyJhbGciOiJIUzI1NiJ9.e30.x'}) is None


def test_w18_forged_headers_without_proof_are_anonymous_on_routes(gate):
    c = watcher.app.test_client()
    r = c.get('/watcher/inactivity-status', headers=_gate_headers(**{'X-Proxy-Token': 'nope'}))
    assert r.status_code == 401
    r = c.post('/watcher/keepalive', headers=_gate_headers(**{'X-Proxy-Token': None}))
    assert r.status_code == 401


# ── W-19 : en-têtes relayés à SongSurf ────────────────────────────────────────

class _FakeResp:
    status_code = 200
    headers = {'Content-Type': 'application/json'}

    def iter_content(self, chunk_size=8192):
        yield b'{}'


def test_w19_proxy_forwards_own_identity_and_drops_client_ones(gate):
    sent = {}

    def fake_request(**kwargs):
        sent.update(kwargs['headers'])
        return _FakeResp()

    gate.setattr(watcher, '_songsurf_running', lambda: True)
    gate.setattr(watcher, '_candidate_target_urls', lambda: ['http://songsurf.test'])
    gate.setattr(watcher.req_lib, 'request', fake_request)

    c = watcher.app.test_client()
    r = c.get('/api/status', headers=_gate_headers(**{'X-User-Email': 'forged@evil',
                                                      'X-Watcher-Token': 'forged'}))
    assert r.status_code == 200
    assert sent['X-Watcher-Token'] == watcher.WATCHER_SECRET
    assert sent['X-User-Id'] == 'Revo'
    assert sent['X-User-Role'] == 'admin'
    assert sent['X-User-Email'] == ''
    assert sent['X-User-Portal-Id'] == '4fac893e-0000-4000-8000-000000000001'
    lowered = {k.lower() for k in sent}
    assert 'x-proxy-token' not in lowered          # la preuve reste au Watcher
    assert 'x-user-name' not in lowered


# ── W-22 : requête anonyme → jamais de redirection (c'est le rôle de Caddy) ───

def test_w22_anonymous_page_says_use_the_portal(gate):
    r = watcher.app.test_client().get('/', headers=_gate_headers(**{'X-Proxy-Token': None}))
    assert r.status_code == 401
    body = r.get_data(as_text=True)
    assert 'Passe par le portail' in body
    assert 'https://portal.example/home/friend' in body


@pytest.mark.parametrize('headers', [
    {'Accept': 'application/json'},
    {'Origin': f'chrome-extension://{watcher.SONGSURF_EXTENSION_ID}'},
])
def test_w22_anonymous_api_and_extension_get_json_401(gate, headers):
    r = watcher.app.test_client().post('/api/queue-direct', headers=headers)
    assert r.status_code == 401
    assert r.get_json() == {'ok': False, 'error': 'unauthenticated'}


def test_w22_token_handoff_is_gone(gate):
    r = watcher.app.test_client().get('/?token=eyJhbGciOiJIUzI1NiJ9.e30.x')
    assert r.status_code == 401
    assert 'Set-Cookie' not in r.headers


# ── W-23 : secret absent → service verrouillé ─────────────────────────────────

def test_w23_no_secret_locks_the_service(gate):
    gate.setattr(watcher, 'SONGSURF_PROXY_SECRET', '')
    r = watcher.app.test_client().get('/', headers=_gate_headers())
    assert r.status_code == 401


# ── W-24 : /logout → espace membre du portail, sans cookie à effacer ──────────

def test_w24_logout_redirects_to_portal_without_cookie(gate):
    gate.setattr(watcher, '_songsurf_running', lambda: False)
    r = watcher.app.test_client().get('/logout')
    assert r.status_code == 302
    assert r.headers['Location'] == 'https://portal.example/home/friend'
    assert 'Set-Cookie' not in r.headers
