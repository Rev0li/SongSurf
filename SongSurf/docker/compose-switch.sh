#!/usr/bin/env bash
set -euo pipefail

# Global toggle (branche `locale` : local = standalone, sans watcher):
#   DEPLOY_TARGET=local -> docker-compose.standalone.yml (SongSurf seul, DEV_MODE)
#   DEPLOY_TARGET=full  -> docker-compose.yml + docker-compose.local.yml (stack complète)
#   DEPLOY_TARGET=nas   -> docker-compose.yml + docker-compose.nas.yml
TARGET="${DEPLOY_TARGET:-local}"
FILES=(-f docker-compose.yml)

# --- CORRECTION : Priorité à 'docker compose' (V2) ---
# On teste d'abord si la commande moderne "docker compose" fonctionne
if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
# Sinon, on regarde si l'ancien "docker-compose" est là
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "[compose-switch] Aucun moteur Compose trouvé. Installe 'docker compose' (plugin v2) ou 'docker-compose'." >&2
    exit 3
fi

case "$TARGET" in
    local)
        # Standalone : SongSurf seul, remplace entièrement la base (pas de watcher)
        FILES=(-f docker-compose.standalone.yml)
        ;;
    full)
        # Stack complète watcher + songsurf (ancien mode local)
        if [ -f docker-compose.local.yml ]; then
            FILES+=(-f docker-compose.local.yml)
        fi
        ;;
    nas|live|prod)
        FILES+=(-f docker-compose.nas.yml)
        ;;
    *)
        echo "[compose-switch] DEPLOY_TARGET invalide: '$TARGET' (attendu: local|full|nas)" >&2
        exit 2
        ;;
esac

echo "[compose-switch] mode=$TARGET engine=${COMPOSE_CMD[*]}"

# On utilise exec pour remplacer le processus shell par docker compose
exec "${COMPOSE_CMD[@]}" "${FILES[@]}" "$@"
