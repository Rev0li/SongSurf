"""
Pages du site et routes de base : application web, fichiers statiques,
déconnexion, identité courante, sonde de santé.
"""
import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, send_file, send_from_directory

from auth.provider import auth_required, get_current_user
from core import config
from core.storage import _user_pseudo

pages_bp = Blueprint('pages', __name__)


# ── Logout ────────────────────────────────────────────────────────────────────

@pages_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """La session est celle du portail (pas de cookie ici) : retour au portail."""
    return redirect(config.REVAUTH_HOME_URL or '/')


# ── SPA ───────────────────────────────────────────────────────────────────────

# In Docker: FRONTEND_BUILD_PATH=/app/frontend/build (set in Dockerfile).
# In local dev: falls back to sibling of server/ directory.
_FRONTEND_BUILD = Path(
    os.environ.get('FRONTEND_BUILD_PATH') or
    str(Path(__file__).parent.parent.parent / 'frontend' / 'build')
).resolve()


def _spa():
    """Serve the SvelteKit SPA index.html (requires auth)."""
    index = _FRONTEND_BUILD / 'index.html'
    if index.exists():
        resp = send_file(index)
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    return 'Frontend not built. Run: make build', 503


@pages_bp.route('/')
@auth_required
def dashboard():
    return _spa()


# Pages de l'appli (SSF-13) : un rechargement (ou « tirer pour rafraîchir » sur
# mobile) sur /library doit rendre l'appli, pas un 404. /metadata = ancienne
# adresse, redirigée côté client vers /library.
@pages_bp.route('/library')
@pages_bp.route('/metadata')
@auth_required
def spa_pages():
    return _spa()


@pages_bp.route('/_app/<path:filename>')
def svelte_assets(filename):
    """Serve SvelteKit's generated JS/CSS bundles (no auth needed)."""
    return send_from_directory(_FRONTEND_BUILD / '_app', filename)


@pages_bp.route('/<path:filename>')
def static_assets(filename):
    """Serve top-level static files copied from SvelteKit's static/ dir
    (fonts, help/ tutorial images, favicon…). Public assets — no auth.
    Only real files are served; unknown paths 404 (SPA pages have their own
    routes above: /, /library, /metadata). This catch-all is the least specific rule, so explicit API /
    asset routes always win."""
    target = (_FRONTEND_BUILD / filename).resolve()
    if not target.is_relative_to(_FRONTEND_BUILD) or not target.is_file():
        abort(404)
    return send_from_directory(_FRONTEND_BUILD, filename)


# ── User identity ──────────────────────────────────────────────────────────────

@pages_bp.route('/api/me')
@auth_required
def api_me():
    user = get_current_user()
    return jsonify({**user, 'pseudo': _user_pseudo(user)})


# ── Health ─────────────────────────────────────────────────────────────────────

@pages_bp.route('/ping')
def ping():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})
