# test_unitaire.md — SongSurf Test Plan

Describes all tests to validate security, auth pipeline, and download functionality.

**Status (2026-06-10):** pytest suite — `SongSurf/tests/` — 110 automated tests, 110 passing.
Run: `cd SongSurf && python3 -m pytest`
New coverage since 2026-05: track number (TRCK) pass-through, multi-artist TPE1 list, album artist TPE2, artist string splitting (`_split_artists` / `_artist_list`).

Automated coverage:
- W-1 → W-9, W-10/11 (JWT validation, DEV_MODE, secret, claims, tamper)
- W-14 → W-19 (SSF-11 portal gate: proof, ignored headers, double acceptance, forwarded headers)
- S-1 → S-4 (Watcher-token auth, header injection, role normalization)
- D-1 → D-5, D-9 (URL validation, download-while-busy rejection)
- ST-3, ST-4 (user isolation, path traversal)
- Z-3 (ZIP without prepare), Z-5 + ST-1/ST-2 (SSF-10: admin ZIP disabled, member library purged)
- A-1 (admin-only route)

Remaining manual tests: W-12/13, W-20/21, D-6→D-8, D-10→D-14, Z-1/2/4, Z-6, I-1→5, P-1→5 (require Docker + yt-dlp network).

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

### 1.4 Portal gate — AUTH-09 (SSF-11, `tests/test_watcher_proxy_gate.py`)

| # | Test | How | Expected |
|---|------|-----|----------|
| W-14 | Valid proof → portal identity | `X-Proxy-Token` = `SONGSURF_PROXY_SECRET` + `X-User-Name/Role/Id` | `sub` = exact pseudo, role lowercased, `uid` = portal UUID |
| W-15 | Missing / wrong proof | Same headers, proof absent, empty, wrong or non-ASCII | Identity headers ignored; wrong proof logged |
| W-16 | Secret not configured | `SONGSURF_PROXY_SECRET` empty | Headers never trusted, whatever the proof |
| W-17 | Incomplete identity | Valid proof without `X-User-Name` or `X-User-Role` (or blank name) | Rejected |
| W-18 | Double acceptance | JWT cookie without proof; both present; forged headers without proof on `/` and `/watcher/*` | JWT still accepted; gate wins; forged → redirect to login / 401 |
| W-19 | Forwarded headers | Proxied request with forged `X-User-Email` / `X-Watcher-Token` | SongSurf gets the Watcher's own values + `X-User-Portal-Id`, never `X-Proxy-Token` / `X-User-Name` |
| W-20 | **Manual (NAS, after step 3)** — through the gate | Open `https://songsurf.rev0li.duckdns.org` logged in / logged out of the portal | Logged in: library of the right account; logged out: portal login |
| W-21 | **Manual (extension)** — portal session | Queue a song logged in, then logged out of the portal | Logged in: queued (the portal cookie is sent); logged out: clickable « Non connecté » toast that opens SongSurf |

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
| D-10 | ~~Cancel in-progress~~ | — | **Not implemented** (dead `cancel_flag` removed in SSF-02; comes back with F2) |

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
| ST-1 | Admin library never exported nor deleted | `test_ssf10_admin_zip_disabled`: POST `/api/prepare-zip` / GET `/api/download-zip` as Admin | 403 `zip_disabled`, files untouched |
| ST-2 | Member files deleted after ZIP | `test_ssf10_member_zip_still_purges_member_library`: prepare then download as Member | `/data/music/<pseudo>/` removed once the stream completes |
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
| Z-5 | ZIP refused on the admin folder, whatever the role | `test_ssf10_zip_refused_on_admin_dir_whatever_the_role` | 403, admin folder untouched even with a ZIP already prepared |
| Z-6 | **Manual (NAS)** — no ZIP button for the admin | Open SongSurf as admin, then as a member | Admin: no « 📥 Télécharger ZIP » button; member: button present |

---

## 6. Inactivity / container lifecycle

| # | Test | How | Expected |
|---|------|-----|----------|
| I-1 | Inactivity warning emitted | No requests for `INACTIVITY_WARN_TIMEOUT` seconds | Log warning, `/watcher/inactivity-status` returns `warned: true` |
| I-2 | SongSurf stopped after grace | No requests for `INACTIVITY_WARN_TIMEOUT + INACTIVITY_GRACE_TIMEOUT` | SongSurf container stopped |
| I-3 | Keepalive resets timer | POST `/watcher/keepalive` | `idle_seconds` resets, `warned: false` |
| I-4 | Keepalive requires auth | POST `/watcher/keepalive` without cookie | 401 |
| I-5 | `/api/status` is passive | Poll `/api/status` only | Timer not reset (passive path) |
| I-6 | Busy download defers stop | Queue a long batch, close everything, wait past the timeouts | Container keeps running until the batch drains (busy = activity) |
| I-7 | No stop during boot window | Return after a long idle (container stopped) | `_start_songsurf` resets the timer; the container is not re-stopped while booting |

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

## 9. SSF-01 hardening (CORS, per-user cookies, request size, status isolation)

| # | Test | How | Expected |
|---|------|-----|----------|
| H-1 | CORS only for SongSurf Clip | `OPTIONS` with `Origin: null` / other `chrome-extension://…` / `https://evil.com` (`test_cors_*`) | 403, no `Access-Control-Allow-Origin` |
| H-2 | Extension ID pinned | `test_cors_extension_id_matches_manifest` | ID derived from manifest `key` = `SONGSURF_EXTENSION_ID` |
| H-3 | No cookies → blocked | `/api/extract`, `/api/preview`, `/api/download`, `/api/download-playlist`, `/api/queue-direct` without `<pseudo>.txt` | 403 `cookies_missing` + message pointing to the extension; no fallback on admin cookies |
| H-4 | Cookies stored per user | `/api/cookies/update` | `/data/cookies/<pseudo>.txt`, chmod 600, response carries `pseudo`; bad format → 400 |
| H-5 | Worker uses owner cookies | `test_ssf01_worker_*` | `cookiefile` = owner's file; file removed after queueing → clean error |
| H-6 | Request size cap | Body > 20 MB | 413 JSON "max 20 Mo" (not 500) |
| H-7 | `/api/status` isolation | Two members | Other member's `last_completed` / `last_error` / `current_download` never returned |
| H-8 | Legacy cookies migration | Boot with `/data/cookies.txt` | Moved to `/data/cookies/<ADMIN_PSEUDO>.txt` |
| H-10 | Clean stop (SSF-02) | `docker stop songsurf` on the NAS (`time`, then `docker inspect -f '{{.State.ExitCode}}'`) | < 2 s, exit 0; `test_ssf02_*` cover temp cleanup |
| H-11 | Healthcheck (SSF-02) | `docker inspect -f '{{.State.Health.Status}}' songsurf` on the NAS | `healthy` |
| H-9 | **Manual, real extension on the NAS** | Reload the unpacked extension (new fixed ID → re-enter the SongSurf URL in options), Sync cookies, queue a song | Popup shows "Cookies synchronisés pour <pseudo>"; download OK; a member without sync sees the blocking message |

---

## Integration checklist (pre-deploy to prod)

- [ ] W-1 through W-9 all pass with real auth-selfhost-rust JWT
- [ ] `DEV_MODE=false` in `.env`
- [ ] `JWT_SECRET` same value in Watcher `.env` and auth-selfhost-rust `.env`
- [ ] `AUTH_SERVICE_LOGIN_URL` points to live auth login page
- [ ] NAS firewall blocks port 8081 from WAN
- [ ] SongSurf port NOT published in `docker-compose.local.yml` (already done)
