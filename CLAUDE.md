# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

SongSurf is a YouTube Music downloader with a two-tier proxy/auth architecture:

```
Internet → [Watcher :8080] → auth check → [SongSurf :8081] → yt-dlp → FFmpeg → /data/music
```

- **Watcher** (always running, ~15 MB): handles authentication, proxies requests, monitors inactivity, controls SongSurf container lifecycle via Docker SDK
- **SongSurf** (launched on demand): Flask app that extracts/downloads/organizes music; has Admin mode (persistent library) and Guest mode (temporary sessions with ZIP export)

## Commands

```bash
# Start (auto-detects DEPLOY_TARGET from .env: "local" or "nas")
./docker/compose-switch.sh up -d --build

# Logs
./docker/compose-switch.sh logs -f

# Stop
./docker/compose-switch.sh down

# Local dev (no Docker)
cd SongSurf/server && python app.py  # port 8081

# Preview resolved compose config
DEPLOY_TARGET=local ./docker/compose-switch.sh config
```

No test framework or linter is configured — testing is manual.

## Architecture

### Deployment topology

Two Docker Compose files merge at runtime via `compose-switch.sh`:
- `docker-compose.yml` — base (shared)
- `docker-compose.local.yml` — binds ports to localhost (dev)
- `docker-compose.nas.yml` — `network_mode: host` for NAS (prod)

`DEPLOY_TARGET` in `.env` controls which override file is selected.

### Request flow

1. All requests hit **Watcher** (`watcher/watcher.py`) on port 8080
2. Watcher validates session/password, starts SongSurf container if needed, proxies via `WATCHER_SECRET` header
3. **SongSurf** (`SongSurf/server/app.py`) verifies the secret header before allowing access
4. Downloads are queued through `queue.Queue`; one runs at a time with a background thread
5. Guest sessions store files in `/data/music_guest/<session_id>/`, cleaned up by a background cleanup thread after TTL

### Backend modules

| File | Responsibility |
|---|---|
| `SongSurf/server/app.py` | Flask routes, session management, download queue, guest session lifecycle |
| `SongSurf/server/downloader.py` | yt-dlp wrapper, FFmpeg MP3 conversion, progress tracking |
| `SongSurf/server/organizer.py` | ID3 tag writing via Mutagen, file organization `Artist/Album/Title.mp3`, album art |
| `watcher/watcher.py` | Auth proxy, brute-force protection (5 attempts → 15 min lockout), inactivity monitoring |

### Threading model (SongSurf)

- Main Flask thread: handles HTTP, validates, enqueues
- Download worker thread: processes `queue.Queue` one at a time
- Guest cleanup thread: periodically expires TTL sessions, auto-zips, deletes
- Prefetch daemon thread: pre-downloads first playlist track in background for preview

### Frontend

Pure HTML + Jinja2 templates + vanilla JavaScript — no framework or bundler.

- `SongSurf/static/css/design-system.css` — CSS custom properties (colors, spacing, radii)
- `SongSurf/static/css/components.css` — atomic component styles
- `SongSurf/static/js/api.js` — thin HTTP client wrapper used by all pages
- `SongSurf/static/js/pages/dashboard-admin.js` — admin dashboard logic (~2000 lines)
- `SongSurf/static/js/pages/guest-unified.js` — guest dashboard logic
- `SongSurf/static/js/components/` — modal, toast, progress-bar, watcher-inactivity

### Key API endpoints

**Admin** (requires `@login_required`):
- `POST /api/extract` — parse URL, return metadata
- `POST /api/download` — queue single song
- `POST /api/download-playlist` — queue playlist/album
- `GET /api/status` — progress, queue size, batch status
- `GET /api/library` — folder tree of `/data/music`

**Guest** (requires guest session):
- Same extract/download pattern under `/api/guest/*`
- `POST /api/guest/prepare-zip` — bundle session files as ZIP
- `POST /api/guest/extend-session` — add TTL

### Environment variables

Copy `.env.example` → `.env` before running.

Key variables:
- `WATCHER_SECRET` — shared secret between Watcher and SongSurf (must match in both)
- `WATCHER_PASSWORD` / `WATCHER_GUEST_PASSWORD` — login credentials
- `GUEST_MAX_SONGS` — per-session download quota (`0` = unlimited)
- `GUEST_SESSION_TTL` — session lifetime in seconds (default 3600)
- `INACTIVITY_TIMEOUT` / `INACTIVITY_GRACE_TIMEOUT` — idle shutdown thresholds

### Data paths (inside containers)

- `/data/music` — admin library (`Artist/Album/Title.mp3`)
- `/data/music_guest/<session_id>/` — guest session files
- `/data/temp` — download staging area
- `/app/logs/activity.log` — human-readable activity log

## Planned migration

The `SongSurf/migration/` folder documents a planned rewrite of the backend to Rust (Axum + Tera), migrating auth/accounts first while keeping Python for download/org logic initially. See `Road_map_V1.md` and `Technical_Tickets_V1.md` for details.
