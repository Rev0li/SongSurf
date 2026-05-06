#!/usr/bin/env bash
# Generate .env (config) and .secrets (key material, chmod 600) for SongSurf.
#
# Auto-generates: all hex/crypto keys
# Prompts user for: passwords, external URLs, optional donation addresses
#
# Safe to re-run: existing files are never silently overwritten.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; DIM='\033[2m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[ok]${NC}  $*"; }
warn() { echo -e "${YELLOW}[!!]${NC}  $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }
info() { echo -e "${CYAN}[..]${NC}  $*"; }
dim()  { echo -e "${DIM}$*${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT/.env"
SECRETS_FILE="$ROOT/.secrets"

# ── Helpers ──────────────────────────────────────────────────────────────────

gen_hex() {
  # 32 bytes = 64 hex chars. Uses openssl if available, falls back to python3.
  if command -v openssl &>/dev/null; then
    openssl rand -hex 32
  else
    python3 -c "import secrets; print(secrets.token_hex(32))"
  fi
}

prompt_password() {
  local label="$1" var
  while true; do
    printf "  %s: " "$label"
    read -rs var; echo
    [ -n "$var" ] && break
    warn "Cannot be empty."
  done
  echo "$var"
}

prompt_optional() {
  local label="$1" default="${2:-}"
  printf "  %s [%s]: " "$label" "${default:-leave empty}"
  read -r var
  echo "${var:-$default}"
}

confirm_overwrite() {
  local file="$1"
  printf "${YELLOW}[!!]${NC}  %s already exists. Overwrite? [y/N] " "$file"
  read -r ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

# ── Header ───────────────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════"
echo "  SongSurf — secrets & env generator"
echo "══════════════════════════════════════════════"
echo ""
echo "  This script creates two files:"
echo "  • .env     → non-secret configuration"
echo "  • .secrets → all key material (chmod 600)"
echo ""
echo "  Hex keys are auto-generated with openssl."
echo "  You only need to provide passwords and URLs."
echo ""

# ── Guard: existing files ────────────────────────────────────────────────────

WRITE_ENV=true
WRITE_SECRETS=true

if [ -f "$ENV_FILE" ]; then
  confirm_overwrite ".env" || WRITE_ENV=false
fi
if [ -f "$SECRETS_FILE" ]; then
  confirm_overwrite ".secrets" || WRITE_SECRETS=false
fi

if ! $WRITE_ENV && ! $WRITE_SECRETS; then
  warn "Nothing to do — both files kept as-is."
  exit 0
fi

# ── Section 1: Deployment config ─────────────────────────────────────────────

echo ""
echo "── Deployment ────────────────────────────────"
echo "  1) local  — bridge network, ports on localhost (dev)"
echo "  2) nas    — host network, production NAS"
printf "  Choice [1/2, default=1]: "
read -r choice
case "$choice" in
  2) DEPLOY_TARGET="nas" ;;
  *) DEPLOY_TARGET="local" ;;
esac
ok "DEPLOY_TARGET=$DEPLOY_TARGET"

WATCHER_PORT=$(prompt_optional "Watcher port" "8080")
ok "WATCHER_PORT=$WATCHER_PORT"

# ── Section 2: Inactivity timeouts ───────────────────────────────────────────

echo ""
echo "── Inactivity shutdown ───────────────────────"
dim "  (seconds; leave empty for defaults: warn=3600, grace=900)"
INACTIVITY_WARN=$(prompt_optional "Warn after (s)" "3600")
INACTIVITY_GRACE=$(prompt_optional "Force-stop grace (s)" "900")
ok "timeouts: warn=${INACTIVITY_WARN}s grace=${INACTIVITY_GRACE}s"

# ── Section 3: Dev mode ───────────────────────────────────────────────────────

echo ""
echo "── Dev mode ──────────────────────────────────"
dim "  DEV_MODE=true bypasses JWT auth. NEVER use in production."
printf "  Enable DEV_MODE? [y/N, default=N]: "
read -r devmode_ans
[[ "$devmode_ans" =~ ^[Yy]$ ]] && DEV_MODE="true" || DEV_MODE="false"
ok "DEV_MODE=$DEV_MODE"

# ── Section 4: Auth service (Phase 3 / rev0auth) ─────────────────────────────

echo ""
echo "── Auth service (Phase 3) ────────────────────"
dim "  Leave empty to skip JWT integration (uses password auth only)."
AUTH_SERVICE_LOGIN_URL=$(prompt_optional "AUTH_SERVICE_LOGIN_URL" "")

# ── Section 5: Passwords ─────────────────────────────────────────────────────

echo ""
echo "── Passwords ─────────────────────────────────"
warn "These are stored in .secrets (600). Choose strong, unique passwords."
WATCHER_PASSWORD=$(prompt_password "Admin password")
WATCHER_GUEST_PASSWORD=$(prompt_password "Guest password")
ok "Passwords set"

# ── Section 6: JWT secret ─────────────────────────────────────────────────────

echo ""
echo "── JWT secret (Phase 3) ──────────────────────"
dim "  If using rev0auth, paste the same AUTH_JWT_SECRET value here."
dim "  Leave empty to auto-generate (Phase 3 disabled for now)."
printf "  AUTH_JWT_SECRET [auto-generate]: "
read -rs JWT_INPUT; echo
if [ -z "$JWT_INPUT" ]; then
  AUTH_JWT_SECRET=$(gen_hex)
  dim "  (auto-generated — copy to rev0auth when activating Phase 3)"
else
  AUTH_JWT_SECRET="$JWT_INPUT"
fi
ok "AUTH_JWT_SECRET set"

# ── Section 7: Donation addresses (optional) ─────────────────────────────────

echo ""
echo "── Donation addresses (optional) ─────────────"
dim "  Leave empty to disable the donation page."
DONATION_BTC=$(prompt_optional  "BTC address" "")
DONATION_ETH=$(prompt_optional  "ETH address" "")
DONATION_SOL=$(prompt_optional  "SOL address" "")
DONATION_XMR=$(prompt_optional  "XMR address" "")

# ── Generate hex keys ─────────────────────────────────────────────────────────

echo ""
info "Generating cryptographic keys..."
WATCHER_FLASK_SECRET_KEY=$(gen_hex)
SONGSURF_FLASK_SECRET_KEY=$(gen_hex)
WATCHER_SECRET=$(gen_hex)
ok "3 keys generated (64 hex chars each)"

# ── Write .env ────────────────────────────────────────────────────────────────

if $WRITE_ENV; then
  cat > "$ENV_FILE" <<EOF
# SongSurf — configuration
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Non-secret configuration. Key material is in .secrets (chmod 600).

# ── Deployment ─────────────────────────────────────────────────────────────
DEPLOY_TARGET=${DEPLOY_TARGET}
WATCHER_PORT=${WATCHER_PORT}

# ── Internal routing ────────────────────────────────────────────────────────
TARGET_URL=http://songsurf:8081
TARGET_URL_NAS=http://localhost:8081

# ── Inactivity shutdown ─────────────────────────────────────────────────────
INACTIVITY_WARN_TIMEOUT=${INACTIVITY_WARN}
INACTIVITY_GRACE_TIMEOUT=${INACTIVITY_GRACE}

# ── Dev mode ─────────────────────────────────────────────────────────────────
# true = bypass JWT auth (NEVER in production)
DEV_MODE=${DEV_MODE}

# ── Auth service (Phase 3) ───────────────────────────────────────────────────
AUTH_SERVICE_LOGIN_URL=${AUTH_SERVICE_LOGIN_URL}

# ── Donation addresses (optional) ────────────────────────────────────────────
DONATION_BTC=${DONATION_BTC}
DONATION_ETH=${DONATION_ETH}
DONATION_SOL=${DONATION_SOL}
DONATION_XMR=${DONATION_XMR}
EOF
  chmod 644 "$ENV_FILE"
  ok ".env written"
fi

# ── Write .secrets ────────────────────────────────────────────────────────────

if $WRITE_SECRETS; then
  cat > "$SECRETS_FILE" <<EOF
# SongSurf — secret key material
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# DO NOT commit. DO NOT share. DO NOT log.
# Loaded by Docker Compose via env_file directive.

# ── Flask session keys (auto-generated) ──────────────────────────────────────
WATCHER_FLASK_SECRET_KEY=${WATCHER_FLASK_SECRET_KEY}
SONGSURF_FLASK_SECRET_KEY=${SONGSURF_FLASK_SECRET_KEY}

# ── Shared internal secret — Watcher ↔ SongSurf (auto-generated) ─────────────
WATCHER_SECRET=${WATCHER_SECRET}

# ── Auth service JWT secret — must match rev0auth AUTH_JWT_SECRET ─────────────
AUTH_JWT_SECRET=${AUTH_JWT_SECRET}

# ── Passwords ─────────────────────────────────────────────────────────────────
WATCHER_PASSWORD=${WATCHER_PASSWORD}
WATCHER_GUEST_PASSWORD=${WATCHER_GUEST_PASSWORD}
EOF
  chmod 600 "$SECRETS_FILE"
  ok ".secrets written (chmod 600)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════"
echo -e "  ${GREEN}Done.${NC}"
echo "══════════════════════════════════════════════"
echo ""
echo "  Files created:"
[ -f "$ENV_FILE" ]     && echo -e "    ${CYAN}.env${NC}     — configuration (644)"
[ -f "$SECRETS_FILE" ] && echo -e "    ${CYAN}.secrets${NC} — key material  (600) ← never commit this"
echo ""
echo "  Next: make up"
if [ "$DEV_MODE" = "false" ] && [ -n "$AUTH_SERVICE_LOGIN_URL" ]; then
  echo ""
  warn "Phase 3 active: ensure AUTH_JWT_SECRET matches rev0auth before deploying."
fi
echo ""
