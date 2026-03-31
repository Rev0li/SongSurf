#!/usr/bin/env bash
set -euo pipefail

# Global toggle:
#   DEPLOY_TARGET=local -> docker-compose.yml
#   DEPLOY_TARGET=nas   -> docker-compose.yml + docker-compose.nas.yml
TARGET="${DEPLOY_TARGET:-local}"
FILES=(-f docker-compose.yml)

case "$TARGET" in
  local)
    ;;
  nas|live|prod)
    FILES+=(-f docker-compose.nas.yml)
    ;;
  *)
    echo "[compose-switch] DEPLOY_TARGET invalide: '$TARGET' (attendu: local|nas)" >&2
    exit 2
    ;;
esac

echo "[compose-switch] mode=$TARGET"
exec docker compose "${FILES[@]}" "$@"
