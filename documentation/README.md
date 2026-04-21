# SongSurf

A self-hosted YouTube Music downloader with a dual-role dashboard (Admin / Guest), organized MP3 library output, and a lightweight authentication proxy.

---

## Overview

SongSurf is built around two Docker services:

| Service | Port | Role |
|---|---|---|
| **Watcher** | 8080 (public) | Always-on auth gateway + inactivity monitor |
| **SongSurf** | 8081 (internal) | Download engine, started on demand by Watcher |

Users never reach SongSurf directly. All traffic goes through Watcher, which handles login, proxies authenticated requests, and shuts SongSurf down after a configurable idle period.

---

## Prerequisites

- Docker + Docker Compose v2
- `.env` file (copy from `.env.example`)

For NAS/production:
- Synology NAS (DSM 7+) or any Linux host
- (Optional) Tailscale for VPN access
- (Optional) VPS with Nginx + DuckDNS + Let's Encrypt for HTTPS

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> && cd bot_music

# 2. Configure environment
cp .env.example .env
# Edit .env — set at minimum:
#   DEPLOY_TARGET=local
#   WATCHER_FLASK_SECRET_KEY=<32+ random chars>
#   SONGSURF_FLASK_SECRET_KEY=<32+ random chars>
#   WATCHER_SECRET=<shared secret>
#   WATCHER_PASSWORD=<admin password>
#   WATCHER_GUEST_PASSWORD=<guest password>

# 3. Start services
./docker/compose-switch.sh up -d --build

# 4. Open in browser
open http://localhost:8080
```

---

## Deployment Modes

The project uses a compose-switch pattern controlled by `DEPLOY_TARGET` in `.env`.

| `DEPLOY_TARGET` | Compose files | Network | Use case |
|---|---|---|---|
| `local` | base + local override | bridge + published ports | Development |
| `nas` | base + nas override | `host` (direct NAS network) | Production NAS |

```bash
# Preview resolved config before applying
./docker/compose-switch.sh config

# Force a mode without touching .env
DEPLOY_TARGET=nas ./docker/compose-switch.sh up -d --build

# View logs
./docker/compose-switch.sh logs -f

# Stop
./docker/compose-switch.sh down
```

---

## NAS Deployment (Production)

```bash
# On the NAS
mkdir -p /volume1/docker/SongSurf
cd /volume1/docker/SongSurf
git clone <repo-url> .

# Or from local machine
rsync -av --delete . <user>@<nas>:/volume1/docker/SongSurf/

cp .env.example .env
# Edit .env with DEPLOY_TARGET=nas and your secrets

./docker/compose-switch.sh up -d --build
# Portal at http://<NAS-IP>:8080
```

### Nginx reverse proxy (VPS → NAS via Tailscale)

```nginx
server {
    listen 443 ssl;
    server_name songsurf.yourdomain.duckdns.org;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.duckdns.org/privkey.pem;

    location / {
        proxy_pass         http://<tailscale-nas-ip>:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }
}
```

---

## Updating

```bash
# After changing Python source files (app.py, downloader.py, organizer.py, watcher.py)
./docker/compose-switch.sh down
./docker/compose-switch.sh up -d --build

# After changing only HTML templates — no rebuild needed
# Templates are hot-reloaded via volume mount
```

---

## Data Directories (Inside Containers)

| Path | Contents |
|---|---|
| `/data/music` | Admin library: `Artist/Album/Title.mp3` |
| `/data/music_guest/<session_id>/` | Guest session files (auto-cleaned after TTL) |
| `/data/temp` | Admin download staging area |
| `/data/temp_guest` | Guest download staging area |
| `/app/logs/activity.log` | Human-readable activity log |

---

## Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DEPLOY_TARGET` | `local` | `local` or `nas` |
| `WATCHER_SECRET` | — | **Required.** Shared secret between Watcher and SongSurf |
| `WATCHER_PASSWORD` | — | Admin portal password |
| `WATCHER_GUEST_PASSWORD` | — | Guest portal password |
| `WATCHER_FLASK_SECRET_KEY` | — | Watcher session encryption key |
| `SONGSURF_FLASK_SECRET_KEY` | — | SongSurf session encryption key |
| `GUEST_MAX_SONGS` | `10` | Per-session download quota (`0` = unlimited) |
| `GUEST_SESSION_TTL` | `3600` | Guest session lifetime in seconds |
| `GUEST_WARN_BEFORE_SECONDS` | `300` | UI warning threshold before session expiry |
| `MAX_DURATION_SECONDS` | `9000` | Max download duration (2h30 — for DJ mixes) |
| `INACTIVITY_TIMEOUT` | `1800` | Seconds idle before Watcher warns admin |
| `INACTIVITY_GRACE_TIMEOUT` | `900` | Additional seconds before forced container stop |

---

## Logs & Troubleshooting

```bash
# Live Docker logs
./docker/compose-switch.sh logs -f

# Activity log (human-readable)
cat /volume1/docker/SongSurf/logs/activity.log
# Format: 2026-03-16 14:25:12 | 🎵 DOWNLOAD | Alice | The Weeknd - Blinding Lights
```

| Problem | Fix |
|---|---|
| Port 8080 not reachable | Check NAS firewall + `docker compose ps` |
| `Permission denied` on `/data/music` | `chown 1000:1000` on the host folder |
| `yt-dlp` download fails | Restart container to force yt-dlp auto-update |
| Guest session expired mid-download | Cleanup is delayed 120s after ZIP download |
| SongSurf not starting | Check Watcher logs — it controls container lifecycle |

---

## Admin Workflow

1. Paste a YouTube Music URL (song, album, or playlist)
2. Click **Analyser** → review/edit metadata (artist, title, album, year)
3. Click **Télécharger** (toggle playlist mode for albums/playlists)
4. Files land in `data/music/Artist/Album/Title.mp3`

## Guest Workflow

1. Same extract/download flow with quota limit
2. Files land in `data/music_guest/<session_id>/`
3. Download all as a ZIP before session expires
4. Session auto-cleaned after TTL
