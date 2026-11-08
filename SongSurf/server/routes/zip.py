"""
Export ZIP de la bibliothèque d'un membre : préparer, suivre, télécharger.
"""
import os
import shutil
import threading
import zipfile
from pathlib import Path

from flask import Blueprint, Response, jsonify

from auth.provider import auth_required, get_current_user
from core import config, queue
from core.config import logger
from core.storage import _user_key, _user_music_dir, _user_pseudo

import events_client

zip_bp = Blueprint('zip', __name__)


# ── ZIP ────────────────────────────────────────────────────────────────────────
# Export en arrière-plan (SSF-03) : /api/prepare-zip lance la construction et répond
# tout de suite, le frontend suit l'avancement via /api/zip-status puis télécharge
# /api/download-zip. L'état vit dans SQLite : un ZIP prêt survit à un redémarrage,
# un ZIP interrompu est signalé (state_store._recover).

ZIP_DISABLED_MSG = "Export ZIP désactivé pour cette bibliothèque."
_zip_start_lock  = threading.Lock()   # une seule construction à la fois par utilisateur


def _zip_forbidden(user: dict, music_dir: Path) -> bool:
    """Export ZIP refusé pour la bibliothèque admin, qui est permanente (décision SSF-10).

    Vérifié sur le rôle ET sur le dossier : l'export vide la bibliothèque après le
    téléchargement, il ne doit jamais viser la racine musique ni un point de montage
    (la bibliothèque admin est la musique Jellyfin montée dans /data/music/<uid>).
    """
    if user.get('role') == 'admin':
        return True
    target = music_dir.resolve()
    return target == config.BASE_MUSIC_DIR.resolve() or _is_mount_point(target)


def _is_mount_point(path: Path) -> bool:
    """os.path.ismount ne voit pas un bind mount venant du même disque (cas du NAS) :
    on consulte aussi la table des montages du conteneur."""
    if os.path.ismount(path):
        return True
    try:
        with open('/proc/self/mountinfo', encoding='utf-8') as f:
            points = {line.split()[4].encode().decode('unicode_escape') for line in f}
    except OSError:
        return False
    return str(path) in points


def _zip_path(user_key: str) -> Path:
    return config.TEMP_DIR / f"songsurf_{user_key}.zip"


def _zip_public(state: dict | None) -> dict:
    """État ZIP renvoyé au frontend (jamais le chemin sur le serveur)."""
    if not state:
        return {'status': 'idle'}
    out = {
        'status':  state['status'],
        'done':    state['done'],
        'total':   state['total'],
        'count':   state['total'],
        'size_mb': state['size_mb'],
    }
    if state['status'] == 'error':
        out['error'] = state['error']
    if state['status'] == 'ready':
        out['download_url'] = '/api/download-zip'
    return out


def _build_zip(user_key: str, music_dir: Path, files: list, zip_path: Path) -> None:
    """Thread : écrit le ZIP dans un .part puis le renomme, en publiant l'avancement."""
    part = zip_path.with_name(zip_path.name + '.part')
    try:
        with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, f in enumerate(files, 1):
                if f.is_file():  # déplacé/supprimé pendant la construction → ignoré
                    zf.write(f, f.relative_to(music_dir))
                if i % 5 == 0 or i == len(files):
                    queue.store.zip_set(user_key, status='building', done=i)
        part.replace(zip_path)
        size_mb = round(zip_path.stat().st_size / (1024 * 1024), 1)
        queue.store.zip_set(user_key, status='ready', done=len(files), size_mb=size_mb)
        logger.info(f"📦 ZIP prêt: {len(files)} fichiers, {size_mb:.1f} MB [{user_key[:8]}]")
    except Exception as e:
        part.unlink(missing_ok=True)
        queue.store.zip_set(user_key, status='error', error=str(e))
        logger.error(f"❌ Construction ZIP [{user_key[:8]}]: {e}")


@zip_bp.route('/api/prepare-zip', methods=['POST'])
@auth_required
def prepare_zip():
    try:
        user      = get_current_user()
        key       = _user_key(user)
        music_dir = _user_music_dir(user)
        if _zip_forbidden(user, music_dir):
            return jsonify({'success': False, 'error': ZIP_DISABLED_MSG, 'code': 'zip_disabled'}), 403
        with _zip_start_lock:
            current = queue.store.zip_get(key)
            if current and current['status'] == 'building':
                return jsonify({'success': True, **_zip_public(current)}), 202
            files = sorted([p for p in music_dir.rglob('*.mp3') if p.is_file()],
                           key=lambda p: p.stat().st_mtime, reverse=True)
            if not files:
                return jsonify({'success': False, 'error': 'Aucune musique disponible'}), 404
            zip_path = _zip_path(key)
            zip_path.unlink(missing_ok=True)
            queue.store.zip_set(key, status='building', zip_path=str(zip_path),
                          done=0, total=len(files), size_mb=0, error='')
        threading.Thread(target=_build_zip, args=(key, music_dir, files, zip_path),
                         daemon=True).start()
        return jsonify({'success': True, **_zip_public(queue.store.zip_get(key))}), 202
    except Exception as e:
        logger.error(f"❌ /api/prepare-zip: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@zip_bp.route('/api/zip-status')
@auth_required
def zip_status():
    """Avancement de l'export ZIP de l'appelant : idle | building | ready | error."""
    key   = _user_key(get_current_user())
    state = queue.store.zip_get(key)
    if state and state['status'] == 'ready' and not Path(state['zip_path']).is_file():
        queue.store.zip_delete(key)   # fichier disparu (config.TEMP_DIR nettoyé) → plus rien à récupérer
        state = None
    return jsonify({'success': True, **_zip_public(state)})


@zip_bp.route('/api/download-zip')
@auth_required
def download_zip():
    user      = get_current_user()
    key       = _user_key(user)
    music_dir = _user_music_dir(user)
    if _zip_forbidden(user, music_dir):
        return jsonify({'success': False, 'error': ZIP_DISABLED_MSG, 'code': 'zip_disabled'}), 403
    state = queue.store.zip_get(key)
    if not state or state['status'] != 'ready':
        return jsonify({'success': False, 'error': 'ZIP non prêt, utilisez /api/prepare-zip'}), 404

    zip_path = Path(state['zip_path'])
    if not zip_path.exists():
        return jsonify({'success': False, 'error': 'ZIP introuvable'}), 404

    _pseudo   = _user_pseudo(user)
    _role     = user.get('role', '')
    _zip_meta = {'count': state['total'], 'size_mb': state['size_mb']}
    file_size = zip_path.stat().st_size

    def _after_full_export():
        try:
            zip_path.unlink(missing_ok=True)
            queue.store.zip_delete(key)
            # Bibliothèque membre = temporaire, supprimée après export. Jamais le
            # dossier admin ni la racine : refusés en amont, revérifiés ici (SSF-10).
            purged = not _zip_forbidden(user, music_dir) and music_dir.exists()
            if purged:
                shutil.rmtree(music_dir, ignore_errors=True)
                logger.info(f"🗑️ Bibliothèque supprimée post-ZIP [{key[:8]}]")
            events_client.emit(
                'zip_export',
                pseudo=_pseudo,
                role=_role,
                detail={**_zip_meta, 'library_purged': purged},
            )
        except Exception as e:
            logger.warning(f"⚠️ Post-download cleanup: {e}")

    def _stream_and_cleanup():
        sent = 0
        try:
            with open(zip_path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    yield chunk
                    sent += len(chunk)
        finally:
            # Appelé par le WSGI quand le stream est terminé OU la connexion coupée
            # (GeneratorExit sur le yield). Interrompu (réseau, écran verrouillé sur
            # mobile…) → on ne touche à rien : bibliothèque intacte, ZIP toujours prêt
            # à être récupéré (SSF-14).
            if sent >= file_size:
                _after_full_export()
            else:
                logger.warning(f"⚠️ Export ZIP interrompu ({sent}/{file_size} octets) — "
                               f"bibliothèque conservée [{key[:8]}]")

    return Response(
        _stream_and_cleanup(),
        mimetype='application/zip',
        headers={
            'Content-Disposition': 'attachment; filename=SongSurf_musiques.zip',
            'Content-Length': file_size,
        },
    )
