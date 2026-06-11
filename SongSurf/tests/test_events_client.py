"""
Tests for shared/events_client.py — push d'événements d'activité vers rev0auth.

Pattern : patch de events_client.urlopen (comme test_genre_lookup.py).
L'émission via emit() est asynchrone (thread daemon) ; les tests appellent
directement _send_or_spool / _post / replay_pending_once pour rester déterministes.
"""
import json
import os
from unittest.mock import patch, MagicMock

import pytest

import events_client


TEST_URL = 'http://auth.test/japprends/api/songsurf-events'
TEST_SECRET = 'test-events-secret'


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """events_client configuré avec un spool temporaire."""
    monkeypatch.setenv('AUTH_EVENTS_URL', TEST_URL)
    monkeypatch.setenv('SONGSURF_EVENTS_SECRET', TEST_SECRET)
    pending = tmp_path / 'events-pending-test.jsonl'
    events_client.init('songsurf', str(pending))
    yield pending
    events_client.init('unknown', None)


def _ok_response():
    resp = MagicMock()
    resp.status = 200
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: False
    return resp


def _build_event(**kw):
    base = dict(pseudo='oliver', role='member', artist='Daft Punk',
                album='Discovery', title='One More Time')
    base.update(kw)
    return base


class TestPost:
    def test_post_sends_expected_payload_and_headers(self, configured):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured['url'] = req.full_url
            captured['headers'] = dict(req.headers)
            captured['body'] = json.loads(req.data.decode('utf-8'))
            captured['timeout'] = timeout
            return _ok_response()

        with patch('events_client.urlopen', side_effect=fake_urlopen):
            events_client._send_or_spool({
                'source': 'songsurf', 'type': 'download_success',
                'ts': '2026-06-11T12:00:00+00:00', **_build_event(),
                'detail': {}, 'ip': '',
            })

        assert captured['url'] == TEST_URL
        # urllib capitalise les clés de header
        header_keys = {k.lower(): v for k, v in captured['headers'].items()}
        assert header_keys['x-events-secret'] == TEST_SECRET
        assert header_keys['content-type'] == 'application/json'
        assert captured['body']['type'] == 'download_success'
        assert captured['body']['artist'] == 'Daft Punk'
        assert captured['timeout'] == events_client.EVENTS_TIMEOUT

    def test_emit_noop_when_unconfigured(self, tmp_path, monkeypatch):
        monkeypatch.setenv('AUTH_EVENTS_URL', '')
        monkeypatch.setenv('SONGSURF_EVENTS_SECRET', '')
        pending = tmp_path / 'pending.jsonl'
        events_client.init('songsurf', str(pending))

        with patch('events_client.urlopen') as mock_open:
            events_client.emit('download_success', **_build_event())

        mock_open.assert_not_called()
        assert not pending.exists()

    def test_failure_spools_event(self, configured):
        with patch('events_client.urlopen', side_effect=OSError('connexion refusée')):
            events_client._send_or_spool({'source': 'songsurf', 'type': 'download_success'})

        lines = configured.read_text(encoding='utf-8').strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])['type'] == 'download_success'

    def test_http_error_status_spools(self, configured):
        resp = _ok_response()
        resp.status = 500
        with patch('events_client.urlopen', return_value=resp):
            events_client._send_or_spool({'source': 'songsurf', 'type': 'zip_export'})
        assert configured.exists()

    def test_spool_path_unwritable_does_not_raise(self, monkeypatch):
        monkeypatch.setenv('AUTH_EVENTS_URL', TEST_URL)
        monkeypatch.setenv('SONGSURF_EVENTS_SECRET', TEST_SECRET)
        events_client.init('watcher', '/nonexistent-dir/pending.jsonl')
        with patch('events_client.urlopen', side_effect=OSError('down')):
            events_client._send_or_spool({'type': 'login_success'})  # ne doit pas lever


class TestReplay:
    def test_replay_posts_batch_and_empties_spool(self, configured):
        for i in range(3):
            configured.open('a', encoding='utf-8').write(
                json.dumps({'type': 'download_success', 'n': i}) + '\n')

        posted = []

        def fake_urlopen(req, timeout=None):
            posted.append(json.loads(req.data.decode('utf-8')))
            return _ok_response()

        with patch('events_client.urlopen', side_effect=fake_urlopen):
            events_client.replay_pending_once()

        assert len(posted) == 1            # un seul POST batch
        assert isinstance(posted[0], list)
        assert len(posted[0]) == 3
        assert configured.read_text(encoding='utf-8').strip() == ''

    def test_replay_failure_keeps_spool(self, configured):
        configured.write_text(json.dumps({'type': 'login_success'}) + '\n', encoding='utf-8')

        with patch('events_client.urlopen', side_effect=OSError('down')):
            events_client.replay_pending_once()

        assert json.loads(configured.read_text(encoding='utf-8').strip())['type'] == 'login_success'

    def test_replay_batches_of_50(self, configured):
        with configured.open('a', encoding='utf-8') as f:
            for i in range(120):
                f.write(json.dumps({'type': 'download_success', 'n': i}) + '\n')

        posted = []

        def fake_urlopen(req, timeout=None):
            posted.append(json.loads(req.data.decode('utf-8')))
            return _ok_response()

        with patch('events_client.urlopen', side_effect=fake_urlopen):
            events_client.replay_pending_once()

        assert [len(b) for b in posted] == [50, 50, 20]

    def test_replay_noop_without_spool_file(self, configured):
        with patch('events_client.urlopen') as mock_open:
            events_client.replay_pending_once()
        mock_open.assert_not_called()

    def test_spool_cap_drops_oldest(self, configured, monkeypatch):
        monkeypatch.setattr(events_client, 'PENDING_MAX_BYTES', 2000)
        with patch('events_client.urlopen', side_effect=OSError('down')):
            for i in range(100):
                events_client._send_or_spool({'type': 'download_success', 'n': i})

        lines = [json.loads(l) for l in
                 configured.read_text(encoding='utf-8').strip().splitlines()]
        assert os.path.getsize(configured) <= 2000
        # Les plus récents sont conservés, les plus anciens droppés
        assert lines[-1]['n'] == 99
        assert lines[0]['n'] > 0


class TestDerivePseudo:
    """Parité avec server/app.py::_user_pseudo (hors override _pseudo)."""

    def test_admin_maps_to_admin_pseudo(self, monkeypatch):
        monkeypatch.setenv('ADMIN_PSEUDO', 'rev0admin')
        assert events_client.derive_pseudo(
            {'sub': 'x', 'role': 'admin', 'email': 'boss@example.com'}) == 'rev0admin'

    def test_email_local_part(self):
        assert events_client.derive_pseudo(
            {'sub': 'x', 'role': 'member', 'email': 'Kientzler.Oliver@gmail.com'}) == 'kientzler.oliver'

    def test_special_chars_sanitized(self):
        assert events_client.derive_pseudo(
            {'sub': 'x', 'role': 'member', 'email': 'jean+test!@ex.fr'}) == 'jean_test'

    def test_fallback_on_sub(self):
        assert events_client.derive_pseudo({'sub': 'abc-123', 'role': 'member', 'email': ''}) == 'abc-123'

    def test_parity_with_app_user_pseudo(self):
        import app as songsurf_app
        for user in [
            {'sub': 'u1', 'role': 'member', 'email': 'foo.bar@ex.com'},
            {'sub': 'u2', 'role': 'member', 'email': 'WEIRD__char$@ex.com'},
            {'sub': 'u3', 'role': 'admin', 'email': 'admin@ex.com'},
            {'sub': 'u4', 'role': 'member', 'email': ''},
        ]:
            assert events_client.derive_pseudo(user) == songsurf_app._user_pseudo(user)
