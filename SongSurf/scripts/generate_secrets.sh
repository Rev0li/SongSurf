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

title "2/6 · Auth (porte du portail)"
dim "L'authentification est faite par le portail rev0auth, devant SongSurf (Caddy)."
dim "Aucun mot de passe local. Renseigne REVAUTH_HOME_URL + SONGSURF_PROXY_SECRET en section 5."
ok "Pas de mot de passe local — auth déléguée au portail"

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Limites téléchargement
# ═════════════════════════════════════════════════════════════════════════════

title "3/6 · Limites"
dim "Laisse vide pour utiliser les valeurs par défaut."
echo ""

DAILY_DOWNLOAD_LIMIT=$(prompt_optional "Limite téléchargements par membre / jour, admin illimité (0 = illimité)" "50")
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
# SECTION 5 — Auth (porte du portail rev0auth)
# ═════════════════════════════════════════════════════════════════════════════

title "5/6 · Auth — porte du portail rev0auth"
dim "Caddy vérifie la session auprès du portail et prouve l'identité au Watcher"
dim "avec SONGSURF_PROXY_SECRET (même valeur côté VPS)."
echo ""

DEV_MODE=$(prompt_bool "Activer DEV_MODE (sans auth — JAMAIS en prod)" "N")
if [[ "$DEV_MODE" == "true" ]]; then
  warn "DEV_MODE=true : toute l'auth est désactivée. N'utilise PAS ça en production !"
fi
ok "DEV_MODE=$DEV_MODE"

REVAUTH_HOME_URL=$(prompt_optional "REVAUTH_HOME_URL (espace membre du portail, retour après logout)" "")
ADMIN_UID=$(prompt_optional "ADMIN_UID (UUID du compte admin du portail, requis sur le NAS)" "")

echo ""
dim "Événements d'activité (optionnel) : le NAS pousse téléchargements/conteneur"
dim "vers le dashboard admin rev0auth. Laisse l'URL vide pour désactiver."
if [[ -n "$REVAUTH_HOME_URL" ]]; then
  _EVENTS_DEFAULT="$(echo "$REVAUTH_HOME_URL" | sed -E 's#^(https?://[^/]+).*#\1#')/japprends/api/songsurf-events"
else
  _EVENTS_DEFAULT=""
fi
AUTH_EVENTS_URL=$(prompt_optional "AUTH_EVENTS_URL (endpoint d'ingestion rev0auth)" "$_EVENTS_DEFAULT")

printf "  SONGSURF_EVENTS_SECRET [auto-générer] : " >/dev/tty
read -rs EVENTS_INPUT </dev/tty; echo >/dev/tty
if [[ -z "$EVENTS_INPUT" ]]; then
  SONGSURF_EVENTS_SECRET=$(gen_hex)
  dim "  → auto-généré. Copie-le dans auth/.secrets côté VPS."
else
  SONGSURF_EVENTS_SECRET="$EVENTS_INPUT"
fi
ok "SONGSURF_EVENTS_SECRET défini"

echo ""
dim "Porte du portail (Caddy forward_auth) : preuve envoyée par Caddy dans X-Proxy-Token."
printf "  SONGSURF_PROXY_SECRET [auto-générer] : " >/dev/tty
read -rs PROXY_INPUT </dev/tty; echo >/dev/tty
if [[ -z "$PROXY_INPUT" ]]; then
  SONGSURF_PROXY_SECRET=$(gen_hex)
  dim "  → auto-généré. Copie-le dans le fichier secret lu par Caddy côté VPS."
else
  SONGSURF_PROXY_SECRET="$PROXY_INPUT"
fi
ok "SONGSURF_PROXY_SECRET défini"

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
# Titres par membre et par jour (admin illimité). 0 = illimité
DAILY_DOWNLOAD_LIMIT=${DAILY_DOWNLOAD_LIMIT}
MAX_DURATION_SECONDS=${MAX_DURATION_SECONDS}

# ── Arrêt automatique (inactivité) ────────────────────────────────────────
INACTIVITY_WARN_TIMEOUT=${INACTIVITY_WARN}
INACTIVITY_GRACE_TIMEOUT=${INACTIVITY_GRACE}

# ── Mode dev ─────────────────────────────────────────────────────────────
# true = aucune authentification — JAMAIS en production
DEV_MODE=${DEV_MODE}

# ── Portail rev0auth ──────────────────────────────────────────────────────
# Espace membre du portail : retour après "← Mon espace" (logout)
REVAUTH_HOME_URL=${REVAUTH_HOME_URL}
# UUID du compte admin du portail — la musique Jellyfin est montée sur /data/music/<ADMIN_UID>
ADMIN_UID=${ADMIN_UID}

# ── Événements d'activité poussés vers rev0auth ───────────────────────────
# Vide = tracking désactivé. Secret associé : SONGSURF_EVENTS_SECRET (.secrets).
AUTH_EVENTS_URL=${AUTH_EVENTS_URL}

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

# ── Secret événements — doit correspondre à SONGSURF_EVENTS_SECRET ────────
# dans auth/.secrets (VPS). Rotation = mise à jour des deux + restart des deux stacks.
SONGSURF_EVENTS_SECRET=${SONGSURF_EVENTS_SECRET}

# ── Preuve de la porte du portail — doit correspondre au secret lu par ────
# Caddy (en-tête X-Proxy-Token). Vide = service verrouillé (sauf DEV_MODE).
SONGSURF_PROXY_SECRET=${SONGSURF_PROXY_SECRET}

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
[[ -n "$REVAUTH_HOME_URL" ]] && echo "    Portail        : $REVAUTH_HOME_URL"
echo ""
echo -e "  Prochaine étape : ${BOLD}make up${NC}"

if [[ "$DEV_MODE" == "false" ]]; then
  echo ""
  warn "Prod : SONGSURF_PROXY_SECRET doit être identique dans .secrets et dans le secret lu par Caddy (VPS)."
fi

if [[ -n "$AUTH_EVENTS_URL" ]]; then
  echo ""
  warn "Événements actifs : SONGSURF_EVENTS_SECRET doit être identique dans auth/.secrets (VPS)."
fi

if [[ "$DEV_MODE" == "true" ]]; then
  echo ""
  warn "DEV_MODE=true est actif — l'auth est désactivée. Ne déploie PAS cette config en production."
fi

echo ""
