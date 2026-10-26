# -*- coding: utf-8 -*-
"""
État persistant de SongSurf (SSF-03) — SQLite dans /data/state.

Survit aux redémarrages :
  - la file de téléchargement (un titre = une ligne, regroupés par job = album) ;
  - le pointeur du round-robin (quel utilisateur a été servi en dernier) ;
  - les compteurs journaliers par utilisateur ;
  - l'état des exports ZIP par utilisateur.

Les utilisateurs sont identifiés par leur clé de stockage (UUID du portail).
Une seule connexion partagée, protégée par un verrou : le trafic est faible
(un worker + quelques requêtes HTTP), la simplicité prime.
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL,
    user_key   TEXT    NOT NULL,
    item_json  TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'pending',   -- pending | active
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queue_user ON queue_items (user_key, id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_counts (
    user_key TEXT NOT NULL,
    day      TEXT NOT NULL,
    count    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_key, day)
);

CREATE TABLE IF NOT EXISTS zip_exports (
    user_key   TEXT PRIMARY KEY,
    status     TEXT NOT NULL,          -- building | ready | error
    zip_path   TEXT NOT NULL DEFAULT '',
    done       INTEGER NOT NULL DEFAULT 0,
    total      INTEGER NOT NULL DEFAULT 0,
    size_mb    REAL    NOT NULL DEFAULT 0,
    error      TEXT    NOT NULL DEFAULT '',
    updated_at TEXT    NOT NULL
);
"""

ZIP_INTERRUPTED_MSG = "Export interrompu par un redémarrage, relance-le."


def round_robin_order(items, last_user: str | None) -> list:
    """Ordre de passage des titres en attente, chaque utilisateur à tour de rôle.

    items : [(id, user_key), ...] dans l'ordre d'arrivée (id croissant).
    Les utilisateurs tournent dans l'ordre de leur clé ; le tour reprend juste
    après `last_user` (le dernier servi). À l'intérieur d'un utilisateur, ses
    titres restent dans l'ordre d'arrivée (un album garde sa séquence).
    Retourne la liste des ids dans l'ordre où le worker les prendra.
    """
    per_user: dict[str, list] = {}
    for item_id, user_key in items:
        per_user.setdefault(user_key, []).append(item_id)
    users = sorted(per_user)
    if not users:
        return []
    start = 0
    if last_user is not None:
        start = next((i for i, u in enumerate(users) if u > last_user), 0)
    rotation = users[start:] + users[:start]

    order = []
    depth = 0
    while len(order) < len(items):
        for u in rotation:
            if depth < len(per_user[u]):
                order.append(per_user[u][depth])
        depth += 1
    return order


class StateStore:
    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(db_path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute('PRAGMA journal_mode=WAL')
            self._db.executescript(_SCHEMA)
            self._recover()

    def _recover(self) -> None:
        """Au démarrage : un titre « en cours » lors de l'arrêt repasse en attente
        (il sera retéléchargé), un ZIP en construction est marqué interrompu."""
        self._db.execute("UPDATE queue_items SET status = 'pending' WHERE status = 'active'")
        self._db.execute(
            "UPDATE zip_exports SET status = 'error', error = ?, updated_at = ? WHERE status = 'building'",
            (ZIP_INTERRUPTED_MSG, _now()),
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ── File de téléchargement ────────────────────────────────────────────────

    def enqueue_job(self, user_key: str, songs: list) -> int:
        """Ajoute un job (album ou titre seul) : ses titres en attente, dans l'ordre."""
        if not songs:
            return 0
        now = _now()
        with self._lock:
            self._db.execute('BEGIN')
            try:
                row = self._db.execute('SELECT COALESCE(MAX(job_id), 0) + 1 FROM queue_items').fetchone()
                job_id = row[0]
                self._db.executemany(
                    'INSERT INTO queue_items (job_id, user_key, item_json, created_at) VALUES (?, ?, ?, ?)',
                    [(job_id, user_key, json.dumps(s, ensure_ascii=False), now) for s in songs],
                )
                self._db.execute('COMMIT')
            except Exception:
                self._db.execute('ROLLBACK')
                raise
        return len(songs)

    def pending_jobs(self, user_key: str) -> int:
        """Nombre de jobs de l'utilisateur pas encore terminés (en attente ou en cours)."""
        with self._lock:
            row = self._db.execute(
                'SELECT COUNT(DISTINCT job_id) FROM queue_items WHERE user_key = ?', (user_key,)
            ).fetchone()
        return row[0]

    def pending_count(self) -> int:
        """Titres en attente (pas encore démarrés), tous utilisateurs confondus."""
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) FROM queue_items WHERE status = 'pending'").fetchone()
        return row[0]

    def pending_for(self, user_key: str) -> list:
        """Titres en attente de l'utilisateur, dans son ordre à lui."""
        with self._lock:
            rows = self._db.execute(
                "SELECT item_json FROM queue_items WHERE user_key = ? AND status = 'pending' ORDER BY id",
                (user_key,),
            ).fetchall()
        return [json.loads(r['item_json']) for r in rows]

    def songs_before(self, user_key: str) -> int | None:
        """Nombre de titres d'autres utilisateurs qui passeront avant le prochain
        titre de `user_key` (titre en cours non compté). None s'il n'a rien en attente."""
        with self._lock:
            order = self._pending_order()
            owners = dict(self._db.execute(
                "SELECT id, user_key FROM queue_items WHERE status = 'pending'"
            ).fetchall())
        for index, item_id in enumerate(order):
            if owners[item_id] == user_key:
                return index
        return None

    def claim_next(self):
        """Prend le prochain titre (round-robin), le marque en cours.
        Retourne (id, item) ou None si la file est vide."""
        with self._lock:
            order = self._pending_order()
            if not order:
                return None
            item_id = order[0]
            row = self._db.execute(
                'SELECT user_key, item_json FROM queue_items WHERE id = ?', (item_id,)
            ).fetchone()
            self._db.execute("UPDATE queue_items SET status = 'active' WHERE id = ?", (item_id,))
            self._db.execute(
                "INSERT INTO meta (key, value) VALUES ('rr_last_user', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (row['user_key'],),
            )
        return item_id, json.loads(row['item_json'])

    def finish(self, item_id: int) -> None:
        """Titre traité (succès ou échec) : il quitte la file."""
        with self._lock:
            self._db.execute('DELETE FROM queue_items WHERE id = ?', (item_id,))

    def _pending_order(self) -> list:
        """Sous self._lock."""
        items = self._db.execute(
            "SELECT id, user_key FROM queue_items WHERE status = 'pending' ORDER BY id"
        ).fetchall()
        last = self._db.execute("SELECT value FROM meta WHERE key = 'rr_last_user'").fetchone()
        return round_robin_order([(r['id'], r['user_key']) for r in items], last[0] if last else None)

    # ── Quota journalier ──────────────────────────────────────────────────────

    def daily_count(self, user_key: str, day: str) -> int:
        with self._lock:
            row = self._db.execute(
                'SELECT count FROM daily_counts WHERE user_key = ? AND day = ?', (user_key, day)
            ).fetchone()
        return row[0] if row else 0

    def daily_increment(self, user_key: str, day: str) -> None:
        with self._lock:
            self._db.execute('DELETE FROM daily_counts WHERE day < ?', (day,))
            self._db.execute(
                'INSERT INTO daily_counts (user_key, day, count) VALUES (?, ?, 1) '
                'ON CONFLICT(user_key, day) DO UPDATE SET count = count + 1',
                (user_key, day),
            )

    # ── Exports ZIP ───────────────────────────────────────────────────────────

    def zip_get(self, user_key: str) -> dict | None:
        with self._lock:
            row = self._db.execute('SELECT * FROM zip_exports WHERE user_key = ?', (user_key,)).fetchone()
        return dict(row) if row else None

    def zip_set(self, user_key: str, **fields) -> None:
        """Crée ou met à jour l'état ZIP de l'utilisateur (champs de zip_exports)."""
        fields['updated_at'] = _now()
        cols = ', '.join(fields)
        marks = ', '.join('?' for _ in fields)
        updates = ', '.join(f'{c} = excluded.{c}' for c in fields)
        with self._lock:
            self._db.execute(
                f'INSERT INTO zip_exports (user_key, {cols}) VALUES (?, {marks}) '
                f'ON CONFLICT(user_key) DO UPDATE SET {updates}',
                (user_key, *fields.values()),
            )

    def zip_delete(self, user_key: str) -> None:
        with self._lock:
            self._db.execute('DELETE FROM zip_exports WHERE user_key = ?', (user_key,))


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')
