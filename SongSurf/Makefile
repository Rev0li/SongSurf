# SongSurf — Makefile
# Usage: make <target> [TARGET=local|nas]
#
# DEPLOY_TARGET is read from .env by default.
# Override: make up TARGET=nas

SHELL := /bin/bash
COMPOSE := ./docker/compose-switch.sh

# Load config from .env, then secrets from .secrets (if they exist)
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

.PHONY: install
install:                          ## Install all dependencies (Python, Node, SvelteKit)
	@bash scripts/install_requirements.sh

.PHONY: secrets
secrets:                          ## Generate .env (config) and .secrets (key material)
	@bash scripts/generate_secrets.sh

.PHONY: init-dirs
init-dirs:                        ## Create host data/logs directories with correct permissions
	@mkdir -p data/music data/music_guest data/temp data/temp_guest logs
	@chmod 755 data/music data/music_guest data/temp data/temp_guest logs
	@echo "Directories ready."

# ── Frontend ─────────────────────────────────────────────────────────────────

.PHONY: frontend-install frontend-build frontend-dev
frontend-install:                 ## Install SvelteKit dependencies
	cd frontend && npm ci

frontend-build: frontend-install  ## Build SvelteKit → frontend/build/
	cd frontend && npm run build

frontend-dev:                     ## SvelteKit hot-reload dev server (port 5173)
	cd frontend && npm run dev

# ── Docker ───────────────────────────────────────────────────────────────────

.PHONY: build up down restart logs ps config

build: init-dirs                  ## Build Docker images (frontend built inside Docker)
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) build

up: init-dirs                     ## Start containers — Docker handles the frontend build
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) up -d --build

down:                             ## Stop and remove containers
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) down

restart: down up                  ## Full restart (down → build → up)

logs:                             ## Stream logs from all containers
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) logs -f

ps:                               ## Show container status
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) ps

config:                           ## Preview the resolved Compose config
	DEPLOY_TARGET=$(TARGET) $(COMPOSE) config

# ── Local dev (no Docker) ────────────────────────────────────────────────────

.PHONY: dev
dev:                              ## Run Flask backend directly (DEV_MODE=true, port 8081)
	cd server && DEV_MODE=true python app.py

# ── Helpers ──────────────────────────────────────────────────────────────────

.PHONY: help
help:                             ## Show this help
	@grep -h '^\([a-zA-Z_-]\+\):.*##' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
