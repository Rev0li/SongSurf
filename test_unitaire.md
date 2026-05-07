# test_unitaire.md — SongSurf Test Plan

Describes all tests to validate security, auth pipeline, and download functionality.

**Status (2026-05-07):** pytest suite added — `SongSurf/tests/` — 99 automated tests, 99 passing.
Run: `cd SongSurf && python3 -m pytest`

Automated coverage:
- W-1 → W-9, W-10/11 (JWT validation, DEV_MODE, secret, claims, tamper)
- S-1 → S-4 (Watcher-token auth, header injection, role normalization)
- D-1 → D-5, D-9 (URL validation, download-while-busy rejection)
- ST-3, ST-4 (user isolation, path traversal)
- Z-3 (ZIP without prepare)
- A-1 (admin-only route)

Remaining manual tests: W-12/13, D-6→D-8, D-10→D-14, ST-1/2, Z-1/2/4, I-1→5, P-1→5 (require Docker + yt-dlp network).

---

## 1. Auth / Security — Watcher

### 1.1 JWT validation

| # | Test | How | Expected |
|---|------|-----|----------|
| W-1 | Valid JWT accepted | Send request with `access_token` cookie containing valid HS256 JWT (`sub`, `role`, `email`, `token_type=access`, non-expired `exp`) | 200 — proxied to SongSurf |
| W-2 | Expired JWT rejected | Same as W-1 but `exp` in the past | Redirect to `AUTH_SERVICE_LOGIN_URL` (or 503) |
| W-3 | Wrong algorithm rejected | JWT signed with RS256 | Redirect / 503 |
| W-4 | Wrong secret rejected | JWT signed with a different secret | Redirect / 503 |
| W-5 | Missing `token_type` claim | JWT without `token_type=access` (e.g. refresh token) | Redirect / 503 |
| W-6 | Missing `sub` or `role` claim | JWT without required claims | Redirect / 503 |
| W-7 | No cookie at all | Request with no `access_token` cookie | Redirect to `AUTH_SERVICE_LOGIN_URL` if set, else 503 |
| W-8 | Tampered JWT payload | Modify base64 payload without re-signing | Redirect / 503 |
| W-9 | `JWT_SECRET` empty | Start Watcher without `JWT_SECRET` set | Every request → 503 (not crash), warning in logs |

### 1.2 DEV_MODE bypass

| # | Test | How | Expected |
|---|------|-----|----------|
| W-10 | DEV_MODE=true bypasses JWT | No cookie, `DEV_MODE=true` | 200 — user is `dev-user-local`, role `admin` |
| W-11 | DEV_MODE=false requires JWT | No cookie, `DEV_MODE=false` | Redirect / 503 |

### 1.3 AUTH_SERVICE_LOGIN_URL redirect

| # | Test | How | Expected |
|---|------|-----|----------|
| W-12 | Redirect when configured | Set `AUTH_SERVICE_LOGIN_URL`, send unauthenticated request | 302 redirect to `AUTH_SERVICE_LOGIN_URL` |
| W-13 | 503 fallback | Unset `AUTH_SERVICE_LOGIN_URL`, send unauthenticated request | 503 + `unavailable.html` |

---

## 2. Auth — Watcher → SongSurf header injection

| # | Test | How | Expected |
|---|------|-----|----------|
| S-1 | `X-Watcher-Token` required | Send request directly to SongSurf `:8081` without header | 401 or 503 |
| S-2 | Wrong `X-Watcher-Token` | Send request to SongSurf with wrong token value | 401 |
| S-3 | Headers injected correctly | Authenticate via Watcher, check SongSurf receives `X-User-Id`, `X-User-Role`, `X-User-Email` | Headers match JWT claims |
| S-4 | Role lowercase | JWT has `role: "Admin"` (capitalized) | SongSurf receives `x-user-role: admin` |

---

## 3. Download pipeline

### 3.1 URL validation

| # | Test | How | Expected |
|---|------|-----|----------|
| D-1 | Valid YouTube URL accepted | POST `/api/extract` with `https://music.youtube.com/watch?v=xxx` | 200 + metadata |
| D-2 | Non-HTTPS URL rejected | POST `/api/extract` with `http://youtube.com/...` | 400 — URL invalide |
| D-3 | Non-YouTube domain rejected | POST `/api/extract` with `https://vimeo.com/...` | 400 — URL invalide |
| D-4 | XSS in URL rejected | URL containing `<script>` or `"` | 400 — URL invalide |
| D-5 | Empty URL rejected | POST `/api/extract` with `url: ""` | 400 — URL manquante |

### 3.2 Single download

| # | Test | How | Expected |
|---|------|-----|----------|
| D-6 | Download queued | POST `/api/download` with valid URL + metadata | 200 `{"success": true, "queue_size": 1}` |
| D-7 | Download completes | Wait for worker, check `GET /api/status` | `last_completed.success = true`, file in `/data/music/<sub>/` |
| D-8 | File organized correctly | Check output path | `Artist/Album/Title.mp3` |
| D-9 | Reject while busy | POST `/api/download` when one is in progress | 429 — download en cours |
| D-10 | Cancel in-progress | POST `/api/cancel` | Download stops, `in_progress = false` |

### 3.3 Playlist download

| # | Test | How | Expected |
|---|------|-----|----------|
| D-11 | Playlist extracted | POST `/api/extract` with playlist URL | `is_playlist: true`, `songs[]` populated |
| D-12 | Playlist queued | POST `/api/download-playlist` | `added` = number of songs, queue fills |
| D-13 | Batch progress | Poll `/api/status` during playlist | `batch_active: true`, `batch_percent` increases |
| D-14 | Queue limit respected | Playlist > 50 songs | Only 50 queued, rest dropped silently |

---

## 4. Storage routing

| # | Test | How | Expected |
|---|------|-----|----------|
| ST-1 | Admin files not deleted after ZIP | Download as Admin, GET `/api/download-zip` | Files remain in `/data/music/<sub>/` after 60s |
| ST-2 | Member files deleted after ZIP | Download as Member, GET `/api/download-zip` | Files removed from `/data/music/<sub>/` after 60s |
| ST-3 | Per-user isolation | Two users (different `sub`) download | Each has their own `/data/music/<sub>/` folder, no cross-access |
| ST-4 | Path traversal blocked | Library endpoints with `../` in paths | 400 — chemin invalide |

---

## 5. ZIP flow

| # | Test | How | Expected |
|---|------|-----|----------|
| Z-1 | ZIP preparation | POST `/api/prepare-zip` | `{"success": true, "count": N, "size_mb": X}` |
| Z-2 | ZIP download | GET `/api/download-zip` after prepare | File downloaded, `Content-Disposition: attachment` |
| Z-3 | ZIP not ready | GET `/api/download-zip` without prepare | 404 |
| Z-4 | ZIP contains all files | Inspect ZIP | All `.mp3` from user's music dir are present |

---

## 6. Inactivity / container lifecycle

| # | Test | How | Expected |
|---|------|-----|----------|
| I-1 | Inactivity warning emitted | No requests for `INACTIVITY_WARN_TIMEOUT` seconds | Log warning, `/watcher/inactivity-status` returns `warned: true` |
| I-2 | SongSurf stopped after grace | No requests for `INACTIVITY_WARN_TIMEOUT + INACTIVITY_GRACE_TIMEOUT` | SongSurf container stopped |
| I-3 | Keepalive resets timer | POST `/watcher/keepalive` | `idle_seconds` resets, `warned: false` |
| I-4 | Keepalive requires auth | POST `/watcher/keepalive` without cookie | 401 |
| I-5 | `/api/status` is passive | Poll `/api/status` only | Timer not reset (passive path) |

---

## 7. Watcher proxy robustness

| # | Test | How | Expected |
|---|------|-----|----------|
| P-1 | SongSurf down → loading page | Stop SongSurf, browser request | 302 to `/watcher/loading` |
| P-2 | SongSurf auto-started | Make request when container is stopped | Watcher starts it, eventually proxies |
| P-3 | Loading page retries | `/watcher/loading` | JS polls `/watcher/ready`, redirects when ready |
| P-4 | API callers get 503 JSON | Fetch to `/api/*` when SongSurf down | `{"success": false, "retry": true}`, status 503 |
| P-5 | Retry loop limit | `_r` counter in URL | Capped at 10 to avoid infinite redirect loop |

---

## 8. Admin-only routes

| # | Test | How | Expected |
|---|------|-----|----------|
| A-1 | `/api/admin/extract-covers` requires admin | Call with Member JWT | 403 — Admin requis |
| A-2 | Admin can call it | Call with Admin JWT | 200 — covers extracted |

---

## Integration checklist (pre-deploy to prod)

- [ ] W-1 through W-9 all pass with real auth-selfhost-rust JWT
- [ ] `DEV_MODE=false` in `.env`
- [ ] `JWT_SECRET` same value in Watcher `.env` and auth-selfhost-rust `.env`
- [ ] `AUTH_SERVICE_LOGIN_URL` points to live auth login page
- [ ] NAS firewall blocks port 8081 from WAN
- [ ] SongSurf port NOT published in `docker-compose.local.yml` (already done)
