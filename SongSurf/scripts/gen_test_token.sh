#!/usr/bin/env bash
# Génère un JWT de test compatible avec le Watcher (HS256, claims requis).
# Utile pour accéder à SongSurf en mode prod sans rev0auth en ligne.
#
# Usage:
#   make token              → token admin 24h
#   make token ROLE=guest   → token guest
#   make token TTL=168      → token admin 7 jours
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[ok]${NC}  $*"; }
warn() { echo -e "${YELLOW}[!!]${NC}  $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_FILE="$ROOT/.secrets"

# ── Lire AUTH_JWT_SECRET depuis .secrets ──────────────────────────────────────

[[ -f "$SECRETS_FILE" ]] || err ".secrets introuvable. Lance 'make secrets' d'abord."

AUTH_JWT_SECRET=$(grep -E '^AUTH_JWT_SECRET=' "$SECRETS_FILE" | cut -d= -f2- | tr -d '"')
[[ -n "$AUTH_JWT_SECRET" ]] || err "AUTH_JWT_SECRET absent ou vide dans .secrets."

# ── Paramètres ────────────────────────────────────────────────────────────────

ROLE="${ROLE:-admin}"
TTL_HOURS="${TTL:-24}"

[[ "$ROLE" == "admin" || "$ROLE" == "guest" ]] || err "ROLE doit être 'admin' ou 'guest' (reçu: $ROLE)"

# ── Générer le JWT via Python (PyJWT déjà installé dans le venv watcher) ──────

TOKEN=$(python3 - <<PYEOF
import base64, hmac, hashlib, json, time

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

secret  = "$AUTH_JWT_SECRET"
role    = "$ROLE"
ttl     = int($TTL_HOURS)

header  = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",",":")).encode())
now     = int(time.time())
payload = b64url(json.dumps({
    "sub":        f"test-{role}-local",
    "role":       role,
    "email":      f"{role}@test.local",
    "token_type": "access",
    "iat":        now,
    "exp":        now + ttl * 3600,
}, separators=(",",":")).encode())

signing_input = f"{header}.{payload}".encode()
sig = b64url(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
print(f"{header}.{payload}.{sig}")
PYEOF
)

# ── Affichage ─────────────────────────────────────────────────────────────────

WATCHER_PORT=$(grep -E '^WATCHER_PORT=' "$ROOT/.env" 2>/dev/null | cut -d= -f2 || echo "8080")
EXPIRE_AT=$(date -d "+${TTL_HOURS} hours" "+%Y-%m-%d %H:%M" 2>/dev/null || date -v+"${TTL_HOURS}"H "+%Y-%m-%d %H:%M" 2>/dev/null || echo "dans ${TTL_HOURS}h")

echo ""
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}JWT de test généré${NC}"
echo -e "${BOLD}══════════════════════════════════════════════${NC}"
echo ""
echo -e "  Role     : ${CYAN}${ROLE}${NC}"
echo -e "  Expire   : ${EXPIRE_AT} (${TTL_HOURS}h)"
echo ""
echo -e "  ${BOLD}Token :${NC}"
echo ""
echo -e "  ${CYAN}${TOKEN}${NC}"
echo ""
echo -e "${BOLD}── Comment l'injecter dans le navigateur ───────${NC}"
echo ""
echo -e "  ${BOLD}Option 1 — Console DevTools (F12 → Console) :${NC}"
echo ""
echo -e "  ${DIM}document.cookie = \"access_token=${TOKEN}; path=/; SameSite=Lax\";${NC}"
echo ""
echo -e "  ${BOLD}Option 2 — curl :${NC}"
echo ""
echo -e "  ${DIM}curl -b \"access_token=${TOKEN}\" http://localhost:${WATCHER_PORT}/${NC}"
echo ""
warn "Ce token est pour les tests LOCAUX uniquement. Ne l'utilise pas en production."
echo ""
