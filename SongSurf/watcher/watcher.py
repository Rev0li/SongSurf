#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SongSurf Watcher — Portail léger toujours actif

Authentification — porte du portail (AUTH-09) :
  - DEV_MODE=true  → utilisateur dev injecté automatiquement, accès libre
  - Sinon : Caddy a déjà vérifié la session auprès du portail et envoie
    l'identité (X-User-Name / X-User-Role / X-User-Id) avec la preuve
    X-Proxy-Token, comparée à SONGSURF_PROXY_SECRET. Sans preuve valide, les
    X-User-* sont ignorés : 401 (API) ou page « passe par le portail ».
    La redirection vers la connexion est faite par Caddy, pas ici.

Variables d'environnement:
  WATCHER_SECRET           Secret partagé avec SongSurf (OBLIGATOIRE)
  DEV_MODE                 'true' pour contourner l'auth en développement
  SONGSURF_PROXY_SECRET    Preuve envoyée par Caddy dans X-Proxy-Token (OBLIGATOIRE en prod,
                           vide = service verrouillé)
  REVAUTH_HOME_URL         URL de l'espace membre du portail (ex: https://…/home/friend)
                           → redirect après logout, lien de la page « passe par le portail »
  TARGET_CONTAINER         Nom du container SongSurf  (défaut: songsurf)
  TARGET_URL               URL interne de SongSurf    (défaut: http://songsurf:8081)
  INACTIVITY_WARN_TIMEOUT  Secondes sans activité avant avertissement (défaut: 3600)
  INACTIVITY_GRACE_TIMEOUT Secondes après avertissement avant arrêt forcé (défaut: 900)
  FLASK_SECRET_KEY         Clé Flask (génération aléatoire si absent)
"""

from flask import (Flask, request, redirect,
                   render_template, Response, stream_with_context, jsonify)
from datetime import datetime
import hmac
import signal
import sys
import threading
import time
import os
import secrets
import logging
import requests as req_lib
import docker as docker_sdk
from waitress import serve
from urllib.parse import urlparse

# En Docker, events_client.py est copié à côté de watcher.py ;
# en dev local (python watcher/watcher.py) il vit dans ../shared.
_SHARED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shared')
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)
import events_client

# ── Configuration ─────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder='templates', static_folder=None)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

WATCHER_SECRET         = os.getenv('WATCHER_SECRET', secrets.token_hex(32))
DEV_MODE               = os.getenv('DEV_MODE', 'false').lower() == 'true'
SONGSURF_PROXY_SECRET  = os.getenv('SONGSURF_PROXY_SECRET', '')
REVAUTH_HOME_URL       = os.getenv('REVAUTH_HOME_URL', '')

# CORS : seule l'extension SongSurf Clip est autorisée (requêtes avec credentials).
# ID fixe, dérivé de la clé "key" de chrome-extension/manifest.json — il ne change
# pas selon le dossier de chargement. Jamais "null" ni chrome-extension://* (S1).
SONGSURF_EXTENSION_ID = 'ojhafabhkjjlganipbadmpifkikhnadf'
_CORS_ORIGINS = {f'chrome-extension://{SONGSURF_EXTENSION_ID}'}

TARGET_CONTAINER         = os.getenv('TARGET_CONTAINER', 'songsurf')
TARGET_URL               = os.getenv('TARGET_URL', 'http://songsurf:8081').rstrip('/')
INACTIVITY_WARN_TIMEOUT  = int(os.getenv('INACTIVITY_WARN_TIMEOUT', os.getenv('INACTIVITY_TIMEOUT', '3600')))
INACTIVITY_GRACE_TIMEOUT = int(os.getenv('INACTIVITY_GRACE_TIMEOUT', '900'))
PROXY_CONNECT_TIMEOUT    = float(os.getenv('PROXY_CONNECT_TIMEOUT', '2.5'))
PROXY_READ_TIMEOUT       = float(os.getenv('PROXY_READ_TIMEOUT', '30'))

# Push d'événements d'activité vers rev0auth (no-op si AUTH_EVENTS_URL absent)
events_client.init('watcher', os.getenv('EVENTS_PENDING_FILE', '/app/logs/events-pending-watcher.jsonl'))


# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHER] %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

if DEV_MODE:
    logger.warning("⚠️  DEV_MODE activé — authentification désactivée (dev only)")
elif not SONGSURF_PROXY_SECRET:
    logger.warning("⚠️  SONGSURF_PROXY_SECRET absent — le service refusera toutes les connexions jusqu'à configuration")
else:
    logger.info("🔒 Mode production — porte du portail (X-Proxy-Token)")

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

_DEV_USER = {'sub': 'dev', 'uid': 'dev-user-local', 'role': 'admin', 'email': 'dev@local'}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _user_from_proxy_headers() -> dict | None:
    """Identité posée par Caddy après vérification de la session par le portail.

    Fiable uniquement si X-Proxy-Token prouve que la requête vient de Caddy :
    le Watcher écoute sur le réseau local, n'importe quel appareil pourrait
    sinon se déclarer admin. Le pseudo est l'identité SongSurf (`sub`) :
    dossiers de bibliothèque et événements en dépendent.
    """
    if not SONGSURF_PROXY_SECRET:
        return None
    proof = request.headers.get('X-Proxy-Token', '')
    if not proof:
        return None
    if not hmac.compare_digest(proof.encode(), SONGSURF_PROXY_SECRET.encode()):
        # Preuve présente mais fausse : secret désynchronisé avec Caddy, ou forge
        logger.warning("⚠️  X-Proxy-Token invalide — en-têtes d'identité ignorés")
        return None
    name = request.headers.get('X-User-Name', '').strip()
    role = request.headers.get('X-User-Role', '').strip().lower()
    if not name or not role:
        return None
    return {
        'sub':   name,
        'role':  role,
        'email': '',
        'uid':   request.headers.get('X-User-Id', '').strip(),
    }


def _get_user_from_request() -> dict | None:
    """
    Returns user claims or None if unauthenticated.
    - DEV_MODE=true → dev user, always authenticated
    - Otherwise     → identity headers set by Caddy, if X-Proxy-Token is valid
    """
    if DEV_MODE:
        return _DEV_USER.copy()
    return _user_from_proxy_headers()


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
    # Reset d'abord : sans ça, idle reste au-dessus du seuil pendant le boot
    # et le tick d'inactivité peut re-stopper le conteneur avant la première
    # requête proxifiée (l'appelant est toujours une requête authentifiée).
    _update_activity()
    c = _get_container()
    if c is None:
        return
    c.reload()
    if c.status != 'running':
        logger.info(f"🚀 Démarrage de '{TARGET_CONTAINER}'...")
        c.start()
        events_client.emit('container_start')


def _stop_songsurf():
    c = _get_container()
    if c is None:
        return
    c.reload()
    if c.status == 'running':
        total_idle = INACTIVITY_WARN_TIMEOUT + INACTIVITY_GRACE_TIMEOUT
        logger.info(f"⏹️  Arrêt de '{TARGET_CONTAINER}' (inactivité {total_idle}s)")
        c.stop(timeout=15)
        events_client.emit('container_stop', detail={'idle_seconds': total_idle})


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


def _songsurf_busy():
    """True si SongSurf a un téléchargement en cours ou des titres en file.
    Statut injoignable → False (on n'empêche pas l'arrêt sur un service muet)."""
    for base_url in _candidate_target_urls():
        try:
            r = req_lib.get(
                f"{base_url}/api/status",
                headers={'X-Watcher-Token': WATCHER_SECRET},
                timeout=2,
            )
            if r.ok:
                data = r.json()
                return bool(data.get('in_progress')) or _safe_int(data.get('queue_size')) > 0
        except Exception:
            continue
    return False


# ── Thread d'inactivité ───────────────────────────────────────────────────────

def _update_activity():
    global last_activity, warning_emitted, warning_since
    with activity_lock:
        last_activity   = time.time()
        warning_emitted = False
        warning_since   = 0.0


def _inactivity_tick():
    """Un passage de la boucle d'inactivité (extrait pour être testable)."""
    global warning_emitted, warning_since
    with activity_lock:
        idle   = time.time() - last_activity
        warned = warning_emitted

    if idle < INACTIVITY_WARN_TIMEOUT:
        # Un keepalive a pu arriver entre la pose du warning et maintenant :
        # on efface le warning périmé pour ne pas laisser la bannière fantôme.
        if warned:
            with activity_lock:
                warning_emitted = False
                warning_since   = 0.0
        return

    running = _songsurf_running()

    # Un téléchargement en cours compte comme de l'activité : l'extension
    # queue en fire-and-forget et le batch doit finir même page fermée.
    # Le reset repousse le prochain check busy d'un cycle WARN complet.
    if running and _songsurf_busy():
        logger.info("⏳ Inactivité HTTP mais téléchargement en cours — arrêt reporté")
        _update_activity()
        return

    if not warned:
        with activity_lock:
            warning_emitted = True
            warning_since   = time.time()
        logger.warning("⌛ Inactivité détectée (%ss). Arrêt dans %ss.", INACTIVITY_WARN_TIMEOUT, INACTIVITY_GRACE_TIMEOUT)

    if idle >= (INACTIVITY_WARN_TIMEOUT + INACTIVITY_GRACE_TIMEOUT) and running:
        _stop_songsurf()


def _inactivity_watcher():
    while True:
        time.sleep(60)
        _inactivity_tick()


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


def _is_identity_header(name: str) -> bool:
    """En-têtes d'identité/preuve venant du client ou de Caddy : jamais relayés
    tels quels à SongSurf (le Watcher pose les siens, la preuve reste ici)."""
    n = name.lower()
    return n.startswith('x-user-') or n in ('x-proxy-token', 'x-watcher-token')


def _proxy(user: dict):
    """Proxyfie la requête vers SongSurf en injectant l'identité utilisateur."""
    if request.path not in _PASSIVE_ACTIVITY_PATHS:
        _update_activity()

    fwd_headers = {k: v for k, v in request.headers
                   if k.lower() not in _HOP_HEADERS and not _is_identity_header(k)}
    fwd_headers['X-Watcher-Token'] = WATCHER_SECRET
    fwd_headers['X-User-Id']       = user['sub']
    fwd_headers['X-User-Role']     = user['role']
    fwd_headers['X-User-Email']    = user.get('email', '')
    if user.get('uid'):
        # Identifiant stable du portail = clé de stockage côté SongSurf (SSF-03) ;
        # absent → SongSurf refuse la requête.
        fwd_headers['X-User-Portal-Id'] = user['uid']

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
        current_r = _safe_int(request.args.get('_r'))
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
    # Anti open-redirect : uniquement un chemin interne ('/...' mais pas '//host' ni backslash)
    if not next_url.startswith('/') or next_url.startswith('//') or '\\' in next_url:
        next_url = '/'
    retries = min(_safe_int(request.args.get('_r')), 10)
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
    """Returns CORS headers only for the SongSurf Clip extension origin."""
    if origin not in _CORS_ORIGINS:
        return {}
    return {
        'Access-Control-Allow-Origin':      origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods':     'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers':     'Content-Type, Accept',
    }


@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def cors_preflight(path=''):
    """Generic CORS preflight for all paths — covers /api/preview, /api/queue-direct, /ping, etc."""
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
    """Stop SongSurf if idle, then back to the portal (its session, its logout)."""
    active = _songsurf_running() and _songsurf_busy()

    if active:
        logger.info("ℹ️  Logout — SongSurf maintenu (téléchargement actif)")
    else:
        logger.info("💤 Logout — mise en veille de SongSurf")
        threading.Thread(target=_stop_songsurf, daemon=True).start()

    return redirect(REVAUTH_HOME_URL or '/')


# ── Catch-all proxy ───────────────────────────────────────────────────────────

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    if path == 'favicon.ico':
        return Response(status=204)

    user = _get_user_from_request()
    if not user:
        # Requête arrivée sans passer par Caddy (accès direct au NAS, ou porte
        # mal configurée) : pas de redirection vers la connexion, c'est le rôle
        # de Caddy. API / extension → 401 JSON, navigateur → page explicative.
        if (request.headers.get('Origin', '') in _CORS_ORIGINS or request.is_json
                or 'application/json' in request.headers.get('Accept', '')):
            return jsonify({'ok': False, 'error': 'unauthenticated'}), 401
        return render_template('pages/use_portal.html', portal_url=REVAUTH_HOME_URL), 401

    if not _songsurf_running():
        _start_songsurf()
        return redirect(f'/watcher/loading?next=/{path}')

    return _proxy(user)


# ── Démarrage ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if DEV_MODE:
        mode = "DEV (sans authentification)"
    elif SONGSURF_PROXY_SECRET:
        mode = "PRODUCTION (porte du portail)"
    else:
        mode = "PRODUCTION (SONGSURF_PROXY_SECRET absent → service verrouillé)"
    logger.info(f"🚀 Watcher démarré — mode={mode}, target={TARGET_URL}")
    events_client.start_replay_thread()

    def _on_sigterm(signum, _frame):
        logger.info(f"🛑 Signal {signum} reçu — arrêt du watcher")
        sys.exit(0)
    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)
    # waitress : serveur de prod multi-thread (polling /api/status + proxy en streaming)
    serve(app, host='0.0.0.0', port=int(os.getenv('WATCHER_PORT', '8080')), threads=16)
