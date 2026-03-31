#!/usr/bin/env bash
set -euo pipefail

# Global toggle:
#   DEPLOY_TARGET=local -> docker-compose.yml
#   DEPLOY_TARGET=nas   -> docker-compose.yml + docker-compose.nas.yml
TARGET="${DEPLOY_TARGET:-local}"
FILES=(-f docker-compose.yml)

# Prefer docker-compose binary on NAS when available, then validate docker compose plugin.
if command -v docker-compose >/dev/null 2>&1 \
  && docker-compose -f docker-compose.yml config >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
elif docker compose -f docker-compose.yml config >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
else
  echo "[compose-switch] Aucun moteur Compose trouvé. Installe 'docker compose' (plugin v2) ou 'docker-compose'." >&2
  exit 3
fi

case "$TARGET" in
  local)
    FILES+=(-f docker-compose.local.yml)
    ;;
  nas|live|prod)
    FILES+=(-f docker-compose.nas.yml)
    ;;
  *)
    echo "[compose-switch] DEPLOY_TARGET invalide: '$TARGET' (attendu: local|nas)" >&2
    exit 2
    ;;
esac

echo "[compose-switch] mode=$TARGET engine=${COMPOSE_CMD[*]}"
exec "${COMPOSE_CMD[@]}" "${FILES[@]}" "$@"
