#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SongSurf Watcher — Portail d'authentification léger

Toujours actif (~15 MB RAM). Gère l'authentification admin et guest,
démarre/arrête le container SongSurf à la demande, et proxyfie toutes
les requêtes vers SongSurf une fois authentifié.

Variables d'environnement:
  WATCHER_PASSWORD        Mot de passe admin
  WATCHER_GUEST_PASSWORD  Mot de passe guest
  WATCHER_SECRET          Secret partagé avec SongSurf (OBLIGATOIRE en prod)
  ADMIN_LOGIN_PATH        URL du login admin          (défaut: /administrator)
  TARGET_CONTAINER        Nom du container SongSurf  (défaut: songsurf)
  TARGET_URL              URL interne de SongSurf    (défaut: http://songsurf:8080)
  INACTIVITY_TIMEOUT      Secondes sans activité avant auto-stop (défaut: 1800)
  FLASK_SECRET_KEY        Clé secrète Flask pour les sessions
"""

from flask import (Flask, request, session, redirect,
                   render_template, Response, stream_with_context, jsonify)
from datetime import datetime, timedelta
from functools import wraps
import threading
import time
import os
import secrets
import logging
import requests as req_lib
import docker as docker_sdk

# ── Configuration ─────────────────────────────────────────────────────────────
# login
app = Flask(__name__, template_folder='templates', static_folder=None)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(days=7)

WATCHER_PASSWORD       = os.getenv('WATCHER_PASSWORD', '')
WATCHER_GUEST_PASSWORD = os.getenv('WATCHER_GUEST_PASSWORD', '')
WATCHER_SECRET         = os.getenv('WATCHER_SECRET', secrets.token_hex(32))

ADMIN_LOGIN_PATH = os.getenv('ADMIN_LOGIN_PATH', '/administrator')
if not ADMIN_LOGIN_PATH.startswith('/'):
    ADMIN_LOGIN_PATH = '/' + ADMIN_LOGIN_PATH

TARGET_CONTAINER   = os.getenv('TARGET_CONTAINER', 'songsurf')
TARGET_URL         = os.getenv('TARGET_URL', 'http://songsurf:8080').rstrip('/')
INACTIVITY_TIMEOUT = int(os.getenv('INACTIVITY_TIMEOUT', '1800'))   # 30 min

MAX_ATTEMPTS     = 5
LOCKOUT_MINUTES  = 15

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHER] %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

# ── État global ───────────────────────────────────────────────────────────────

last_activity   = time.time()
activity_lock   = threading.Lock()

login_attempts  = {}   # ip → {'count': n, 'locked_until': datetime|None}
attempts_lock   = threading.Lock()

docker_client   = None
try:
    docker_client = docker_sdk.from_env()
    logger.info("✅ Docker socket connecté")
except Exception as e:
    logger.warning(f"⚠️  Docker socket indisponible: {e} — le contrôle auto est désactivé")

# ── Helpers : protection brute-force ─────────────────────────────────────────

def _client_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()

def _is_locked(ip):
    with attempts_lock:
        entry = login_attempts.get(ip, {})
        lu = entry.get('locked_until')
        return bool(lu and datetime.now() < lu)

def _lockout_remaining(ip):
    with attempts_lock:
        lu = login_attempts.get(ip, {}).get('locked_until')
        if lu:
            return max(1, int((lu - datetime.now()).total_seconds() / 60) + 1)
        return 0

def _record_fail(ip):
    with attempts_lock:
        entry = login_attempts.setdefault(ip, {'count': 0, 'locked_until': None})
        entry['count'] += 1
        if entry['count'] >= MAX_ATTEMPTS:
            entry['locked_until'] = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
            logger.warning(f"🔒 IP {ip} bloquée {LOCKOUT_MINUTES} min")

def _reset_fail(ip):
    with attempts_lock:
        login_attempts.pop(ip, None)

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
        return True   # assume running si pas de socket Docker
    c.reload()
    res = c.status == 'running'
    return res

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
        logger.info(f"⏹️  Arrêt de '{TARGET_CONTAINER}' (inactivité {INACTIVITY_TIMEOUT}s)")
        c.stop(timeout=15)

def _songsurf_ready(timeout=2):
    """Teste si SongSurf répond sur /ping."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = req_lib.get(f"{TARGET_URL}/ping", timeout=1.5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

# ── Thread d'inactivité ───────────────────────────────────────────────────────

def _update_activity():
    global last_activity
    with activity_lock:
        last_activity = time.time()

def _inactivity_watcher():
    """Background thread : arrête SongSurf après INACTIVITY_TIMEOUT secondes sans requête."""
    while True:
        time.sleep(60)
        with activity_lock:
            idle = time.time() - last_activity
        if idle >= INACTIVITY_TIMEOUT:
            if _songsurf_running():
                _stop_songsurf()

threading.Thread(target=_inactivity_watcher, daemon=True).start()

# ── Proxy ─────────────────────────────────────────────────────────────────────

# Headers qui ne doivent pas être transférés (hop-by-hop)
_HOP_HEADERS = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'host'
}

def _proxy():
    """Proxyfie la requête courante vers SongSurf avec enrichissement des headers."""
    _update_activity()

    # Construire les headers enrichis
    fwd_headers = {k: v for k, v in request.headers if k.lower() not in _HOP_HEADERS}
    fwd_headers['X-Watcher-Token']  = WATCHER_SECRET
    fwd_headers['X-User-Role']      = session.get('role', '')
    if session.get('role') == 'guest':
        fwd_headers['X-Guest-Session-Id'] = session.get('guest_id', '')
        fwd_headers['X-Guest-Name']       = session.get('guest_name', '')

    # URL cible : conserver le path + query string
    url = TARGET_URL + request.full_path.rstrip('?')

    try:
        resp = req_lib.request(
            method=request.method,
            url=url,
            headers=fwd_headers,
            data=request.get_data(),
            params={},            # déjà inclus dans full_path
            allow_redirects=False,
            stream=True,
            timeout=120,
        )
    except req_lib.exceptions.ConnectionError:
        # SongSurf pas encore prêt → page de chargement
        return redirect(f'/watcher/loading?next={request.path}')

    resp_headers = [(k, v) for k, v in resp.headers.items()
                    if k.lower() not in _HOP_HEADERS]

    return Response(
        stream_with_context(resp.iter_content(chunk_size=8192)),
        status=resp.status_code,
        headers=resp_headers,
        content_type=resp.headers.get('Content-Type', 'text/html'),
    )

# ── Routes Watcher (interceptées avant proxy) ─────────────────────────────────

@app.route(ADMIN_LOGIN_PATH, methods=['GET', 'POST'])
def admin_login():
    if session.get('role') == 'admin':
        return redirect('/')

    ip    = _client_ip()
    error = None

    if _is_locked(ip):
        return render_template('pages/login.html',
                               error=f'Trop de tentatives. Réessayez dans {_lockout_remaining(ip)} min.',
                               locked=True, is_guest=False)

    if request.method == 'POST':
        pwd = request.form.get('password', '')
        if WATCHER_PASSWORD and pwd == WATCHER_PASSWORD:
            session.clear()
            session.permanent = True
            session['role'] = 'admin'
            _reset_fail(ip)
            logger.info(f"✅ Login admin depuis {ip}")
            _start_songsurf()
            next_url = request.args.get('next', '/')
            if _songsurf_ready(timeout=3):
                return redirect(next_url)
            return redirect(f'/watcher/loading?next={next_url}')
        else:
            _record_fail(ip)
            if _is_locked(ip):
                error = f'Trop de tentatives. Réessayez dans {_lockout_remaining(ip)} min.'
            else:
                remaining = MAX_ATTEMPTS - login_attempts.get(ip, {}).get('count', 0)
                error = f'Mot de passe incorrect ({max(0, remaining)} essai{"s" if remaining > 1 else ""} restant{"s" if remaining > 1 else ""})'

    return render_template('pages/login.html', error=error, locked=_is_locked(ip),is_guest=False, admin_login_path=ADMIN_LOGIN_PATH)


@app.route('/guest/login', methods=['GET', 'POST'])
def guest_login():
    if session.get('role') in ('admin', 'guest'):
        return redirect('/')

    ip    = _client_ip()
    error = None

    if not WATCHER_GUEST_PASSWORD:
        return render_template('pages/login.html',
                               error="L'accès guest est désactivé.",
                               locked=True, is_guest=True)

    if _is_locked(ip):
        return render_template('pages/login.html',
                               error=f'Trop de tentatives. Réessayez dans {_lockout_remaining(ip)} min.',
                               locked=True, is_guest=True)

    if request.method == 'POST':
        pwd  = request.form.get('password', '')
        name = request.form.get('guest_name', '').strip()
        if pwd == WATCHER_GUEST_PASSWORD and name:
            session.clear()
            session.permanent = True
            session['role']       = 'guest'
            session['guest_id']   = secrets.token_hex(16)
            session['guest_name'] = name[:30]
            _reset_fail(ip)
            logger.info(f"✅ Login guest '{name}' depuis {ip}")
            _start_songsurf()
            if _songsurf_ready(timeout=3):
                return redirect('/guest')
            return redirect('/watcher/loading?next=/guest')
        else:
            _record_fail(ip)
            if _is_locked(ip):
                error = f'Trop de tentatives. Réessayez dans {_lockout_remaining(ip)} min.'
            else:
                error = 'Prénom ou mot de passe incorrect.'

    return render_template('pages/login.html', error=error, locked=_is_locked(ip), is_guest=True)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(ADMIN_LOGIN_PATH)


@app.route('/guest/logout')
def guest_logout():
    session.clear()
    return redirect('/guest/login')


@app.route('/watcher/loading')
def loading():
    next_url = request.args.get('next', '/')
    return render_template('pages/loading.html', next_url=next_url)


@app.route('/watcher/ready')
def watcher_ready():
    """Polling endpoint utilisé par la page de chargement."""
    ready = _songsurf_running() and _songsurf_ready(timeout=2)
    return jsonify({'ready': ready})


@app.route('/ping')
def ping():
    return 'pong', 200


# ── Catch-all proxy ───────────────────────────────────────────────────────────

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    # Routes système Watcher déjà gérées ci-dessus

    # Vérification auth
    role = session.get('role')
    if not role:
        if path.startswith('guest'):
            return redirect('/guest/login')
        return redirect(ADMIN_LOGIN_PATH)

    # SongSurf arrêté ? Le relancer et afficher la page de chargement
    if not _songsurf_running():
        _start_songsurf()
        return redirect(f'/watcher/loading?next=/{path}')

    return _proxy()


# ── Démarrage ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    logger.info(f"🚀 Watcher démarré — admin sur {ADMIN_LOGIN_PATH}, target={TARGET_URL}")
    app.run(host='0.0.0.0', port=8080, debug=False)
