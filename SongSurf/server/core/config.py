"""
Configuration du serveur : quota, dossiers de données, journaux.

Toujours lire ces valeurs par `config.X` (jamais `from core.config import X`) : les
dossiers restent ainsi modifiables à un seul endroit, notamment par les tests.
"""
import logging
import os
import sys
from pathlib import Path

# server/ : ce fichier est dans server/core/.
_SERVER_DIR = Path(__file__).parent.parent

# En Docker, events_client.py est copié à côté de app.py ;
# en dev local (make dev) il vit dans ../shared.
_SHARED_DIR = _SERVER_DIR.parent / 'shared'
if _SHARED_DIR.is_dir():
    sys.path.insert(0, str(_SHARED_DIR))
import events_client  # noqa: E402

DEV_MODE              = os.getenv('DEV_MODE', 'false').lower() == 'true'
# Preuve envoyée par Caddy dans X-Proxy-Token (porte du portail). Vide = verrouillé.
SONGSURF_PROXY_SECRET = os.getenv('SONGSURF_PROXY_SECRET', '')
# Espace membre du portail : redirection après /logout, lien de la page « passe par le portail »
REVAUTH_HOME_URL      = os.getenv('REVAUTH_HOME_URL', '')

# CORS : seule l'extension SongSurf Clip est autorisée (requêtes avec credentials).
# ID fixe, dérivé de la clé "key" de chrome-extension/manifest.json — il ne change
# pas selon le dossier de chargement. Jamais "null" ni chrome-extension://* (S1).
SONGSURF_EXTENSION_ID = 'ojhafabhkjjlganipbadmpifkikhnadf'
_CORS_ORIGINS = {f'chrome-extension://{SONGSURF_EXTENSION_ID}'}

# Quota par utilisateur et par jour (l'admin est illimité). 0 = illimité pour tous.
DAILY_DOWNLOAD_LIMIT = int(os.getenv('DAILY_DOWNLOAD_LIMIT', '50'))

# ── Directories ───────────────────────────────────────────────────────────────

if _SERVER_DIR == Path('/app'):
    BASE_MUSIC_DIR = Path('/data/music')
    TEMP_DIR       = Path('/data/temp')
    LOG_DIR        = Path('/app/logs')
    _cookies_dflt  = Path('/data/cookies')
    _state_dflt    = Path('/data/state')
else:
    _base          = _SERVER_DIR.parent
    BASE_MUSIC_DIR = _base / 'music'
    TEMP_DIR       = _base / 'temp'
    LOG_DIR        = _base / 'logs'
    _cookies_dflt  = _base / 'data' / 'cookies'
    _state_dflt    = _base / 'data' / 'state'

# Cookies YouTube par utilisateur (<uid>.txt), hors bibliothèque : l'export ZIP
# membre (qui supprime la bibliothèque) ne les emporte pas.
COOKIES_DIR = Path(os.environ.get('YTDLP_COOKIES_DIR') or _cookies_dflt)

# État persistant (file, quotas, exports ZIP) — SQLite, survit aux redémarrages (SSF-03).
STATE_DIR = Path(os.environ.get('SONGSURF_STATE_DIR') or _state_dflt)

for _d in [BASE_MUSIC_DIR, TEMP_DIR, LOG_DIR, COOKIES_DIR, STATE_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Push d'événements d'activité vers rev0auth (no-op si AUTH_EVENTS_URL absent)
events_client.init('songsurf', str(LOG_DIR / 'events-pending-songsurf.jsonl'))

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logger = logging.getLogger('songsurf')

_ah = logging.FileHandler(LOG_DIR / 'activity.log', encoding='utf-8')
_ah.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
activity_logger = logging.getLogger('songsurf.activity')
activity_logger.addHandler(_ah)
activity_logger.propagate = False
activity_logger.setLevel(logging.INFO)

_dlh = logging.FileHandler(LOG_DIR / 'downloads.log', encoding='utf-8')
_dlh.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
dl_logger = logging.getLogger('songsurf.downloads')
dl_logger.addHandler(_dlh)
dl_logger.propagate = False
dl_logger.setLevel(logging.INFO)
