"""
Tests for the Watcher inactivity shutdown logic — _songsurf_busy (downloads
block the stop), _inactivity_tick lifecycle (warn → grace → stop, stale
warning cleanup), activity reset on container start, logout busy check.
"""
import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'watcher'))

import pytest
import watcher


@pytest.fixture()
def client():
    watcher.app.config['TESTING'] = True
    return watcher.app.test_client()


@pytest.fixture(autouse=True)
def _fresh_activity_state():
    """Chaque test part d'un état d'activité neuf et le restaure à la fin."""
    with watcher.activity_lock:
        watcher.last_activity   = time.time()
        watcher.warning_emitted = False
        watcher.warning_since   = 0.0
    yield
    with watcher.activity_lock:
        watcher.last_activity   = time.time()
        watcher.warning_emitted = False
        watcher.warning_since   = 0.0


def _set_idle(seconds, warned=False):
    with watcher.activity_lock:
        watcher.last_activity   = time.time() - seconds
        watcher.warning_emitted = warned
        watcher.warning_since   = time.time() - 1 if warned else 0.0


class _FakeResponse:
    def __init__(self, ok=True, payload=None):
        self.ok = ok
        self._payload = payload or {}

    def json(self):
        return self._payload


# ── _songsurf_busy ────────────────────────────────────────────────────────────

def _patch_status(monkeypatch, responses):
    """responses: liste alignée sur les URLs candidates — dict payload,
    Exception à lever, ou None (réponse non-ok)."""
    urls = [f'http://target-{i}:8081' for i in range(len(responses))]
    monkeypatch.setattr(watcher, '_candidate_target_urls', lambda: urls)
    by_url = dict(zip(urls, responses))

    def fake_get(url, **kwargs):
        item = by_url[url.rsplit('/api/status', 1)[0]]
        if isinstance(item, Exception):
            raise item
        if item is None:
            return _FakeResponse(ok=False)
        return _FakeResponse(payload=item)

    monkeypatch.setattr(watcher.req_lib, 'get', fake_get)


def test_busy_when_download_in_progress(monkeypatch):
    _patch_status(monkeypatch, [{'in_progress': True, 'queue_size': 0}])
    assert watcher._songsurf_busy() is True


def test_busy_when_queue_not_empty(monkeypatch):
    _patch_status(monkeypatch, [{'in_progress': False, 'queue_size': 3}])
    assert watcher._songsurf_busy() is True


def test_not_busy_when_idle(monkeypatch):
    _patch_status(monkeypatch, [{'in_progress': False, 'queue_size': 0}])
    assert watcher._songsurf_busy() is False


def test_busy_falls_back_to_next_url_on_error(monkeypatch):
    # La 1re URL en erreur ne doit pas court-circuiter les fallbacks
    _patch_status(monkeypatch, [
        watcher.req_lib.exceptions.ConnectionError('down'),
        {'in_progress': True, 'queue_size': 0},
    ])
    assert watcher._songsurf_busy() is True


def test_not_busy_when_all_urls_unreachable(monkeypatch):
    _patch_status(monkeypatch, [
        watcher.req_lib.exceptions.ConnectionError('down'),
        watcher.req_lib.exceptions.ConnectionError('down'),
    ])
    assert watcher._songsurf_busy() is False


# ── _inactivity_tick ──────────────────────────────────────────────────────────

@pytest.fixture()
def tick_env(monkeypatch):
    """Seuils courts + espions sur running/busy/stop."""
    monkeypatch.setattr(watcher, 'INACTIVITY_WARN_TIMEOUT', 100)
    monkeypatch.setattr(watcher, 'INACTIVITY_GRACE_TIMEOUT', 50)
    calls = {'stop': 0, 'busy_checked': 0}
    state = {'running': True, 'busy': False}
    monkeypatch.setattr(watcher, '_songsurf_running', lambda: state['running'])

    def fake_busy():
        calls['busy_checked'] += 1
        return state['busy']

    def fake_stop():
        calls['stop'] += 1

    monkeypatch.setattr(watcher, '_songsurf_busy', fake_busy)
    monkeypatch.setattr(watcher, '_stop_songsurf', fake_stop)
    return calls, state


def test_tick_noop_while_active(tick_env):
    calls, _ = tick_env
    _set_idle(10)
    watcher._inactivity_tick()
    assert watcher.warning_emitted is False
    assert calls == {'stop': 0, 'busy_checked': 0}


def test_tick_clears_stale_warning_after_keepalive(tick_env):
    # Warning posé puis keepalive : le tick suivant doit effacer le warning
    _set_idle(10, warned=True)
    watcher._inactivity_tick()
    assert watcher.warning_emitted is False
    assert watcher.warning_since == 0.0


def test_tick_warns_after_warn_timeout(tick_env):
    calls, _ = tick_env
    _set_idle(120)
    watcher._inactivity_tick()
    assert watcher.warning_emitted is True
    assert watcher.warning_since > 0
    assert calls['stop'] == 0


def test_tick_stops_after_grace_elapsed(tick_env):
    calls, _ = tick_env
    _set_idle(200, warned=True)
    watcher._inactivity_tick()
    assert calls['stop'] == 1


def test_tick_does_not_stop_when_container_already_down(tick_env):
    calls, state = tick_env
    state['running'] = False
    _set_idle(200, warned=True)
    watcher._inactivity_tick()
    assert calls == {'stop': 0, 'busy_checked': 0}


def test_tick_busy_download_defers_warning(tick_env):
    calls, state = tick_env
    state['busy'] = True
    _set_idle(120)
    watcher._inactivity_tick()
    assert watcher.warning_emitted is False
    # busy = activité : le timer est reparti de zéro
    assert time.time() - watcher.last_activity < 5


def test_tick_busy_download_blocks_stop(tick_env):
    calls, state = tick_env
    state['busy'] = True
    _set_idle(200, warned=True)
    watcher._inactivity_tick()
    assert calls['stop'] == 0
    assert watcher.warning_emitted is False


def test_tick_stops_once_download_finished(tick_env):
    # Batch fini : le cycle warn+grace complet doit s'écouler avant l'arrêt
    calls, state = tick_env
    state['busy'] = True
    _set_idle(200)
    watcher._inactivity_tick()
    assert calls['stop'] == 0

    state['busy'] = False
    watcher._inactivity_tick()          # idle ~0 → rien
    assert watcher.warning_emitted is False
    _set_idle(200)
    watcher._inactivity_tick()          # nouveau cycle écoulé → stop
    assert calls['stop'] == 1


# ── _start_songsurf : reset d'activité ───────────────────────────────────────

def test_start_songsurf_resets_activity_timer(monkeypatch):
    # Même sans Docker (container None), le timer doit repartir : sinon le
    # tick d'inactivité re-stoppe le conteneur pendant sa fenêtre de boot.
    monkeypatch.setattr(watcher, '_get_container', lambda: None)
    _set_idle(9999, warned=True)
    watcher._start_songsurf()
    assert time.time() - watcher.last_activity < 5
    assert watcher.warning_emitted is False


def test_start_songsurf_starts_stopped_container(monkeypatch):
    class FakeContainer:
        status = 'exited'
        started = False

        def reload(self):
            pass

        def start(self):
            self.started = True

    c = FakeContainer()
    monkeypatch.setattr(watcher, '_get_container', lambda: c)
    monkeypatch.setattr(watcher.events_client, 'emit', lambda *a, **k: None)
    watcher._start_songsurf()
    assert c.started is True


# ── /logout : check busy ──────────────────────────────────────────────────────

def test_logout_keeps_songsurf_when_busy(client, monkeypatch):
    stopped = threading.Event()
    monkeypatch.setattr(watcher, '_songsurf_running', lambda: True)
    monkeypatch.setattr(watcher, '_songsurf_busy', lambda: True)
    monkeypatch.setattr(watcher, '_stop_songsurf', lambda: stopped.set())
    resp = client.get('/logout')
    assert resp.status_code == 302
    assert not stopped.wait(0.3)


def test_logout_stops_songsurf_when_idle(client, monkeypatch):
    stopped = threading.Event()
    monkeypatch.setattr(watcher, '_songsurf_running', lambda: True)
    monkeypatch.setattr(watcher, '_songsurf_busy', lambda: False)
    monkeypatch.setattr(watcher, '_stop_songsurf', lambda: stopped.set())
    resp = client.get('/logout')
    assert resp.status_code == 302
    assert stopped.wait(2)
