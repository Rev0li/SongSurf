#!/usr/bin/env bash
# SongSurf — interactive wizard to generate .env (config) and .secrets (key material).
#
# Auto-generates : Flask session keys, WATCHER_SECRET (64-char hex via openssl)
# Prompts user   : passwords, deployment config, limits, optional URLs and addresses
#
# Safe to re-run : existing files are never silently overwritten.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

ok()   { echo -e "${GREEN}[ok]${NC}  $*"; }
warn() { echo -e "${YELLOW}[!!]${NC}  $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }
info() { echo -e "${CYAN}[..]${NC}  $*"; }
dim()  { echo -e "${DIM}      $*${NC}"; }
title(){ echo -e "\n${BOLD}── $* ${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT/.env"
SECRETS_FILE="$ROOT/.secrets"

# ── Helpers ───────────────────────────────────────────────────────────────────

gen_hex() {
  if command -v openssl &>/dev/null; then
    openssl rand -hex 32
  else
    python3 -c "import secrets; print(secrets.token_hex(32))"
  fi
}

# Read a non-empty value (hidden input for passwords)
prompt_required() {
  local label="$1" hidden="${2:-false}" var
  while true; do
    printf "  %s : " "$label" >/dev/tty
    if [[ "$hidden" == "true" ]]; then
      read -rs var </dev/tty; echo >/dev/tty
    else
      read -r var </dev/tty
    fi
    [[ -n "$var" ]] && break
    warn "Ce champ est obligatoire."
  done
  printf '%s' "$var"
}

# Read an optional value with a default
prompt_optional() {
  local label="$1" default="${2:-}" var
  if [[ -n "$default" ]]; then
    printf "  %s [%s] : " "$label" "$default" >/dev/tty
  else
    printf "  %s [laisser vide] : " "$label" >/dev/tty
  fi
  read -r var </dev/tty
  printf '%s' "${var:-$default}"
}

# Yes/No prompt — returns "true" or "false"
prompt_bool() {
  local label="$1" default="${2:-N}" ans
  printf "  %s [o/N, défaut=%s] : " "$label" "$default" >/dev/tty
  read -r ans </dev/tty
  if [[ "$ans" =~ ^[Oo]$ ]]; then echo "true"; else echo "false"; fi
}

confirm_overwrite() {
  local file="$1"
  printf "${YELLOW}[!!]${NC}  %s existe déjà. Écraser ? [o/N] : " "$file" >/dev/tty
  read -r ans </dev/tty
  [[ "$ans" =~ ^[Oo]$ ]]
}

# ── Header ────────────────────────────────────────────────────────────────────

clear
echo ""
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
echo -e "${BOLD}  SongSurf — wizard de configuration${NC}"
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
echo ""
echo "  Ce wizard génère deux fichiers :"
echo -e "  ${CYAN}.env${NC}     — configuration non-secrète  (chmod 644)"
echo -e "  ${CYAN}.secrets${NC} — mots de passe et clés      (chmod 600, ne JAMAIS committer)"
echo ""
echo "  Les clés cryptographiques sont auto-générées via openssl."
echo "  Tu n'as qu'à renseigner les mots de passe et les options."
echo ""

# ── Guard : fichiers existants ────────────────────────────────────────────────

WRITE_ENV=true
WRITE_SECRETS=true

if [[ -f "$ENV_FILE" ]]; then
  confirm_overwrite ".env" || WRITE_ENV=false
fi
if [[ -f "$SECRETS_FILE" ]]; then
  confirm_overwrite ".secrets" || WRITE_SECRETS=false
fi

if ! $WRITE_ENV && ! $WRITE_SECRETS; then
  warn "Rien à faire — les deux fichiers sont conservés."
  exit 0
fi

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Déploiement
# ═════════════════════════════════════════════════════════════════════════════

title "1/6 · Déploiement & Ports"
dim "local = bridge Docker, ports sur localhost  (développement)"
dim "nas   = network_mode host, accès direct NAS  (production)"
echo ""
printf "  Mode [1=local / 2=nas, défaut=1] : " >/dev/tty
read -r choice </dev/tty
case "$choice" in
  2) DEPLOY_TARGET="nas" ;;
  *) DEPLOY_TARGET="local" ;;
esac
ok "DEPLOY_TARGET=$DEPLOY_TARGET"

echo ""
dim "  Watcher = proxy d'auth, port exposé à l'extérieur (VPS / browser)"
dim "  SongSurf = moteur de téléchargement, port interne uniquement"
WATCHER_PORT=$(prompt_optional "Port Watcher (externe)" "8080")
SONGSURF_PORT=$(prompt_optional "Port SongSurf (interne)" "8081")

# Calcul automatique des TARGET_URL selon le mode et SONGSURF_PORT
TARGET_URL="http://songsurf:${SONGSURF_PORT}"
TARGET_URL_NAS="http://localhost:${SONGSURF_PORT}"

ok "Watcher    : :${WATCHER_PORT}"
ok "SongSurf   : :${SONGSURF_PORT} (interne)"
ok "TARGET_URL : ${TARGET_URL}  (local) / ${TARGET_URL_NAS}  (nas)"

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Mots de passe (obligatoires)
# ═════════════════════════════════════════════════════════════════════════════

title "2/6 · Auth JWT (rev0auth)"
dim "L'authentification est gérée par rev0auth (VPS). Aucun mot de passe local."
dim "Renseigne AUTH_SERVICE_LOGIN_URL + AUTH_JWT_SECRET dans la section 5."
ok "Pas de mot de passe local — auth déléguée à rev0auth"

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Limites téléchargement
# ═════════════════════════════════════════════════════════════════════════════

title "3/6 · Limites"
dim "Laisse vide pour utiliser les valeurs par défaut."
echo ""

DAILY_DOWNLOAD_LIMIT=$(prompt_optional "Limite téléchargements admin / jour (0 = illimité)" "50")
ok "DAILY_DOWNLOAD_LIMIT=$DAILY_DOWNLOAD_LIMIT"

MAX_DURATION_SECONDS=$(prompt_optional "Durée max d'une vidéo en secondes (0 = illimité)" "9000")
ok "MAX_DURATION_SECONDS=${MAX_DURATION_SECONDS}s ($(( MAX_DURATION_SECONDS / 60 )) min)"

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Inactivité
# ═════════════════════════════════════════════════════════════════════════════

title "4/6 · Arrêt automatique (inactivité)"
dim "Watcher coupe SongSurf après WARN + GRACE secondes sans activité."
dim "Défauts : avertissement 3600s (1h), délai de grâce 900s (15min)."
echo ""

INACTIVITY_WARN=$(prompt_optional "Avertissement après (s)" "3600")
INACTIVITY_GRACE=$(prompt_optional "Arrêt forcé après + (s)" "900")
ok "Inactivité : avertissement ${INACTIVITY_WARN}s, grâce ${INACTIVITY_GRACE}s"

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Auth Phase 3 (rev0auth / JWT)
# ═════════════════════════════════════════════════════════════════════════════

title "5/6 · Auth JWT — rev0auth (Phase 3)"
dim "Laisse vide si rev0auth n'est pas encore en ligne."
dim "Quand actif : AUTH_JWT_SECRET doit être identique dans SongSurf et rev0auth."
echo ""

DEV_MODE=$(prompt_bool "Activer DEV_MODE (bypass JWT — JAMAIS en prod)" "N")
if [[ "$DEV_MODE" == "true" ]]; then
  warn "DEV_MODE=true : toute l'auth JWT est désactivée. N'utilise PAS ça en production !"
fi
ok "DEV_MODE=$DEV_MODE"

AUTH_SERVICE_LOGIN_URL=$(prompt_optional "AUTH_SERVICE_LOGIN_URL (URL login rev0auth)" "")

echo ""
dim "JWT secret : laisse vide pour auto-générer (à copier dans rev0auth quand tu l'actives)."
printf "  AUTH_JWT_SECRET [auto-générer] : " >/dev/tty
read -rs JWT_INPUT </dev/tty; echo >/dev/tty
if [[ -z "$JWT_INPUT" ]]; then
  AUTH_JWT_SECRET=$(gen_hex)
  dim "  → auto-généré. Copie-le dans rev0auth quand tu actives la Phase 3."
else
  AUTH_JWT_SECRET="$JWT_INPUT"
fi
ok "AUTH_JWT_SECRET défini"

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Adresses donation (optionnel)
# ═════════════════════════════════════════════════════════════════════════════

title "6/6 · Adresses donation (optionnel)"
dim "Laisse vide pour désactiver la page donation."
echo ""

DONATION_BTC=$(prompt_optional "Adresse BTC" "")
DONATION_ETH=$(prompt_optional "Adresse ETH" "")
DONATION_SOL=$(prompt_optional "Adresse SOL" "")
DONATION_XMR=$(prompt_optional "Adresse XMR" "")

# ═════════════════════════════════════════════════════════════════════════════
# Génération des clés cryptographiques
# ═════════════════════════════════════════════════════════════════════════════

echo ""
info "Génération des clés cryptographiques (openssl rand -hex 32)..."
WATCHER_FLASK_SECRET_KEY=$(gen_hex)
SONGSURF_FLASK_SECRET_KEY=$(gen_hex)
WATCHER_SECRET=$(gen_hex)
ok "3 clés générées (64 caractères hex chacune)"

# ═════════════════════════════════════════════════════════════════════════════
# Écriture .env
# ═════════════════════════════════════════════════════════════════════════════

if $WRITE_ENV; then
  cat > "$ENV_FILE" <<EOF
# SongSurf — configuration
# Généré le : $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Config non-secrète. Le matériel de clés est dans .secrets (chmod 600).

# ── Déploiement ────────────────────────────────────────────────────────────
# local = bridge Docker, ports publiés en localhost (développement)
# nas   = network_mode host, réseau direct NAS (production)
DEPLOY_TARGET=${DEPLOY_TARGET}
WATCHER_PORT=${WATCHER_PORT}
SONGSURF_PORT=${SONGSURF_PORT}

# ── Routage interne (calculé automatiquement depuis SONGSURF_PORT) ─────────
TARGET_URL=${TARGET_URL}
TARGET_URL_NAS=${TARGET_URL_NAS}

# ── Limites téléchargement ────────────────────────────────────────────────
# 0 = illimité
DAILY_DOWNLOAD_LIMIT=${DAILY_DOWNLOAD_LIMIT}
MAX_DURATION_SECONDS=${MAX_DURATION_SECONDS}

# ── Arrêt automatique (inactivité) ────────────────────────────────────────
INACTIVITY_WARN_TIMEOUT=${INACTIVITY_WARN}
INACTIVITY_GRACE_TIMEOUT=${INACTIVITY_GRACE}

# ── Mode dev ─────────────────────────────────────────────────────────────
# true = bypass complet de l'auth JWT — JAMAIS en production
DEV_MODE=${DEV_MODE}

# ── Auth JWT — Phase 3 (rev0auth) ─────────────────────────────────────────
# Laisser vide désactive l'intégration JWT (authentification par mot de passe seule).
AUTH_SERVICE_LOGIN_URL=${AUTH_SERVICE_LOGIN_URL}

# ── Adresses donation (optionnel) ─────────────────────────────────────────
DONATION_BTC=${DONATION_BTC}
DONATION_ETH=${DONATION_ETH}
DONATION_SOL=${DONATION_SOL}
DONATION_XMR=${DONATION_XMR}
EOF
  chmod 644 "$ENV_FILE"
  ok ".env écrit (644)"
fi

# ═════════════════════════════════════════════════════════════════════════════
# Écriture .secrets
# ═════════════════════════════════════════════════════════════════════════════

if $WRITE_SECRETS; then
  cat > "$SECRETS_FILE" <<EOF
# SongSurf — matériel de clés secret
# Généré le : $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# NE PAS committer. NE PAS partager. NE PAS logger.
# Chargé automatiquement par Docker Compose via env_file.

# ── Clés de session Flask (auto-générées) ─────────────────────────────────
WATCHER_FLASK_SECRET_KEY=${WATCHER_FLASK_SECRET_KEY}
SONGSURF_FLASK_SECRET_KEY=${SONGSURF_FLASK_SECRET_KEY}

# ── Secret partagé Watcher ↔ SongSurf (auto-généré) ──────────────────────
WATCHER_SECRET=${WATCHER_SECRET}

# ── Secret JWT — doit correspondre à AUTH_JWT_SECRET dans rev0auth ────────
AUTH_JWT_SECRET=${AUTH_JWT_SECRET}

EOF
  chmod 600 "$SECRETS_FILE"
  ok ".secrets écrit (600)"
fi

# ═════════════════════════════════════════════════════════════════════════════
# Récapitulatif
# ═════════════════════════════════════════════════════════════════════════════

echo ""
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}Configuration générée avec succès.${NC}"
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
echo ""
echo "  Fichiers créés :"
[[ -f "$ENV_FILE" ]]     && echo -e "    ${CYAN}.env${NC}     — configuration      (644)"
[[ -f "$SECRETS_FILE" ]] && echo -e "    ${CYAN}.secrets${NC} — clés et mots passe  (600) ${RED}← ne jamais committer${NC}"
echo ""
echo -e "  Récapitulatif :"
echo "    Déploiement    : $DEPLOY_TARGET"
echo "    Ports          : Watcher :${WATCHER_PORT}  →  SongSurf :${SONGSURF_PORT} (interne)"
echo "    DEV_MODE       : $DEV_MODE"
echo "    Limite /jour   : ${DAILY_DOWNLOAD_LIMIT} téléchargements (0=illimité)"
echo "    Durée max      : ${MAX_DURATION_SECONDS}s ($(( MAX_DURATION_SECONDS / 60 )) min)"
echo "    Inactivité     : avertissement ${INACTIVITY_WARN}s + arrêt ${INACTIVITY_GRACE}s"
[[ -n "$AUTH_SERVICE_LOGIN_URL" ]] && echo "    rev0auth       : $AUTH_SERVICE_LOGIN_URL"
echo ""
echo -e "  Prochaine étape : ${BOLD}make up${NC}"

if [[ "$DEV_MODE" == "false" ]] && [[ -n "$AUTH_SERVICE_LOGIN_URL" ]]; then
  echo ""
  warn "Phase 3 active : vérifie que AUTH_JWT_SECRET est identique dans .secrets et rev0auth avant de déployer."
fi

if [[ "$DEV_MODE" == "true" ]]; then
  echo ""
  warn "DEV_MODE=true est actif — l'auth JWT est désactivée. Ne déploie PAS cette config en production."
fi

echo ""
