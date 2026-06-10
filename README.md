# SongSurf

Self-hosted YouTube Music downloader with clean, Jellyfin-ready libraries.

```
Browser ──► [Watcher :8080] ──auth──► [SongSurf :8081] ──► yt-dlp ──► FFmpeg ──► /data/music/<user>/Artist/Album/Title.mp3
```

A lightweight auth proxy (**Watcher**, ~15 MB RAM, always on) sits in front of the download engine (**SongSurf**), which Watcher starts and stops on demand via the Docker SDK — the heavy container only runs while you actually use it.

## Features

- **Single songs, albums and playlists** from YouTube / YouTube Music → best-quality MP3 (FFmpeg)
- **Clean ID3 tags**: title, album, year, **track number** (`n/total`), **multi-value artists** (TPE1, null-separated — each artist credited individually), **album artist** (TPE2 — stable album grouping in Jellyfin), embedded cover + `cover.jpg` sidecar
- **Featuring detection** — `Song feat. X` is normalized into the title and credited in the artist tag
- **Per-user libraries** — each authenticated user gets `/data/music/<pseudo>/`; members can export their library as a ZIP (deleted afterwards), the admin library is permanent
- **Web UI** (SvelteKit): URL queue with metadata preview/edit, library tree with drag-and-drop, full **ID3 metadata editor** (multi-value support with `;`), cover upload
- **Browser extension** (Chrome/Firefox): one-click queue from music.youtube.com pages, batch an artist's full discography, YouTube cookie sync for yt-dlp
- **On-demand lifecycle**: automatic container shutdown after inactivity (warn → grace → stop)
- **JWT auth** via an external HS256 issuer ([rev0auth](https://github.com/Rev0li) or your own), or `DEV_MODE` for local use

## Requirements

- Docker + Docker Compose
- For production auth: any service that issues an HS256 JWT in an `access_token` cookie with `sub` / `role` / `email` / `token_type=access` claims (see `documentation/CONNECTOR.md`)
- For frontend development only: Node 20+

## Quick start (local)

```bash
cd SongSurf
make secrets      # interactive wizard → creates .env + .secrets
make up-local     # build + start (bridge network, ports on localhost)
```

Open `http://localhost:8080` (default `WATCHER_PORT`).

For a quick try without an auth provider, set `DEV_MODE=true` in `.env` — full bypass, local admin user. **Never in production.**

Useful commands:

```bash
make logs         # stream all logs
make down         # stop
make restart      # down → up
make config       # preview resolved compose config
make dev          # Flask backend only, no Docker (port 8081)
make token        # generate a test JWT (test prod-mode auth without an auth service)
```

## Configuration

`make secrets` generates both files. `.env` holds non-secret config:

| Variable | Default | Description |
|---|---|---|
| `DEPLOY_TARGET` | `local` | `local` (bridge, published ports) or `nas` (host network) |
| `WATCHER_PORT` | `8080` | Public port — the only one that should face traffic |
| `DEV_MODE` | `false` | `true` bypasses JWT auth — never in production |
| `AUTH_SERVICE_LOGIN_URL` | _(empty)_ | Login page to redirect unauthenticated users to |
| `REVAUTH_HOME_URL` | _(empty)_ | "Back to my space" link target after logout |
| `DAILY_DOWNLOAD_LIMIT` | `0` | Downloads per day, `0` = unlimited |
| `MAX_DURATION_SECONDS` | `9000` | Reject videos longer than this (2h30 allows DJ mixes) |
| `INACTIVITY_WARN_TIMEOUT` | `3600` | Idle seconds before shutdown warning |
| `INACTIVITY_GRACE_TIMEOUT` | `900` | Extra idle seconds before container stop |
| `ADMIN_PSEUDO` | `rev0admin` | Folder name for the admin library |

`.secrets` (chmod 600, never committed): `AUTH_JWT_SECRET` (shared with your auth service), `WATCHER_SECRET` (internal Watcher↔SongSurf token), Flask secret keys.

## Production deployment (NAS)

```bash
make up-nas              # on the NAS: host network, JWT auth required
# or, from your dev machine (rsync + remote rebuild):
make deploy-nas NAS_USER=<user> NAS_HOST=<ip> NAS_DIR=/volume1/docker/songsurf
```

Typical topology: reverse proxy (Caddy/Nginx + TLS) on a VPS → Tailscale tunnel → NAS. Port 8081 (SongSurf itself) must never be exposed; only Watcher faces traffic.

Guides: [`SongSurf/DEPLOY.md`](SongSurf/DEPLOY.md) (full setup) · [`deploy_action.md`](deploy_action.md) (one-command deploy) · [`deploy_troubleshooting.md`](deploy_troubleshooting.md) (Synology pitfalls).

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
    app.py                    # Flask routes, queue, auth guard, metadata API
    downloader.py             # yt-dlp wrapper, extraction, progress
    organizer.py              # file placement, ID3 tags, covers
  watcher/watcher.py          # auth proxy + container lifecycle
  frontend/                   # SvelteKit (adapter-static, built into the image)
  tests/                      # pytest suite
  docker/compose-switch.sh    # merges base + local|nas compose files
chrome-extension/             # MV3 extension
documentation/                # architecture, API reference, auth contract
```

```bash
python3 -m pytest             # run the test suite (110 tests) from SongSurf/SongSurf/
make frontend-dev             # SvelteKit dev server with hot reload (port 5173)
make frontend-build           # build the static bundle locally
```

No linter is configured. The frontend is rebuilt automatically by the Docker multi-stage build (`make up --build`, `make deploy-nas`).

Docs for contributors:

| File | Contents |
|---|---|
| [`documentation/ARCHITECTURE.md`](documentation/ARCHITECTURE.md) | Components, request lifecycle, threading model, frontend |
| [`documentation/API_OR_MODULES.md`](documentation/API_OR_MODULES.md) | Full HTTP API + module reference |
| [`documentation/CONNECTOR.md`](documentation/CONNECTOR.md) | JWT contract with the auth service |
| [`documentation/REV0AUTH_INTEGRATION.md`](documentation/REV0AUTH_INTEGRATION.md) | End-to-end integration walkthrough (French) |
| [`documentation/TEST_PLAN.md`](documentation/TEST_PLAN.md) | Test matrix (automated + manual) |

## Security notes

- `.secrets` is chmod 600 and never committed
- All URLs are validated (HTTPS + YouTube/YouTube Music domains only)
- SongSurf only accepts requests carrying the internal `X-Watcher-Token` (constant-time compare)
- Containers run as uid 1000 (non-root)
- Per-user path containment checks on every library endpoint

## License

[MIT](SongSurf/LICENSE)
