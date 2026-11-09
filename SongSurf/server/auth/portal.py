"""
Porte du portail : identité envoyée par Caddy, avec la preuve X-Proxy-Token.
"""
import hmac

from flask import request

from core import config
from core.config import logger


def user_from_portal_headers() -> dict | None:
    """Identité posée par Caddy après vérification de la session par le portail.

    Fiable uniquement si X-Proxy-Token prouve que la requête vient de Caddy :
    SongSurf écoute sur le réseau local, n'importe quel appareil pourrait sinon
    se déclarer admin. Caddy retire les X-User-* envoyés par le client.
    """
    if not config.SONGSURF_PROXY_SECRET:
        return None
    proof = request.headers.get('X-Proxy-Token', '')
    if not proof:
        return None
    if not hmac.compare_digest(proof.encode(), config.SONGSURF_PROXY_SECRET.encode()):
        # Preuve présente mais fausse : secret désynchronisé avec Caddy, ou forge
        logger.warning("⚠️  X-Proxy-Token invalide — en-têtes d'identité ignorés")
        return None
    name = request.headers.get('X-User-Name', '').strip()
    role = request.headers.get('X-User-Role', '').strip().lower()
    if not name or not role:
        return None
    return {
        'sub':   name,                                          # pseudo : affichage, logs, .owner
        'uid':   request.headers.get('X-User-Id', '').strip(),  # UUID du portail : clé de stockage
        'role':  role,
    }
