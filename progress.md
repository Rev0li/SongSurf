# SongSurf — Progress & Next Session

_Last updated: 2026-04-21_

---

## Phase 3 — JWT Integration ✅ DONE

- `watcher/watcher.py`: JWT HS256 validation implemented (`_validate_jwt`, `_extract_jwt_from_request`)
- `_get_user_from_request()` now reads `access_token` cookie and validates via PyJWT
- Unauthenticated → redirects to `AUTH_SERVICE_LOGIN_URL` if set, else 503
- `watcher/requirements.txt`: `PyJWT>=2.8.0` added
- `docker-compose.yml`: `AUTH_JWT_SECRET` and `AUTH_SERVICE_LOGIN_URL` env vars uncommented/added
- New env vars needed in `.env`:
  - `AUTH_JWT_SECRET=<same value as rev0auth>`
  - `AUTH_SERVICE_LOGIN_URL=<auth login page URL>`
  - `DEV_MODE=false` for production

---

## SvelteKit Frontend ✅ SCAFFOLDED

Vanilla JS IIFE replaced with a proper SvelteKit SPA.

### Architecture
```
SongSurf/frontend/        ← SvelteKit project (Svelte 4, adapter-static)
  src/
    lib/
      api.js              ← thin HTTP client (ES module)
      stores.js           ← user, downloadStatus, workerBusy, recentDownloads, toasts
      utils.js            ← helpers (primaryArtist, resolveCoverCandidates, etc.)
      components/
        DownloadPanel.svelte    ← URL input + metadata form + download
        ProgressZone.svelte     ← batch progress bar
        RecentDownloads.svelte  ← history list + ZIP button
        LibraryTree.svelte      ← tree with search, drag-drop, rename, image upload
        Toast.svelte            ← toast notifications
        WatcherInactivity.svelte← inactivity warning banner
    routes/
      +layout.js          ← SPA mode (ssr=false, prerender=false)
      +layout.svelte      ← loads /api/me, polls /api/status every 1.5s
      +page.svelte        ← dashboard grid
      donation/
        +page.svelte      ← donation page (fetches /api/donation-config)
  build/                  ← prod output (git-ignored)
  package.json            ← Svelte 4.2.20, SvelteKit 2.9.0, Vite 5.4.0
```

### New Flask endpoints
- `GET /api/me` → `{ sub, role, email }` (auth required)
- `GET /api/donation-config` → `{ btc, eth, sol, xmr }` (auth required)
- `GET /_app/<path>` → SvelteKit JS/CSS bundles (no auth)
- `/` and `/donation` now serve `frontend/build/index.html` (SPA entry point)

### Dev workflow
```bash
# Terminal 1: Flask backend (DEV_MODE=true)
cd SongSurf/server && DEV_MODE=true python app.py

# Terminal 2: SvelteKit dev server with hot-reload
cd SongSurf/frontend && npm run dev
# → http://localhost:5173 (proxies /api → :8081, /static → :8081)

# Production build
cd SongSurf/frontend && npm run build
# → output in frontend/build/, served by Flask
```

### Docker
No changes needed — `npm run build` must run before building the Docker image.
Add to Dockerfile or CI: `cd frontend && npm ci && npm run build`

---

## Known issues / next steps

### Frontend
- A11y warnings in build output (label/input association, ARIA roles on draggable divs) — cosmetic, don't affect function. Fix by adding `for`/`id` pairs and `role="row"` on song items.
- `LibraryTree.svelte`: `refresh()` is called via `bind:this` from `+page.svelte`. Called after download queued and after status poll detects a completed download.

### Integration with rev0auth (Phase 3 activation)
1. Set `AUTH_JWT_SECRET=<same as rev0auth>` in `.env`
2. Set `AUTH_SERVICE_LOGIN_URL=http://<auth-host>/login` in `.env`
3. Set `DEV_MODE=false`
4. Rebuild and redeploy

### Docker build
Add to the Dockerfile or a build script:
```dockerfile
# In songsurf Dockerfile, before COPY:
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
```
Or build the frontend locally before `docker build` (current approach).
