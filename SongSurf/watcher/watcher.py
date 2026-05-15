#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SongSurf Watcher — Portail léger toujours actif

Phase 3 : authentification JWT (HS256) émis par auth-selfhost-rust.
  - DEV_MODE=true  → utilisateur dev injecté automatiquement, accès libre
  - DEV_MODE=false → valide le cookie access_token (JWT HS256)
  - Si JWT invalide/absent → redirect vers AUTH_SERVICE_LOGIN_URL (ou 503 si non configuré)

Variables d'environnement:
  WATCHER_SECRET           Secret partagé avec SongSurf (OBLIGATOIRE)
  DEV_MODE                 'true' pour contourner l'auth en développement
  AUTH_JWT_SECRET          Clé HMAC partagée avec auth-selfhost-rust (OBLIGATOIRE en prod)
  AUTH_SERVICE_LOGIN_URL   URL de la page de login auth-selfhost-rust (ex: http://auth:8000/login)
  TARGET_CONTAINER         Nom du container SongSurf  (défaut: songsurf)
  TARGET_URL               URL interne de SongSurf    (défaut: http://songsurf:8081)
  INACTIVITY_WARN_TIMEOUT  Secondes sans activité avant avertissement (défaut: 3600)
  INACTIVITY_GRACE_TIMEOUT Secondes après avertissement avant arrêt forcé (défaut: 900)
  FLASK_SECRET_KEY         Clé Flask (génération aléatoire si absent)
"""

from flask import (Flask, request, redirect,
                   render_template, Response, stream_with_context, jsonify)
from datetime import datetime
import threading
import time
import os
import secrets
import logging
import requests as req_lib
import docker as docker_sdk
import jwt as pyjwt
from urllib.parse import urlparse

# ── Configuration ─────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder='templates', static_folder=None)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# Allowed CORS origins: Chrome extension + optional custom origin
_CORS_ORIGINS = set(filter(None, [
    # Chrome extensions send Origin: chrome-extension://<id>
    # We allow all extension origins; the real auth guard is the JWT cookie.
    'null',  # some browsers send "null" for extensions
] + [o.strip() for o in os.getenv('CORS_EXTRA_ORIGINS', '').split(',') if o.strip()]))

WATCHER_SECRET         = os.getenv('WATCHER_SECRET', secrets.token_hex(32))
DEV_MODE               = os.getenv('DEV_MODE', 'false').lower() == 'true'
AUTH_JWT_SECRET        = os.getenv('AUTH_JWT_SECRET', '')
AUTH_SERVICE_LOGIN_URL = os.getenv('AUTH_SERVICE_LOGIN_URL', '')

TARGET_CONTAINER         = os.getenv('TARGET_CONTAINER', 'songsurf')
TARGET_URL               = os.getenv('TARGET_URL', 'http://songsurf:8081').rstrip('/')
INACTIVITY_WARN_TIMEOUT  = int(os.getenv('INACTIVITY_WARN_TIMEOUT', os.getenv('INACTIVITY_TIMEOUT', '3600')))
INACTIVITY_GRACE_TIMEOUT = int(os.getenv('INACTIVITY_GRACE_TIMEOUT', '900'))
PROXY_CONNECT_TIMEOUT    = float(os.getenv('PROXY_CONNECT_TIMEOUT', '2.5'))
PROXY_READ_TIMEOUT       = float(os.getenv('PROXY_READ_TIMEOUT', '30'))

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHER] %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

if DEV_MODE:
    logger.warning("⚠️  DEV_MODE activé — authentification désactivée (dev only)")
elif not AUTH_JWT_SECRET:
    logger.warning("⚠️  AUTH_JWT_SECRET absent — le service refusera toutes les connexions jusqu'à configuration")
else:
    logger.info("🔒 Mode production — JWT HS256 activé")

# ── État global ───────────────────────────────────────────────────────────────

last_activity    = time.time()
activity_lock    = threading.Lock()
warning_emitted  = False
warning_since    = 0.0

docker_client = None
try:
    docker_client = docker_sdk.from_env()
    logger.info("✅ Docker socket connecté")
except Exception as e:
    logger.warning(f"⚠️  Docker socket indisponible: {e} — contrôle auto désactivé")

# ── Authentification utilisateur ──────────────────────────────────────────────

_DEV_USER = {'sub': 'dev-user-local', 'role': 'admin', 'email': 'dev@local'}


def _validate_jwt(token: str) -> dict | None:
    """Validates HS256 JWT from auth-selfhost-rust. Returns normalized claims or None."""
    if not AUTH_JWT_SECRET:
        return None
    try:
        claims = pyjwt.decode(
            token,
            AUTH_JWT_SECRET,
            algorithms=['HS256'],
            options={'require': ['sub', 'role', 'exp']},
        )
        if claims.get('token_type') != 'access':
            return None
        return {
            'sub':   claims['sub'],
            'role':  claims['role'].lower(),
            'email': claims.get('email', ''),
        }
    except pyjwt.PyJWTError:
        return None


def _extract_jwt_from_request() -> str | None:
    """Reads JWT from the access_token HttpOnly cookie."""
    return request.cookies.get('access_token') or None


def _get_user_from_request() -> dict | None:
    """
    Returns user claims or None if unauthenticated.
    - DEV_MODE=true → dev user, always authenticated
    - Otherwise     → validate access_token cookie (JWT HS256)
    """
    if DEV_MODE:
        return _DEV_USER.copy()
    token = _extract_jwt_from_request()
    if token:
        return _validate_jwt(token)
    return None


# ── Helpers : contrôle Docker ─────────────────────────────────────────────────

def _get_container():
    if not docker_client:
        return None
    try:
        return docker_client.containers.get(TARGET_CONTAINER)
    except docker_sdk.errors.NotFound:
        logger.error(f"❌ Container '{TARGET_CONTAINER}' introuvable")
        return None
    except Exception as e:
        logger.error(f"❌ Erreur Docker: {e}")
        return None


def _songsurf_running():
    c = _get_container()
    if c is None:
        return True
    c.reload()
    return c.status == 'running'


def _target_port(default=8081):
    try:
        return int(urlparse(TARGET_URL).port or default)
    except Exception:
        return default


def _candidate_target_urls():
    urls = []

    def _add(u):
        if u and u not in urls:
            urls.append(u)

    _add(TARGET_URL)
    for raw in os.getenv('TARGET_URL_FALLBACKS', '').split(','):
        _add(raw.strip().rstrip('/'))

    c = _get_container()
    if c is not None:
        try:
            c.reload()
            networks = (c.attrs.get('NetworkSettings', {}) or {}).get('Networks', {}) or {}
            port = _target_port()
            for net in networks.values():
                ip = (net or {}).get('IPAddress')
                if ip:
                    _add(f"http://{ip}:{port}")
        except Exception:
            pass
    return urls


def _start_songsurf():
    c = _get_container()
    if c is None:
        return
    c.reload()
    if c.status != 'running':
        logger.info(f"🚀 Démarrage de '{TARGET_CONTAINER}'...")
        c.start()


def _stop_songsurf():
    c = _get_container()
    if c is None:
        return
    c.reload()
    if c.status == 'running':
        total_idle = INACTIVITY_WARN_TIMEOUT + INACTIVITY_GRACE_TIMEOUT
        logger.info(f"⏹️  Arrêt de '{TARGET_CONTAINER}' (inactivité {total_idle}s)")
        c.stop(timeout=15)


def _songsurf_ready(timeout=2):
    deadline = time.time() + timeout
    urls = _candidate_target_urls()
    while time.time() < deadline:
        for base_url in urls:
            try:
                r = req_lib.get(f"{base_url}/ping", timeout=1.5)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


# ── Thread d'inactivité ───────────────────────────────────────────────────────

def _update_activity():
    global last_activity, warning_emitted, warning_since
    with activity_lock:
        last_activity   = time.time()
        warning_emitted = False
        warning_since   = 0.0


def _inactivity_watcher():
    global warning_emitted, warning_since
    while True:
        time.sleep(60)
        with activity_lock:
            idle = time.time() - last_activity

        if idle >= INACTIVITY_WARN_TIMEOUT and not warning_emitted:
            warning_emitted = True
            warning_since   = time.time()
            logger.warning("⌛ Inactivité détectée (%ss). Arrêt dans %ss.", INACTIVITY_WARN_TIMEOUT, INACTIVITY_GRACE_TIMEOUT)

        if idle >= (INACTIVITY_WARN_TIMEOUT + INACTIVITY_GRACE_TIMEOUT):
            if _songsurf_running():
                _stop_songsurf()


def _inactivity_snapshot():
    with activity_lock:
        now   = time.time()
        idle  = int(max(0, now - last_activity))
        warned = bool(warning_emitted)
        since  = float(warning_since or 0.0)

    force_stop_in = max(0, INACTIVITY_WARN_TIMEOUT + INACTIVITY_GRACE_TIMEOUT - idle)
    grace_left    = max(0, INACTIVITY_GRACE_TIMEOUT - int(max(0.0, now - since))) if warned and since > 0 else INACTIVITY_GRACE_TIMEOUT

    return {
        'warned':                  warned,
        'idle_seconds':            idle,
        'warn_after_seconds':      INACTIVITY_WARN_TIMEOUT,
        'grace_seconds':           INACTIVITY_GRACE_TIMEOUT,
        'grace_remaining_seconds': grace_left,
        'force_stop_in_seconds':   force_stop_in,
    }


threading.Thread(target=_inactivity_watcher, daemon=True).start()

# ── Proxy ─────────────────────────────────────────────────────────────────────

_HOP_HEADERS = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'host'
}

_PASSIVE_ACTIVITY_PATHS = {'/ping', '/api/status'}


def _proxy(user: dict):
    """Proxyfie la requête vers SongSurf en injectant l'identité utilisateur."""
    if request.path not in _PASSIVE_ACTIVITY_PATHS:
        _update_activity()

    fwd_headers = {k: v for k, v in request.headers if k.lower() not in _HOP_HEADERS}
    fwd_headers['X-Watcher-Token'] = WATCHER_SECRET
    fwd_headers['X-User-Id']       = user['sub']
    fwd_headers['X-User-Role']     = user['role']
    fwd_headers['X-User-Email']    = user.get('email', '')

    path_qs = request.full_path.rstrip('?')
    resp = None
    last_err = None

    for base_url in _candidate_target_urls():
        try:
            resp = req_lib.request(
                method=request.method,
                url=base_url + path_qs,
                headers=fwd_headers,
                data=request.get_data(),
                params={},
                allow_redirects=False,
                stream=True,
                timeout=(PROXY_CONNECT_TIMEOUT, PROXY_READ_TIMEOUT),
            )
            break
        except req_lib.exceptions.RequestException as e:
            last_err = e
            continue

    if resp is None:
        if last_err:
            logger.warning(f"⚠️ Proxy SongSurf indisponible: {last_err}")
        if request.path == '/favicon.ico':
            return Response(status=204)
        # JSON/API callers → 503 (pas de redirect pour éviter les boucles)
        if request.is_json or 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': False, 'error': 'Service temporairement indisponible', 'retry': True}), 503
        # Pages → loading avec compteur de retry (_r) pour briser les boucles
        current_r = int(request.args.get('_r', '0'))
        return redirect(f'/watcher/loading?next={request.path}&_r={current_r + 1}')

    resp_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in _HOP_HEADERS]
    return Response(
        stream_with_context(resp.iter_content(chunk_size=8192)),
        status=resp.status_code,
        headers=resp_headers,
        content_type=resp.headers.get('Content-Type', 'text/html'),
    )


# ── Routes Watcher ────────────────────────────────────────────────────────────

@app.route('/watcher/loading')
def loading():
    next_url = request.args.get('next', '/')
    retries  = min(int(request.args.get('_r', '0')), 10)
    return render_template('pages/loading.html', next_url=next_url, retries=retries)


@app.route('/watcher/ready')
def watcher_ready():
    ready = _songsurf_running() and _songsurf_ready(timeout=2)
    return jsonify({'ready': ready})


@app.route('/watcher/inactivity-status', methods=['GET'])
def watcher_inactivity_status():
    user = _get_user_from_request()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401
    return jsonify(_inactivity_snapshot())


@app.route('/watcher/keepalive', methods=['POST'])
def watcher_keepalive():
    user = _get_user_from_request()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401
    _update_activity()
    return jsonify({'success': True, **_inactivity_snapshot()})


@app.route('/ping')
def ping():
    return 'pong', 200


# ── CORS for Chrome extension ─────────────────────────────────────────────────

def _cors_headers(origin: str) -> dict:
    """Returns CORS headers when the request comes from a Chrome extension."""
    if not origin:
        return {}
    is_extension = origin.startswith('chrome-extension://') or origin == 'null'
    if not is_extension and origin not in _CORS_ORIGINS:
        return {}
    return {
        'Access-Control-Allow-Origin':      origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods':     'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers':     'Content-Type, Accept',
    }


@app.route('/api/queue-direct', methods=['OPTIONS'])
@app.route('/ping', methods=['OPTIONS'])
def cors_preflight():
    origin = request.headers.get('Origin', '')
    hdrs = _cors_headers(origin)
    if not hdrs:
        return Response(status=403)
    return Response(status=204, headers=hdrs)


@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin', '')
    for k, v in _cors_headers(origin).items():
        response.headers[k] = v
    return response


# ── Logout ───────────────────────────────────────────────────────────────────

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Clear session cookie, stop SongSurf if idle, redirect to auth login."""
    active = False
    if _songsurf_running():
        try:
            for base_url in _candidate_target_urls():
                r = req_lib.get(
                    f"{base_url}/api/status",
                    headers={'X-Watcher-Token': WATCHER_SECRET},
                    timeout=2,
                )
                if r.ok:
                    data   = r.json()
                    active = data.get('in_progress', False) or (data.get('queue_size', 0) > 0)
                    break
        except Exception:
            pass

    if active:
        logger.info("ℹ️  Logout — SongSurf maintenu (téléchargement actif)")
    else:
        logger.info("💤 Logout — mise en veille de SongSurf")
        threading.Thread(target=_stop_songsurf, daemon=True).start()

    target = AUTH_SERVICE_LOGIN_URL or '/'
    resp = redirect(target)
    resp.delete_cookie('access_token', path='/', samesite='Lax')
    return resp


# ── Catch-all proxy ───────────────────────────────────────────────────────────

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    if path == 'favicon.ico':
        return Response(status=204)

    user = _get_user_from_request()
    if not user:
        if AUTH_SERVICE_LOGIN_URL:
            return redirect(AUTH_SERVICE_LOGIN_URL)
        return render_template('pages/unavailable.html'), 503

    if not _songsurf_running():
        _start_songsurf()
        return redirect(f'/watcher/loading?next=/{path}')

    return _proxy(user)


# ── Démarrage ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if DEV_MODE:
        mode = "DEV (bypass JWT)"
    elif AUTH_JWT_SECRET:
        mode = f"PRODUCTION (JWT HS256, login={AUTH_SERVICE_LOGIN_URL or 'non configuré → 503'})"
    else:
        mode = "PRODUCTION (AUTH_JWT_SECRET absent → service verrouillé)"
    logger.info(f"🚀 Watcher démarré — mode={mode}, target={TARGET_URL}")
    app.run(host='0.0.0.0', port=int(os.getenv('WATCHER_PORT', '8080')), debug=False)
