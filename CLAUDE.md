# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

SongSurf is a self-hosted YouTube Music downloader with a two-tier proxy architecture:

```
Browser ──portal session──► Caddy (forward_auth) ──identity + X-Proxy-Token──► [Watcher :8080*] ──headers──► [SongSurf :8081] ──► yt-dlp ──► FFmpeg ──► /data/music/<uid>/Artist/Album/Title.mp3
                            │                              ▲
                            └── Docker SDK (start/stop) ───┘
```
*\*8080 by default (`WATCHER_PORT`); production NAS runs it on 9000.*

- **Watcher** (`SongSurf/watcher/watcher.py`, always running): trusts the identity sent by Caddy only with a valid `X-Proxy-Token` (portal gate), injects identity headers, starts/stops the SongSurf container on demand, monitors inactivity.
- **SongSurf** (`SongSurf/server/`, started on demand): Flask app — extraction, download queue, MP3 conversion, ID3 tagging, library management, metadata editor API.
- **Frontend** (`SongSurf/frontend/`): SvelteKit (adapter-static), built into the Docker image and served by Flask. Both pages share `Header.svelte` (fixed 93px chrome: "← Mon espace" left, centered logo, pseudo + theme right, Téléchargement/Métadonnées tabs). `/metadata` persists navigation state (expanded tree, sidebar collapsed, selection) in localStorage under `ssf.meta.*`. Cover/artist image URLs are versioned (`?t=<n>` from `ssf.meta.imgv`, bumped only on cover upload — never `Date.now()`, which would defeat the browser cache); the image endpoints send `Cache-Control: private, max-age=86400`.
- **Browser extension** (`chrome-extension/`): MV3, queues songs/albums/playlists from music.youtube.com into SongSurf, scrapes artist discographies, syncs YouTube cookies for yt-dlp.

Repo layout note: the actual app lives under `SongSurf/SongSurf/` (nested). Paths below are relative to `SongSurf/SongSurf/` unless stated otherwise.

## Commands

All `make` commands run from `SongSurf/SongSurf/`:

```bash
make secrets         # interactive wizard → .env + .secrets (first run)
make up-local        # start in local mode (bridge network, localhost ports)
make up-nas          # start in NAS mode (network_mode: host, portal gate required)
make logs            # stream all container logs (logs-watcher / logs-songsurf)
make down / restart  # stop / full restart
make config          # preview resolved compose config
make dev             # Flask backend without Docker (DEV_MODE=true, port 8081)
make frontend-dev    # SvelteKit hot-reload dev server (port 5173)
make deploy-nas      # rsync + rebuild + restart on the Synology NAS
make bump-ytdlp      # pin the latest yt-dlp in server/requirements.txt (VERSION=… to force)

# Tests (~300 pytest tests, no linter configured; the test_watcher_* files need the docker SDK)
python3 -m pytest               # from SongSurf/SongSurf/
python3 -m pytest tests/test_organizer.py -q
```

Docker Compose files merge at runtime via `docker/compose-switch.sh` based on `DEPLOY_TARGET` in `.env`: `docker-compose.yml` (base) + `docker-compose.local.yml` (dev) or `docker-compose.nas.yml` (prod, host network).

## Authentication model

Portal gate (AUTH-09, **implemented**: SSF-11 then SSF-12 removed the JWT):

1. Caddy on the VPS asks the portal before each request to `songsurf.` (`forward_auth`). No session → Caddy itself redirects to the portal login (navigation) or answers 401 (API); no SongSurf access → 403. The Watcher never redirects to a login page.
2. Access granted → Caddy sends `X-User-Name` (exact pseudo) / `X-User-Role` / `X-User-Id` (portal UUID) plus the proof `X-Proxy-Token`, after stripping client-sent `X-User-*` and the portal cookie.
3. The Watcher trusts those headers **only** if `X-Proxy-Token` matches `SONGSURF_PROXY_SECRET` (constant-time). Otherwise → 401 JSON (API / extension) or a « passe par le portail » page. Empty secret → locked.
4. It proxies to SongSurf with `X-Watcher-Token: <WATCHER_SECRET>` + `X-User-Id` = pseudo (`sub`, display/logs/events only) / `X-User-Role` / `X-User-Email` (empty) / `X-User-Portal-Id` = portal UUID (**storage key**, required: SongSurf answers 401 without a valid one). Client-sent `X-User-*` / `X-Proxy-Token` are never forwarded. SongSurf verifies `X-Watcher-Token` and performs no auth itself.
5. `/logout` puts SongSurf to sleep and redirects to `REVAUTH_HOME_URL` (the session is the portal's, no cookie here).
6. `DEV_MODE=true` bypasses everything with a local admin dev user — never in production.

There are no login forms, password auth, guest sessions or JWT anymore (`?token=`, `access_token`, `AUTH_JWT_SECRET`, `AUTH_SERVICE_LOGIN_URL`, `make token` removed in SSF-12). Contract: `docs/CONNECTOR.md`.

## Storage model

- Production: per-user library `/data/music/<uid>/Artist/Album/Title.mp3`, `uid` = portal UUID (`_user_key()`, SSF-03) — admin included, never derived from the pseudo. Each folder has a `.owner` file holding the exact pseudo. On the NAS the admin library is the Jellyfin music folder bind-mounted on `/data/music/${ADMIN_UID}` (`docker-compose.nas.yml`). Old pseudo-named folders: one-shot `scripts/migrate_to_uid.py` (procedure in `docs/DEPLOY.md` §5.1).
- `DEV_MODE`: flat `/data/music/Artist/Album/`.
- Member ZIP export (`/api/prepare-zip` → 202, built in a background thread; frontend polls `/api/zip-status`; then `/api/download-zip`) **deletes the member's library after streaming** — by design (temporary libraries) — but **only if the whole file was sent** (SSF-14): an interrupted download (network, locked phone, closed tab) keeps the library and the ready ZIP, recoverable with « Récupérer le ZIP ». ZIP export is **disabled for the admin library** (SSF-10): button hidden, both endpoints return 403 `zip_disabled`. `_zip_forbidden()` checks the role *and* the target folder (music root, any mount point — `_is_mount_point()` also reads `/proc/self/mountinfo` because `os.path.ismount` misses same-disk bind mounts), and the post-stream cleanup re-checks it before `rmtree`.
- Persistent state (`server/state_store.py`, SQLite `/data/state/songsurf.db`, volume `./data/state`): download queue, round-robin pointer, per-user daily counters, ZIP export state. Survives restarts.
- MP3 only. Playlist flat-folder mode and MP4 support were removed (2026-06).

## Backend modules

| File | Responsibility |
|---|---|
| `server/app.py` | Flask routes, auth guard, download queue + worker thread, per-user dirs, ZIP export, metadata editor API, extension endpoints |
| `server/downloader.py` | yt-dlp wrapper: metadata extraction (single + playlist/album), MP3 download to temp, progress tracking, artist list normalization |
| `server/state_store.py` | `StateStore` (SQLite): persistent queue with round-robin `claim_next`/`finish`, daily counters, ZIP export state; `round_robin_order()` pure helper |
| `server/organizer.py` | File placement `Artist/Album/Title.mp3`, ID3 tags via Mutagen, featuring detection, album covers (`cover.jpg` + embedded APIC) |
| `watcher/watcher.py` | Portal gate (`X-Proxy-Token`), header injection, reverse proxy, SongSurf container lifecycle (Docker SDK), inactivity shutdown, CORS for the extension |
| `shared/events_client.py` | Activity-event push to rev0auth (stdlib-only, copied into both images): `emit()` fire-and-forget thread, JSONL spool in `logs/events-pending-<source>.jsonl` on failure, replay thread every 5 min |

Full API reference: `docs/API_OR_MODULES.md`.

## Activity events (push to rev0auth)

Watcher + SongSurf push activity events to the auth VPS (`POST $AUTH_EVENTS_URL`, header `X-Events-Secret: $SONGSURF_EVENTS_SECRET`), stored in PostgreSQL and displayed on the admin page `/japprends/songsurf-activity`. Event types: `download_success` / `download_failed` / `zip_export` (server worker + ZIP cleanup), `container_start` / `container_stop` (watcher Docker lifecycle). Empty `AUTH_EVENTS_URL` disables everything (no-op). Never blocking: 3 s timeout, failures go to the local spool. Deploy order: auth (VPS) first, then NAS.

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

Maintenance tools (`server/library_audit.py`, UI on `/metadata`):
- **Genre backfill** (`/api/admin/genre-backfill` + `/status`, **admin-only**): background thread fills missing TCON across the whole admin library via iTunes lookups. **No UI button** (removed by design — genres are handled per artist via the audit); endpoint kept for curl/automation.
- **Per-artist metadata audit** (`/api/library/audit/artist` → report, `/api/library/audit/apply` → write, section in the artist panel): **available to all members** — runs the iTunes scan on the caller's own library (`_user_music_dir`). Compares every album against iTunes (`lookup_album_info`) plus local coherence checks (TPE2 = artist folder, TRCK `n/total`, year consistency, TPE1/TPE2 mismatch, duplicate tracks, missing covers). Missing TRCK values are proposed from the official iTunes tracklist (`lookup_album_tracks`, unambiguous title matches only). Produces checkable recommendations — **nothing is written without explicit user validation**.
- **Manual track renumbering** (all users, album panel → "🔢 Numéroter les pistes"): drag-and-drop reorder of the album tracklist (numbered tracks first, unnumbered appended), then `/api/library/renumber-album` rewrites TRCK `1/N…N/N` on the whole album.
- **Artist-wide genre** (all users, artist panel → "Genre (TCON)" field): one input applied to every MP3 of the artist (all albums, recursive) via `/api/library/set-artist-genre`; `;`-separated multi-values, confirmation modal before overwrite. Prefilled with the most common genre combination across the artist's albums (`genres` field of `/api/library/album-status`).

## Threading model (SongSurf)

- Main Flask thread: HTTP, validation, enqueue. The queue lives in SQLite (`store`, SSF-03): one album = one job, a single track = a one-song job (`_enqueue_job(user, songs)`), max `MAX_PENDING_JOBS=100` jobs **per user** (`_queue_full`). Daily limit `DAILY_DOWNLOAD_LIMIT` **per member**, admin unlimited (`_daily_limit_for`), also enforced on `/api/queue-direct`. `queue_size` in `/api/status` = `store.pending_count()` (all users). The frontend submits everything at once; the server owns ordering and the batch keeps draining even if the page is closed.
- One download worker thread (`_worker_step`): `store.claim_next()` takes the next song **round-robin between users** (each user's songs in arrival order), `_process_song`, then `store.finish()` — a song only leaves the queue once processed, so a restart mid-download re-downloads it (`StateStore._recover`); `_resume_pending_batch()` reopens the progress batch at boot. `_queue_wakeup` (Event) wakes the worker on enqueue. Updates `download_status` under `queue_lock` (lock order: `queue_lock` → store lock).
- `/api/status` `worker`: who uses the worker — members get `songs_before_mine` only, the admin also gets `owner` (pseudo) + `current`. A token-only call (Watcher busy probe, no identity) gets `{in_progress, queue_size}` — before SSF-03 it got 503 and the Watcher could stop SongSurf mid-batch.
- Extension queueing is server-side fire-and-forget: `/api/queue-direct` spawns a daemon thread (`_queue_direct_async`) that extracts metadata then `_enqueue_job`, and returns immediately. No `extension_pending`/visual-queue round-trip anymore — the NAS downloads even with no SongSurf tab open.
- Watcher side: inactivity thread (`_inactivity_tick` every 60 s: warn after `INACTIVITY_WARN_TIMEOUT`, stop container after `+ INACTIVITY_GRACE_TIMEOUT`). A busy SongSurf (`in_progress` or `queue_size > 0` via `_songsurf_busy()`) counts as activity — never stopped mid-batch; `_start_songsurf()` resets the idle timer (boot-window race). Same busy check on `/logout`.

## Environment variables

`.env` (non-secret): `DEPLOY_TARGET`, `WATCHER_PORT`, `SONGSURF_PORT`, `TARGET_URL(_NAS)`, `DAILY_DOWNLOAD_LIMIT`, `MAX_DURATION_SECONDS`, `INACTIVITY_WARN_TIMEOUT`, `INACTIVITY_GRACE_TIMEOUT`, `DEV_MODE`, `REVAUTH_HOME_URL`, `ADMIN_UID` (portal UUID of the admin, NAS only — mount target of the Jellyfin library, compose refuses to start without it), `AUTH_EVENTS_URL` (empty = activity tracking off). `SONGSURF_STATE_DIR` (default `/data/state`) overrides the SQLite location.

`.secrets` (chmod 600, never committed, generated by `make secrets`): `WATCHER_SECRET`, `SONGSURF_EVENTS_SECRET` (must match `auth/.secrets` on the VPS), `SONGSURF_PROXY_SECRET` (must match the secret file Caddy reads on the VPS; empty = service locked), Flask secret keys.

`YTDLP_COOKIES_DIR` (default `/data/cookies`, volume `./data/cookies`): **per-user** YouTube cookies `<uid>.txt` (chmod 600, Netscape format) written by the extension via `/api/cookies/update`. yt-dlp always uses the cookies of the job owner — no global file, no fallback on admin cookies: a user without cookies gets `403 {code: 'cookies_missing'}` on `/api/extract`, `/api/preview`, `/api/download`, `/api/download-playlist`, `/api/queue-direct`.

## Gotchas

- `SONGSURF_PROXY_SECRET` must match the secret Caddy reads on the VPS — rotating it requires restarting both sides. Same constraint for `SONGSURF_EVENTS_SECRET` (activity-event push, `auth/.secrets`).
- Port 8081 (SongSurf) must never be exposed to WAN; only Watcher faces traffic.
- CORS (watcher) allows **only** `chrome-extension://<SONGSURF_EXTENSION_ID>`; the ID is pinned by the `key` field of `chrome-extension/manifest.json` (test `test_cors_extension_id_matches_manifest` keeps both in sync). Never re-add `null` or `chrome-extension://*`.
- Request bodies are capped at 20 MB (`MAX_REQUEST_MB`, rejected in `before_request` — route-level `try/except` would turn Flask's 413 into a 500).
- `/api/status` only returns the caller's `last_completed` / `last_error` (`_last_*_by_user`); `current_download` is `null` when it belongs to someone else.
- Frontend changes require a rebuild: Docker multi-stage builds it (`make up --build` / `make deploy-nas`); for local no-Docker dev use `make frontend-dev`.
- Download cancellation does not exist (dead `cancel_flag` removed in SSF-02); it will come back with feature F2.
- yt-dlp is **pinned** in `server/requirements.txt` (no update at boot): when YouTube breaks extraction, `make bump-ytdlp` (or `VERSION=…`) then rebuild/`make deploy-nas`.
- Both services run under **waitress** (single process, multi-thread — never gunicorn multi-process: queue/status state is process-global) with `init: true` (tini). SIGTERM → clean exit 0 (SongSurf deletes the current song's temp files; incomplete `*.part`/`*.temp.*` are also purged at boot).
- Healthcheck uses `$${FLASK_PORT}` (resolved inside the container) — `${…}` would be resolved from the host `.env` and hit the wrong port.
- Path containment checks use `Path.is_relative_to()` everywhere (migrated 2026-06); never reintroduce `str.startswith()` (prefix-match flaw: `/music/user` matches `/music/user2`).
- Extension DOM scraping of music.youtube.com is fragile (virtual scrolling, selector drift) — see memory/project notes.
- The zsh `chpwd` hook on this dev machine (eza tree) hangs non-interactive shells: use `git -C <path>` instead of `cd && git`.

## Roadmap context

- Work follows `docs/PLAN_V1.md` step by step: each ticket is a GitHub issue `[SSF-0X]` that opens with questions the **user** answers before any code. Never decide them yourself.
- Long-term vision: Auth (rev0auth) + SongSurf as two independent services under one unified site. V1 only prepares this (auth isolated behind one interface).
- Frontend: SongSurf is **adapted** to the shared `MyCss` design system, never rebuilt from scratch.
- The public showcase (SongSurf + Jellyfin demo) lives in the `portfolio` repo, not here. Ideas: `docs/VITRINE_IDEAS.md`.

## Documentation map

| File | Contents |
|---|---|
| `README.md` | User/dev-facing overview, quick start, self-hosting |
| `docs/ARCHITECTURE.md` | Components, request lifecycle, threading, frontend |
| `docs/API_OR_MODULES.md` | Full HTTP API + module reference |
| `docs/CONNECTOR.md` | rev0auth ↔ SongSurf portal-gate contract (implemented) |
| `docs/TEST_PLAN.md` | Test matrix (automated + manual) |
| `docs/DEPLOY.md` | NAS deployment guide, `make deploy-nas`, Synology pitfalls |
| `docs/AUDIT_2026-10-15.md` | Audit findings (S/R/E/M/F codes) |
| `docs/PLAN_V1.md` | Step-by-step plan to V1 — decisions are the user's, ask before coding each step |
| `docs/VITRINE_IDEAS.md` | Public showcase ideas for the portfolio (handoff notes) |
| GitHub issues `[SSF-0X]` | One ticket per plan step; handoff = one comment per role (`ticket-handoff` workflow) |
