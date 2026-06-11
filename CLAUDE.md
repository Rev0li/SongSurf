# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

SongSurf is a self-hosted YouTube Music downloader with a two-tier proxy architecture:

```
Browser ──JWT cookie──► [Watcher :8080*] ──headers──► [SongSurf :8081] ──► yt-dlp ──► FFmpeg ──► /data/music/<pseudo>/Artist/Album/Title.mp3
                            │                              ▲
                            └── Docker SDK (start/stop) ───┘
```
*\*8080 by default (`WATCHER_PORT`); production NAS runs it on 9000.*

- **Watcher** (`SongSurf/watcher/watcher.py`, always running): validates the `access_token` JWT cookie (HS256, secret shared with rev0auth), injects identity headers, starts/stops the SongSurf container on demand, monitors inactivity.
- **SongSurf** (`SongSurf/server/`, started on demand): Flask app — extraction, download queue, MP3 conversion, ID3 tagging, library management, metadata editor API.
- **Frontend** (`SongSurf/frontend/`): SvelteKit (adapter-static), built into the Docker image and served by Flask.
- **Browser extension** (`chrome-extension/`): MV3, queues songs/albums/playlists from music.youtube.com into SongSurf, scrapes artist discographies, syncs YouTube cookies for yt-dlp.

Repo layout note: the actual app lives under `SongSurf/SongSurf/` (nested). Paths below are relative to `SongSurf/SongSurf/` unless stated otherwise.

## Commands

All `make` commands run from `SongSurf/SongSurf/`:

```bash
make secrets         # interactive wizard → .env + .secrets (first run)
make up-local        # start in local mode (bridge network, localhost ports)
make up-nas          # start in NAS mode (network_mode: host, JWT required)
make logs            # stream all container logs (logs-watcher / logs-songsurf)
make down / restart  # stop / full restart
make config          # preview resolved compose config
make dev             # Flask backend without Docker (DEV_MODE=true, port 8081)
make frontend-dev    # SvelteKit hot-reload dev server (port 5173)
make token ROLE=admin TTL=24   # generate a test JWT (prod-mode testing without rev0auth)
make deploy-nas      # rsync + rebuild + restart on the Synology NAS

# Tests (153 pytest tests, no linter configured)
python3 -m pytest               # from SongSurf/SongSurf/
python3 -m pytest tests/test_organizer.py -q
```

Docker Compose files merge at runtime via `docker/compose-switch.sh` based on `DEPLOY_TARGET` in `.env`: `docker-compose.yml` (base) + `docker-compose.local.yml` (dev) or `docker-compose.nas.yml` (prod, host network).

## Authentication model

Phase 3 (rev0auth integration) is **implemented**:

1. Watcher reads the `access_token` cookie and validates the HS256 JWT locally with `AUTH_JWT_SECRET` (must be byte-identical to the rev0auth side — see root `rev0Univers/CLAUDE.md` for rotation).
2. On success it proxies to SongSurf, injecting `X-Watcher-Token: <WATCHER_SECRET>` plus `X-User-Id` / `X-User-Role` / `X-User-Email` from the JWT claims.
3. SongSurf trusts those headers after verifying `X-Watcher-Token` (constant-time compare). It performs **no JWT validation** itself.
4. No cookie → redirect to `AUTH_SERVICE_LOGIN_URL` (or 503 if unset).
5. `DEV_MODE=true` bypasses everything with a local admin dev user — never in production.

There are no login forms, password auth, or guest sessions anymore (removed in Phase 2/3 — older docs mentioning `/api/guest/*` are obsolete).

## Storage model

- Production: per-user library `/data/music/<pseudo>/Artist/Album/Title.mp3`. `pseudo` = email local part (sanitized); admin role always maps to `ADMIN_PSEUDO` (default `rev0admin`).
- `DEV_MODE`: flat `/data/music/Artist/Album/`.
- Member ZIP export (`/api/prepare-zip` → `/api/download-zip`) **deletes the member's library after streaming** — by design (temporary libraries). The admin library is never deleted.
- MP3 only. Playlist flat-folder mode and MP4 support were removed (2026-06).

## Backend modules

| File | Responsibility |
|---|---|
| `server/app.py` | Flask routes, auth guard, download queue + worker thread, per-user dirs, ZIP export, metadata editor API, extension endpoints |
| `server/downloader.py` | yt-dlp wrapper: metadata extraction (single + playlist/album), MP3 download to temp, prefetch, progress tracking, artist list normalization |
| `server/organizer.py` | File placement `Artist/Album/Title.mp3`, ID3 tags via Mutagen, featuring detection, album covers (`cover.jpg` + embedded APIC) |
| `watcher/watcher.py` | JWT validation, header injection, reverse proxy, SongSurf container lifecycle (Docker SDK), inactivity shutdown, CORS for the extension |

Full API reference: `documentation/API_OR_MODULES.md`.

## Metadata pipeline (ID3)

Written by `organizer._update_tags` on every download:

- `TIT2` title · `TALB` album · `TDRC` year
- `TPE1` artist(s) — **multi-value** (null-separated ID3v2.4): yt-dlp `artists` list when available, fallback split on `&`/`,`/`et`; featurings detected in the title are appended. Never a combined `"A & B"` string (it would fragment Jellyfin artists).
- `TPE2` album artist — **always written, single value** (Jellyfin's album-grouping key); album artist for album downloads, falls back to primary artist.
- `TRCK` track number as `n/total` (album position or yt-dlp `track_number`).
- `TCON` genre — **admin downloads only**, auto-fetched from the iTunes Search API (`server/genre_lookup.py`, FR + US storefronts, deduped multi-value, cached per album, silent failure). YouTube itself provides no usable genre.
- `APIC` embedded cover + `cover.jpg` in the album folder.

The metadata editor (`/metadata` page → `/api/library/song-meta/save`) accepts `;`-separated values for artist/genre/composer and writes real multi-value frames. `TPE2` deliberately stays single-value.

The folder name always uses only the **primary artist** (first of the list).

Admin maintenance tools (`server/library_audit.py`, UI on `/metadata`):
- **Genre backfill** (`/api/admin/genre-backfill` + `/status`, button on the `/metadata` home): background thread fills missing TCON across the whole admin library via iTunes lookups.
- **Per-artist metadata audit** (`/api/admin/audit/artist` → report, `/api/admin/audit/apply` → write, section in the artist panel): compares every album against iTunes (`lookup_album_info`) plus local coherence checks (TPE2 = artist folder, TRCK `n/total`, year consistency, TPE1/TPE2 mismatch, duplicate tracks, missing covers). Produces checkable recommendations — **nothing is written without explicit admin validation**.

## Threading model (SongSurf)

- Main Flask thread: HTTP, validation, enqueue (`queue.Queue`, max 50, daily limit `DAILY_DOWNLOAD_LIMIT`).
- One download worker thread: processes the queue sequentially, updates `download_status` under `queue_lock`.
- Prefetch daemon thread: pre-downloads the first playlist track for instant cover preview.
- Watcher side: inactivity thread (warn after `INACTIVITY_WARN_TIMEOUT`, stop container after `+ INACTIVITY_GRACE_TIMEOUT`).

## Environment variables

`.env` (non-secret): `DEPLOY_TARGET`, `WATCHER_PORT`, `SONGSURF_PORT`, `TARGET_URL(_NAS)`, `DAILY_DOWNLOAD_LIMIT`, `MAX_DURATION_SECONDS`, `INACTIVITY_WARN_TIMEOUT`, `INACTIVITY_GRACE_TIMEOUT`, `DEV_MODE`, `AUTH_SERVICE_LOGIN_URL`, `REVAUTH_HOME_URL`, `ADMIN_PSEUDO`.

`.secrets` (chmod 600, never committed, generated by `make secrets`): `AUTH_JWT_SECRET`, `WATCHER_SECRET`, Flask secret keys.

`YTDLP_COOKIES` (default `/data/cookies.txt`): YouTube cookies written by the extension via `/api/cookies/update`, picked up by yt-dlp.

## Gotchas

- `AUTH_JWT_SECRET` must match `auth/.secrets` on the rev0auth side — rotating it requires restarting both stacks.
- Port 8081 (SongSurf) must never be exposed to WAN; only Watcher faces traffic.
- Frontend changes require a rebuild: Docker multi-stage builds it (`make up --build` / `make deploy-nas`); for local no-Docker dev use `make frontend-dev`.
- `cancel_flag` in `app.py` is checked by the worker but **no route sets it** — download cancellation is currently not wired.
- Path containment checks use `str.startswith()` (prefix-match edge case); prefer `Path.is_relative_to()` for new code.
- Extension DOM scraping of music.youtube.com is fragile (virtual scrolling, selector drift) — see memory/project notes.
- The zsh `chpwd` hook on this dev machine (eza tree) hangs non-interactive shells: use `git -C <path>` instead of `cd && git`.

## Documentation map

| File | Contents |
|---|---|
| `README.md` | User/dev-facing overview, quick start, self-hosting |
| `documentation/ARCHITECTURE.md` | Components, request lifecycle, threading, frontend |
| `documentation/API_OR_MODULES.md` | Full HTTP API + module reference |
| `documentation/CONNECTOR.md` | rev0auth ↔ SongSurf JWT contract (implemented) |
| `documentation/REV0AUTH_INTEGRATION.md` | Local + prod integration walkthrough (FR) |
| `documentation/TEST_PLAN.md` | Test matrix (automated + manual) |
| `SongSurf/DEPLOY.md` | NAS deployment guide |
| `deploy_action.md` / `deploy_troubleshooting.md` | `make deploy-nas` usage + Synology pitfalls |
