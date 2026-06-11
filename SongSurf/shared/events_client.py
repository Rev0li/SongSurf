"""
events_client — émission d'événements d'activité vers rev0auth (push NAS → VPS).

Utilisé par le watcher ET le serveur SongSurf (copié dans les deux images Docker).
Stdlib uniquement (urllib) pour ne pas toucher aux requirements du serveur.

Contrat : POST AUTH_EVENTS_URL avec header X-Events-Secret, body = événement seul
ou batch (array). Jamais bloquant : envoi en thread daemon, timeout court, échec
→ spool JSONL local rejoué périodiquement. Si AUTH_EVENTS_URL ou
SONGSURF_EVENTS_SECRET est vide, tout est no-op.
"""

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

logger = logging.getLogger('events_client')

EVENTS_TIMEOUT = 3.0
PENDING_MAX_BYTES = 5 * 1024 * 1024
REPLAY_BATCH = 50

_source = 'unknown'
_pending_file = None
_spool_lock = threading.Lock()
_warned_unreachable = False


def _events_url() -> str:
    return (os.getenv('AUTH_EVENTS_URL') or '').strip()


def _events_secret() -> str:
    return (os.getenv('SONGSURF_EVENTS_SECRET') or '').strip()


def _enabled() -> bool:
    return bool(_events_url() and _events_secret())


def init(source: str, pending_file: str) -> None:
    """Configure l'émetteur : source ('watcher'|'songsurf') + chemin du spool."""
    global _source, _pending_file
    _source = source
    _pending_file = pending_file


def derive_pseudo(claims: dict) -> str:
    """Réplique de app.py::_user_pseudo pour les claims JWT (sub/role/email)."""
    admin_pseudo = os.getenv('ADMIN_PSEUDO', 'rev0admin')
    if claims.get('role') == 'admin' and admin_pseudo:
        return admin_pseudo
    email = (claims.get('email') or '').strip().lower()
    if email and '@' in email:
        raw = email.split('@')[0]
    else:
        raw = (claims.get('sub') or 'user')
    pseudo = re.sub(r'[^a-z0-9._-]', '_', raw)
    return pseudo.strip('._-') or 'user'


def emit(event_type: str, *, pseudo='', role='', artist='', album='', title='',
         detail=None, ip='') -> None:
    """Émet un événement en arrière-plan. No-op si non configuré."""
    if not _enabled():
        return
    event = {
        'source': _source,
        'type': event_type,
        'ts': datetime.now(timezone.utc).isoformat(),
        'pseudo': pseudo,
        'role': role,
        'artist': artist,
        'album': album,
        'title': title,
        'detail': detail or {},
        'ip': ip,
    }
    threading.Thread(target=_send_or_spool, args=(event,), daemon=True).start()


def _send_or_spool(event: dict) -> None:
    if not _post(event):
        _spool(event)


def _post(payload) -> bool:
    """POST un événement (dict) ou un batch (list). True si 2xx. N'élève jamais."""
    global _warned_unreachable
    try:
        body = json.dumps(payload).encode('utf-8')
        req = Request(
            _events_url(),
            data=body,
            headers={
                'Content-Type': 'application/json',
                'X-Events-Secret': _events_secret(),
            },
            method='POST',
        )
        with urlopen(req, timeout=EVENTS_TIMEOUT) as resp:
            ok = 200 <= resp.status < 300
        if ok:
            _warned_unreachable = False
        return ok
    except Exception as e:
        if not _warned_unreachable:
            logger.warning(f"⚠️ Événements auth injoignables ({e}) — spool local")
            _warned_unreachable = True
        return False


def _spool(event: dict) -> None:
    """Append JSONL ; au-delà du cap, drop les lignes les plus anciennes."""
    if not _pending_file:
        return
    try:
        line = json.dumps(event, ensure_ascii=False)
        with _spool_lock:
            with open(_pending_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
            if os.path.getsize(_pending_file) > PENDING_MAX_BYTES:
                with open(_pending_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                size = 0
                kept = []
                for ln in reversed(lines):
                    size += len(ln.encode('utf-8'))
                    if size > PENDING_MAX_BYTES // 2:
                        break
                    kept.append(ln)
                with open(_pending_file, 'w', encoding='utf-8') as f:
                    f.writelines(reversed(kept))
    except OSError as e:
        logger.warning(f"⚠️ Spool événements inaccessible: {e}")


def replay_pending_once() -> None:
    """Rejoue le spool par batchs de 50 ; stop au premier échec (retente plus tard)."""
    if not _enabled() or not _pending_file:
        return
    with _spool_lock:
        try:
            if not os.path.exists(_pending_file):
                return
            with open(_pending_file, 'r', encoding='utf-8') as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        except OSError:
            return
        if not lines:
            return

        events = []
        for ln in lines:
            try:
                events.append(json.loads(ln))
            except ValueError:
                continue  # ligne corrompue, abandonnée

        sent = 0
        while sent < len(events):
            batch = events[sent:sent + REPLAY_BATCH]
            if not _post(batch):
                break
            sent += len(batch)

        try:
            remaining = events[sent:]
            with open(_pending_file, 'w', encoding='utf-8') as f:
                for ev in remaining:
                    f.write(json.dumps(ev, ensure_ascii=False) + '\n')
        except OSError as e:
            logger.warning(f"⚠️ Réécriture du spool impossible: {e}")


def start_replay_thread(interval: int = 300) -> None:
    """Thread daemon : rejoue le spool toutes les `interval` secondes."""
    if not _enabled():
        return

    def _loop():
        while True:
            time.sleep(interval)
            try:
                replay_pending_once()
            except Exception as e:
                logger.warning(f"⚠️ Replay événements: {e}")

    threading.Thread(target=_loop, daemon=True).start()
