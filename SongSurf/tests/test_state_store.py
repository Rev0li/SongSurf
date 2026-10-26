"""
State store (SSF-03) — file persistante, round-robin, quotas, état ZIP.
Chaque test ouvre sa propre base SQLite ; « redémarrer » = rouvrir le même fichier.
"""
import pytest

from state_store import StateStore, round_robin_order, ZIP_INTERRUPTED_MSG


@pytest.fixture
def db(tmp_path):
    return tmp_path / 'state' / 'songsurf.db'


def _song(title):
    return {'url': f'https://www.youtube.com/watch?v={title}', 'metadata': {'title': title}}


def _drain(store):
    titles = []
    while (claimed := store.claim_next()) is not None:
        titles.append(claimed[1]['metadata']['title'])
        store.finish(claimed[0])
    return titles


# ── round_robin_order (fonction pure) ────────────────────────────────────────

def test_rr_alternates_users_and_keeps_each_user_order():
    items = [(1, 'alice'), (2, 'alice'), (3, 'alice'), (4, 'bob')]
    assert round_robin_order(items, None) == [1, 4, 2, 3]


def test_rr_resumes_after_last_served_user():
    items = [(1, 'alice'), (2, 'bob'), (3, 'carol')]
    assert round_robin_order(items, 'alice') == [2, 3, 1]
    assert round_robin_order(items, 'carol') == [1, 2, 3]
    # Dernier servi sans titre en attente : on reprend au suivant dans l'ordre des clés
    assert round_robin_order(items, 'bert') == [2, 3, 1]


def test_rr_empty():
    assert round_robin_order([], 'alice') == []


# ── File persistante ──────────────────────────────────────────────────────────

def test_queue_round_robin_between_users(db):
    store = StateStore(db)
    store.enqueue_job('alice', [_song('a1'), _song('a2'), _song('a3')])
    store.enqueue_job('bob', [_song('b1')])
    assert _drain(store) == ['a1', 'b1', 'a2', 'a3']


def test_late_user_is_served_before_the_rest_of_a_big_album(db):
    store = StateStore(db)
    store.enqueue_job('alice', [_song(f'a{i}') for i in range(1, 6)])
    first = store.claim_next()
    store.finish(first[0])                        # a1 terminé
    store.enqueue_job('bob', [_song('b1')])       # bob arrive pendant l'album
    assert _drain(store) == ['b1', 'a2', 'a3', 'a4', 'a5']


def test_queue_survives_restart_and_resumes_interrupted_song(db):
    store = StateStore(db)
    store.enqueue_job('alice', [_song('a1'), _song('a2')])
    store.enqueue_job('bob', [_song('b1')])
    claimed = store.claim_next()                  # a1 en cours…
    assert claimed[1]['metadata']['title'] == 'a1'
    store.close()                                 # … arrêt brutal

    restarted = StateStore(db)
    assert restarted.pending_count() == 3         # a1 repassé en attente
    # Le pointeur round-robin a survécu (alice servie en dernier) : bob passe,
    # puis a1 est retéléchargé avant a2 (ordre des titres d'alice conservé).
    assert _drain(restarted) == ['b1', 'a1', 'a2']


def test_pending_jobs_counts_jobs_not_songs(db):
    store = StateStore(db)
    store.enqueue_job('alice', [_song('a1'), _song('a2')])
    store.enqueue_job('alice', [_song('a3')])
    store.enqueue_job('bob', [_song('b1')])
    assert store.pending_jobs('alice') == 2
    assert store.pending_jobs('bob') == 1
    assert store.pending_jobs('carol') == 0
    _drain(store)
    assert store.pending_jobs('alice') == 0


def test_pending_for_and_songs_before(db):
    store = StateStore(db)
    store.enqueue_job('alice', [_song('a1'), _song('a2'), _song('a3')])
    store.enqueue_job('bob', [_song('b1'), _song('b2')])
    assert [s['metadata']['title'] for s in store.pending_for('bob')] == ['b1', 'b2']
    assert store.songs_before('alice') == 0
    assert store.songs_before('bob') == 1         # a1 passe avant b1
    assert store.songs_before('carol') is None


def test_enqueue_empty_job_is_noop(db):
    store = StateStore(db)
    assert store.enqueue_job('alice', []) == 0
    assert store.pending_count() == 0


# ── Quota journalier ──────────────────────────────────────────────────────────

def test_daily_count_is_per_user_and_per_day(db):
    store = StateStore(db)
    store.daily_increment('alice', '2026-10-26')
    store.daily_increment('alice', '2026-10-26')
    store.daily_increment('bob', '2026-10-26')
    assert store.daily_count('alice', '2026-10-26') == 2
    assert store.daily_count('bob', '2026-10-26') == 1
    store.close()
    restarted = StateStore(db)
    assert restarted.daily_count('alice', '2026-10-26') == 2   # survit au redémarrage
    restarted.daily_increment('alice', '2026-10-27')           # nouveau jour : purge des anciens
    assert restarted.daily_count('alice', '2026-10-27') == 1
    assert restarted.daily_count('alice', '2026-10-26') == 0


# ── État ZIP ──────────────────────────────────────────────────────────────────

def test_zip_state_survives_restart(db):
    store = StateStore(db)
    store.zip_set('alice', status='ready', zip_path='/tmp/a.zip', total=3, done=3, size_mb=1.5)
    store.zip_set('bob', status='building', zip_path='/tmp/b.zip', total=10, done=4)
    store.close()

    restarted = StateStore(db)
    alice = restarted.zip_get('alice')
    assert alice['status'] == 'ready' and alice['size_mb'] == 1.5
    bob = restarted.zip_get('bob')
    assert bob['status'] == 'error' and bob['error'] == ZIP_INTERRUPTED_MSG
    restarted.zip_delete('alice')
    assert restarted.zip_get('alice') is None
