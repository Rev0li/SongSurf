"""
Tests for the Watcher loading page (/watcher/loading) — open-redirect guard,
robust _r parsing, JS polling of /watcher/ready (no blind meta-refresh).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'watcher'))

import pytest
import watcher


@pytest.fixture()
def client():
    watcher.app.config['TESTING'] = True
    return watcher.app.test_client()


# ── _safe_int ─────────────────────────────────────────────────────────────────

def test_safe_int_parses_valid():
    assert watcher._safe_int('7') == 7


def test_safe_int_falls_back_on_garbage():
    assert watcher._safe_int('abc') == 0
    assert watcher._safe_int(None) == 0
    assert watcher._safe_int('', default=3) == 3


# ── Robustesse _r ─────────────────────────────────────────────────────────────

def test_loading_non_numeric_r_returns_200(client):
    resp = client.get('/watcher/loading?next=/&_r=abc')
    assert resp.status_code == 200


# ── Anti open-redirect sur next ───────────────────────────────────────────────

@pytest.mark.parametrize('evil', [
    'https://evil.com',
    '//evil.com',
    '/\\evil.com',
    'javascript:alert(1)',
])
def test_loading_rejects_external_next(client, evil):
    resp = client.get('/watcher/loading', query_string={'next': evil})
    body = resp.get_data(as_text=True)
    assert 'evil.com' not in body
    assert 'NEXT_URL     = "/"' in body


def test_loading_keeps_internal_next(client):
    resp = client.get('/watcher/loading?next=/metadata')
    assert '"/metadata"' in resp.get_data(as_text=True)


# ── Poll JS au lieu du meta-refresh ───────────────────────────────────────────

def test_loading_polls_ready_endpoint_without_meta_refresh(client):
    body = client.get('/watcher/loading?next=/').get_data(as_text=True)
    assert 'http-equiv' not in body
    assert '/watcher/ready' in body
    # retries < 10 → le poll démarre, pas d'état erreur initial
    assert "show('error');\n" not in body


def test_loading_breaks_redirect_loop_after_10_retries(client):
    body = client.get('/watcher/loading?next=/&_r=12').get_data(as_text=True)
    assert "show('error');\n" in body
    assert '\n    poll();\n' not in body
