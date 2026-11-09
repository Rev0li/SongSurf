"""
Interface unique « qui est l'utilisateur ? ». Le reste du serveur ne connaît que
ce fichier : changer de source d'identité ne touche que auth/.
"""
from functools import wraps

from flask import jsonify, render_template, request

from auth.dev import dev_user
from auth.portal import user_from_portal_headers
from core import config
from core.storage import _UID_RE


def get_current_user() -> dict | None:
    """Seule source d'identité : config.DEV_MODE (utilisateur dev local) ou la porte du portail."""
    if config.DEV_MODE:
        return dev_user()
    return user_from_portal_headers()


def is_identified(user: dict | None) -> bool:
    """Pseudo présent ET UUID du portail valide : sans UUID, pas de clé de stockage,
    donc refus — jamais de repli sur le pseudo (SSF-03)."""
    return bool(user and user.get('sub') and _UID_RE.match(user.get('uid') or ''))


def unauthenticated_response():
    """Requête arrivée sans passer par Caddy (accès direct au NAS, ou porte mal
    configurée). Pas de redirection vers la connexion, c'est le rôle de Caddy :
    API / extension → 401 JSON, navigateur → page « passe par le portail »."""
    if (request.headers.get('Origin', '') in config._CORS_ORIGINS or request.is_json
            or 'application/json' in request.headers.get('Accept', '')):
        return jsonify({'success': False, 'error': 'Non authentifié'}), 401
    return render_template('use_portal.html', portal_url=config.REVAUTH_HOME_URL), 401


def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_identified(get_current_user()):
            return unauthenticated_response()
        return f(*args, **kwargs)
    return decorated


def is_admin(user: dict | None) -> bool:
    return bool(user) and user.get('role') == 'admin'


def admin_only_response():
    """Outils experts (SSF-13) : réservés à l'admin, 403 pour un membre."""
    return jsonify({'success': False, 'error': 'Réservé à l\'administrateur', 'code': 'admin_only'}), 403
