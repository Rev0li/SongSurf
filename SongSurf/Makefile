# SongSurf — Makefile
#
# Modes:
#   make up-local   → force local mode (bridge network, localhost ports, DEV_MODE)
#   make up-nas     → force NAS mode   (host network, production)
#   make up         → use DEPLOY_TARGET from .env (defaults to local)
#
# Logs:
#   make logs             → all containers
#   make logs-watcher     → watcher only
#   make logs-songsurf    → songsurf only
#
# Cleanup:
#   make clean            → remove Docker images + temp data
#   make reset            → clean full restart (down → clean → up)

SHELL := /bin/bash
COMPOSE := ./docker/compose-switch.sh

# Load .env then .secrets if they exist
ifneq (,$(wildcard .env))
  include .env
  export
endif
ifneq (,$(wildcard .secrets))
  include .secrets
  export
endif

TARGET ?= $(DEPLOY_TARGET)
TARGET ?= local

# ── First-time setup ─────────────────────────────────────────────────────────

.PHONY: secrets
secrets:                          ## Interactive wizard: creates .env + .secrets
	@bash scripts/generate_secrets.sh

.PHONY: init-dirs
init-dirs:                        ## Create host data/logs directories
	@mkdir -p data/music data/music_guest data/temp logs
	@chmod 777 data/music data/music_guest data/temp logs
	@mkdir -p data/cookies && chmod 700 data/cookies   # cookies YouTube par utilisateur (SSF-01)
	@mkdir -p data/state && chmod 700 data/state       # SQLite : file, quotas, ZIP (SSF-03)
	@echo "[ok] Data directories ready."

# ── Frontend (local, no Docker) ───────────────────────────────────────────────

.PHONY: frontend-build frontend-dev
frontend-build:                   ## Build SvelteKit locally → frontend/build/
	cd frontend && npm ci && npm run build

frontend-dev:                     ## SvelteKit hot-reload dev server (port 5173)
	cd frontend && npm ci && npm run dev

# ── Docker — explicit mode targets ───────────────────────────────────────────

.PHONY: up-local up-nas
up-local: init-dirs               ## Start in LOCAL mode (bridge network, DEV_MODE=true)
	DEPLOY_TARGET=local $(COMPOSE) up -d --build

up-nas: init-dirs                 ## Start in NAS mode (host network, portal gate required)
	DEPLOY_TARGET=nas $(COMPOSE) up -d --build

# ── Docker — generic targets (use TARGET from .env or override) ───────────────

.PHONY: build up down restart
build: init-dirs                  ## Build Docker images only (no start)
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) build

up: init-dirs                     ## Start containers using DEPLOY_TARGET from .env
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) up -d --build

down:                             ## Stop and remove containers
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) down

restart: down up                  ## Full restart (down → up)

# ── Logs ─────────────────────────────────────────────────────────────────────

.PHONY: logs logs-watcher logs-songsurf
logs:                             ## Stream logs from all containers
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) logs -f

logs-watcher:                     ## Stream Watcher logs only
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) logs -f watcher

logs-songsurf:                    ## Stream SongSurf logs only
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) logs -f songsurf

# ── Debug ─────────────────────────────────────────────────────────────────────

.PHONY: ps config shell
ps:                               ## Show container status
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) ps

config:                           ## Preview the resolved Compose config
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) config

shell:                            ## Open a shell in the running songsurf container
	docker exec -it songsurf bash

# ── yt-dlp (version épinglée) ─────────────────────────────────────────────────

.PHONY: bump-ytdlp
bump-ytdlp:                       ## Épingle la dernière version de yt-dlp (VERSION=… pour forcer), puis rebuild/deploy
	@v="$(VERSION)"; \
	if [ -z "$$v" ]; then \
	  v=$$(curl -fsS https://pypi.org/pypi/yt-dlp/json | python3 -c 'import json,sys; print(json.load(sys.stdin)["info"]["version"])'); \
	fi; \
	[ -n "$$v" ] || { echo "Version introuvable"; exit 1; }; \
	old=$$(sed -n 's/^yt-dlp==//p' server/requirements.txt); \
	sed -i "s/^yt-dlp==.*/yt-dlp==$$v/" server/requirements.txt; \
	echo "[ok] yt-dlp $$old → $$v (server/requirements.txt). Ensuite : make up --build / make deploy-nas"

# ── Local dev (no Docker) ─────────────────────────────────────────────────────

.PHONY: dev
dev:                              ## Run Flask backend directly (DEV_MODE=true, port 8081)
	cd server && DEV_MODE=true python app.py

# ── Cleanup ───────────────────────────────────────────────────────────────────

.PHONY: clean reset
clean:                            ## Remove Docker images + temp data
	@echo "Removing Docker images..."
	-docker rmi songsurf:latest watcher:latest 2>/dev/null || true
	@echo "Clearing temp data..."
	@rm -rf data/temp/*
	@echo "Clearing frontend local build artifacts (may need sudo for root-owned files)..."
	@rm -rf frontend/build/ 2>/dev/null || sudo rm -rf frontend/build/
	@rm -rf frontend/.svelte-kit/ 2>/dev/null || sudo rm -rf frontend/.svelte-kit/
	@echo "[ok] Clean done."

reset: down clean up              ## Full wipe: stop → clean → start fresh

# ── Deploy NAS (manuel, depuis la machine de dev) ────────────────────────────

NAS_USER ?= rev0li08
# alias ~/.ssh/config → IP Tailscale du NAS (pas d'IP dans le repo public)
NAS_HOST ?= nas-songsurf
NAS_PORT ?= 22
NAS_KEY  ?= $(HOME)/.ssh/nas_songsurf
NAS_DIR  ?= /volume1/docker/songsurf

NAS_SSH := ssh -p $(NAS_PORT) -i $(NAS_KEY)

.PHONY: deploy-nas
deploy-nas:                       ## rsync + restart watcher/songsurf sur le NAS
	rsync -avz --delete \
	  -e "ssh -p $(NAS_PORT) -i $(NAS_KEY)" \
	  --exclude='__pycache__/' \
	  --exclude='data/' \
	  --exclude='logs/' \
	  --exclude='.git/' \
	  --exclude='.env' \
	  --exclude='.secrets' \
	  ./ $(NAS_USER)@$(NAS_HOST):$(NAS_DIR)/
	$(NAS_SSH) $(NAS_USER)@$(NAS_HOST) \
	  "cd $(NAS_DIR) && mkdir -p data/cookies data/state && chmod 700 data/cookies data/state && set -a && . ./.env && . ./.secrets && set +a && PATH=/usr/local/bin:/var/packages/Docker/target/usr/bin:$$PATH DEPLOY_TARGET=nas sudo -n -E ./docker/compose-switch.sh up -d --no-deps --build --force-recreate watcher songsurf"

.PHONY: deploy-nas-dry
deploy-nas-dry:                   ## dry-run rsync (aperçu sans envoyer)
	rsync -avzn --delete \
	  -e "ssh -p $(NAS_PORT) -i $(NAS_KEY)" \
	  --exclude='__pycache__/' \
	  --exclude='data/' \
	  --exclude='logs/' \
	  --exclude='.git/' \
	  --exclude='.env' \
	  --exclude='.secrets' \
	  ./ $(NAS_USER)@$(NAS_HOST):$(NAS_DIR)/

# ── Helpers ───────────────────────────────────────────────────────────────────

.PHONY: help
help:                             ## Show this help
	@grep -h '^\([a-zA-Z_-]\+\):.*##' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
