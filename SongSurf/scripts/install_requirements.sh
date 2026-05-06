#!/usr/bin/env bash
# Install all dependencies required to run SongSurf locally or build for Docker.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[ok]${NC}  $*"; }
warn() { echo -e "${YELLOW}[!!]${NC}  $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }
info() { echo -e "${CYAN}[..]${NC}  $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "══════════════════════════════════════════════"
echo "  SongSurf — install requirements"
echo "══════════════════════════════════════════════"
echo ""

# ── 1. Python 3.11+ ──────────────────────────────────────────────────────────

info "Checking Python..."
if ! command -v python3 &>/dev/null; then
  err "python3 not found. Install Python 3.11+ and retry."
  exit 1
fi

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
  err "Python 3.11+ required, found $PYTHON_VER."
  exit 1
fi
ok "Python $PYTHON_VER"

# ── 2. pip ────────────────────────────────────────────────────────────────────

info "Checking pip..."
if ! python3 -m pip --version &>/dev/null; then
  err "pip not found. Run: python3 -m ensurepip --upgrade"
  exit 1
fi
ok "pip $(python3 -m pip --version | awk '{print $2}')"

# ── 3. Python deps: server + watcher ─────────────────────────────────────────

info "Installing Python dependencies (server + watcher)..."

# Merge requirements without duplicates
COMBINED=$(mktemp)
cat "$ROOT/server/requirements.txt" "$ROOT/watcher/requirements.txt" | sort -u > "$COMBINED"

python3 -m pip install --quiet --requirement "$COMBINED"
rm "$COMBINED"
ok "Python packages installed"

# ── 4. Node.js 18+ ───────────────────────────────────────────────────────────

info "Checking Node.js..."
if ! command -v node &>/dev/null; then
  err "node not found. Install Node.js 18+ (https://nodejs.org) and retry."
  exit 1
fi

NODE_VER=$(node --version | tr -d 'v')
NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 18 ]; then
  err "Node.js 18+ required, found v$NODE_VER."
  exit 1
fi
ok "Node.js v$NODE_VER"

# ── 5. npm ────────────────────────────────────────────────────────────────────

if ! command -v npm &>/dev/null; then
  err "npm not found (should come with Node.js)."
  exit 1
fi
ok "npm $(npm --version)"

# ── 6. SvelteKit frontend deps ───────────────────────────────────────────────

if [ -f "$ROOT/frontend/package.json" ]; then
  info "Installing SvelteKit frontend dependencies..."
  (cd "$ROOT/frontend" && npm ci --silent)
  ok "SvelteKit packages installed"
else
  warn "frontend/package.json not found — skipping Node install."
fi

# ── 7. Docker (check only — not installed by this script) ────────────────────

info "Checking Docker..."
if ! command -v docker &>/dev/null; then
  warn "docker not found. Install Docker Desktop or Docker Engine to use 'make up'."
else
  ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
  if docker compose version &>/dev/null 2>&1; then
    ok "Docker Compose plugin available"
  elif command -v docker-compose &>/dev/null; then
    ok "docker-compose (v1) available"
  else
    warn "No Docker Compose found. Install the Compose plugin: https://docs.docker.com/compose/install/"
  fi
fi

echo ""
echo -e "${GREEN}All requirements satisfied.${NC}"
echo "Next step: run 'make secrets' to generate your .env and .secrets files."
echo ""
