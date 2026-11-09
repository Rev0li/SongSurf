"""
Stockage par utilisateur : bibliothèque et cookies, rangés par UUID du portail.
"""
import logging
import re
from pathlib import Path

from flask import jsonify

from core import config

logger = logging.getLogger('songsurf')

# ── Per-user storage ───────────────────────────────────────────────────────────
# Clé de stockage = UUID du compte portail (X-User-Id), admin compris :
# unique et stable par construction, jamais dérivée du pseudo (SSF-03). Le pseudo
# ne sert qu'à l'affichage, aux logs et au fichier .owner des dossiers.

_UID_RE = re.compile(r'^[A-Za-z0-9-]{8,64}$')

OWNER_FILE = '.owner'


def _user_key(user: dict) -> str:
    """Clé de stockage de l'utilisateur (bibliothèque, cookies, file, quota, ZIP)."""
    uid = (user or {}).get('uid') or ''
    if not _UID_RE.match(uid):
        raise ValueError(f"Identifiant de compte invalide: {uid!r}")
    return uid


def _user_pseudo(user: dict) -> str:
    """Pseudo d'affichage (exact, transmis par le portail)."""
    return (user or {}).get('sub') or ''


def _user_music_dir(user: dict) -> Path:
    """config.BASE_MUSIC_DIR/<uid>/ (uid/Artist/Album/), with a .owner file holding the
    pseudo so the folder stays readable. DEV_MODE too (user 'dev-user-local')."""
    key = _user_key(user)
    d = (config.BASE_MUSIC_DIR / key).resolve()
    if not d.is_relative_to(config.BASE_MUSIC_DIR.resolve()) or d == config.BASE_MUSIC_DIR.resolve():
        raise ValueError(f"Invalid user key — path escapes music dir: {key!r}")
    d.mkdir(parents=True, exist_ok=True)
    _write_owner_file(d, _user_pseudo(user))
    return d


def _write_owner_file(d: Path, pseudo: str) -> None:
    """Écrit le pseudo dans <dossier>/.owner s'il manque ou a changé (jamais bloquant)."""
    if not pseudo:
        return
    owner = d / OWNER_FILE
    try:
        if not owner.is_file() or owner.read_text(encoding='utf-8').strip() != pseudo:
            owner.write_text(pseudo + '\n', encoding='utf-8')
    except OSError as e:
        logger.warning(f"⚠️ .owner non écrit dans {d.name}: {e}")


COOKIES_MISSING_MSG = ("Cookies YouTube manquants pour ton compte : connecte-toi à YouTube, "
                       "puis clique « Sync cookies YouTube » dans l'extension SongSurf Clip.")


def _user_cookies_file(user: dict | None) -> Path:
    """Fichier cookies Netscape de l'utilisateur : config.COOKIES_DIR/<uid>.txt."""
    key = _user_key(user or {})
    f = (config.COOKIES_DIR / f'{key}.txt').resolve()
    if not f.is_relative_to(config.COOKIES_DIR.resolve()):
        raise ValueError(f"Invalid user key — path escapes cookies dir: {key!r}")
    return f


def _cookies_missing_response(user: dict | None):
    """403 + message clair si l'utilisateur n'a pas synchronisé ses cookies, sinon None.

    Pas de repli sur les cookies d'un autre compte (décision SSF-01).
    """
    if _user_cookies_file(user).is_file():
        return None
    return jsonify({'success': False, 'error': COOKIES_MISSING_MSG,
                    'code': 'cookies_missing'}), 403
