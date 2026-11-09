# SongSurf

Self-hosted YouTube Music downloader with clean, Jellyfin-ready libraries.

```
Browser ──► reverse proxy (auth gate) ──identity + proof──► [SongSurf :8081] ──► yt-dlp ──► FFmpeg ──► /data/music/<user>/Artist/Album/Title.mp3
```

A single container (~40 MB RAM idle) that trusts the identity sent by your reverse proxy only when it carries a shared proof.

## Features

- **Single songs, albums and playlists** from YouTube / YouTube Music → best-quality MP3 (FFmpeg)
- **Clean ID3 tags**: title, album, year, **track number** (`n/total`), **multi-value artists** (TPE1, null-separated — each artist credited individually), **album artist** (TPE2 — stable album grouping in Jellyfin), embedded cover + `cover.jpg` sidecar
- **Featuring detection** — `Song feat. X` is normalized into the title and credited in the artist tag
- **Per-user libraries** — each authenticated user gets `/data/music/<portal UUID>/` (a `.owner` file names the pseudo); members can export their library as a ZIP (deleted afterwards), the admin library is permanent
- **Fair, restart-proof queue** — songs are served round-robin between users (two members progress side by side), with a per-member daily quota; the queue, quotas and ZIP exports live in SQLite and survive restarts
- **Web UI** (SvelteKit): URL queue with metadata preview/edit, library tree with drag-and-drop, full **ID3 metadata editor** (multi-value support with `;`), cover upload
- **Browser extension** (Chrome/Firefox): one-click queue from music.youtube.com pages, batch an artist's full discography, YouTube cookie sync for yt-dlp
- **Auth delegated to a reverse proxy**: a gate (e.g. Caddy `forward_auth` + [rev0auth](https://github.com/Rev0li)) authenticates users and passes their identity with a shared proof, or `DEV_MODE` for local use

## Requirements

- Docker + Docker Compose
- For production auth: a reverse proxy that authenticates users and sends `X-User-Name` / `X-User-Role` / `X-User-Id` plus `X-Proxy-Token` (see `docs/CONNECTOR.md`)
- For frontend development only: Node 22+

## Quick start (local)

```bash
cd SongSurf
make secrets      # interactive wizard → creates .env + .secrets
make up-local     # build + start (bridge network, ports on localhost)
```

Open `http://localhost:8081` (default `SONGSURF_PORT`).

For a quick try without an auth provider, set `DEV_MODE=true` in `.env` — full bypass, local admin user. **Never in production.**

Useful commands:

```bash
make logs         # stream logs
make down         # stop
make restart      # down → up
make config       # preview resolved compose config
make dev          # Flask backend only, no Docker (port 8081)
```

## Configuration

`make secrets` generates both files. `.env` holds non-secret config:

| Variable | Default | Description |
|---|---|---|
| `DEPLOY_TARGET` | `local` | `local` (bridge, published ports) or `nas` (host network) |
| `SONGSURF_PORT` | `8081` | Port your reverse proxy reaches — never expose it to the internet |
| `DEV_MODE` | `false` | `true` bypasses auth — never in production |
| `REVAUTH_HOME_URL` | _(empty)_ | Portal member space: target after logout, link on the « use the portal » page |
| `DAILY_DOWNLOAD_LIMIT` | `0` | Downloads per member per day (admin unlimited), `0` = unlimited |
| `MAX_DURATION_SECONDS` | `9000` | Reject videos longer than this (2h30 allows DJ mixes) |
| `ADMIN_UID` | — | Portal UUID of the admin account (NAS only): the Jellyfin music folder is mounted on `/data/music/<ADMIN_UID>` |

`.secrets` (chmod 600, never committed): `SONGSURF_PROXY_SECRET` (proof sent by your reverse proxy in `X-Proxy-Token`; empty = service locked), `SONGSURF_EVENTS_SECRET` (optional activity push), Flask secret key.

## Production deployment (NAS)

```bash
make up-nas              # on the NAS: host network, portal gate required
# or, from your dev machine (rsync + remote rebuild):
make deploy-nas NAS_USER=<user> NAS_HOST=<ip> NAS_DIR=/volume1/docker/songsurf
```

Typical topology: reverse proxy (Caddy/Nginx + TLS) on a VPS → Tailscale tunnel → NAS. The SongSurf port must never be exposed to the internet: only the reverse proxy reaches it (LAN / tunnel).

Guide: [`docs/DEPLOY.md`](docs/DEPLOY.md) (full setup, `make deploy-nas`, Synology pitfalls).

## Browser extension

`chrome-extension/` — Manifest V3, works on Chrome and Firefox.

1. Load it unpacked (`chrome://extensions` → Developer mode → *Load unpacked*).
2. Open the extension options and set your SongSurf URL.
3. On music.youtube.com: a queue button appears on song/album/playlist pages; on artist pages, batch-queue the whole *Albums* shelf (artist + album names scraped from the page).
4. The extension can also sync your YouTube cookies to SongSurf so yt-dlp can access content that requires a session.

## Development

```
SongSurf/SongSurf/            # the app (nested folder)
  server/
    app.py                    # Flask app, CORS, blueprints, startup
    auth/                     # who is the user (portal gate, dev mode)
    core/                     # config, storage, queue, worker, ID3 tags
    routes/                   # HTTP routes, one file per domain
    downloader.py             # yt-dlp wrapper, extraction, progress
    organizer.py              # file placement, ID3 tags, covers
    state_store.py            # SQLite: queue (round-robin), quotas, ZIP exports
  frontend/                   # SvelteKit (adapter-static, built into the image)
  tests/                      # pytest suite
  docker/compose-switch.sh    # merges base + local|nas compose files
  scripts/migrate_to_uid.py   # one-shot SSF-03 migration: pseudo folders → portal UUID
chrome-extension/             # MV3 extension
docs/                         # architecture, API reference, auth contract, deploy, V1 plan
```

```bash
python3 -m pytest             # run the test suite (~290 tests) from SongSurf/SongSurf/
make frontend-dev             # SvelteKit dev server with hot reload (port 5173)
make frontend-build           # build the static bundle locally
```

No linter is configured. The frontend is rebuilt automatically by the Docker multi-stage build (`make up --build`, `make deploy-nas`).

Docs for contributors:

| File | Contents |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Components, request lifecycle, threading model, frontend |
| [`docs/API_OR_MODULES.md`](docs/API_OR_MODULES.md) | Full HTTP API + module reference |
| [`docs/CONNECTOR.md`](docs/CONNECTOR.md) | Portal-gate contract with the auth service |
| [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) | Test matrix (automated + manual) |
| [`docs/PLAN_V1.md`](docs/PLAN_V1.md) | Step-by-step plan to V1 (from the 2026-10-15 audit) |

## Security notes

- `.secrets` is chmod 600 and never committed
- All URLs are validated (HTTPS + YouTube/YouTube Music domains only)
- SongSurf only trusts an identity carrying the reverse proxy's `X-Proxy-Token` proof (constant-time compare); empty secret = locked
- Containers run as uid 1000 (non-root)
- Per-user path containment checks on every library endpoint

## License

[MIT](SongSurf/LICENSE)
