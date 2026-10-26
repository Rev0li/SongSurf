# test_unitaire.md — SongSurf Test Plan

Describes all tests to validate security, auth pipeline, and download functionality.

**Status (2026-06-10):** pytest suite — `SongSurf/tests/` — 110 automated tests, 110 passing.
Run: `cd SongSurf && python3 -m pytest`
New coverage since 2026-05: track number (TRCK) pass-through, multi-artist TPE1 list, album artist TPE2, artist string splitting (`_split_artists` / `_artist_list`).

Automated coverage:
- W-14 → W-19, W-22 → W-24 (portal gate: proof, ignored headers, forwarded headers, anonymous page/401, locked without secret, logout)
- S-1 → S-4 (Watcher-token auth, header injection, role normalization)
- D-1 → D-5, D-9 (URL validation, download-while-busy rejection)
- ST-3, ST-4 (user isolation, path traversal)
- Z-3 (ZIP without prepare), Z-5 + ST-1/ST-2 (SSF-10: admin ZIP disabled, member library purged)
- A-1 (admin-only route)

Remaining manual tests: W-10/11, W-20/21, D-6→D-8, D-10→D-14, Z-1/2/4, Z-6, I-1→5, P-1→5 (require Docker + yt-dlp network).

---

## 1. Auth / Security — Watcher

_W-1 → W-9 (JWT validation) and W-12/13 (`AUTH_SERVICE_LOGIN_URL` redirect) were removed with the JWT in SSF-12._

### 1.1 DEV_MODE bypass

| # | Test | How | Expected |
|---|------|-----|----------|
| W-10 | DEV_MODE=true bypasses auth | No headers, `DEV_MODE=true` | 200 — user is `dev-user-local`, role `admin` |
| W-11 | DEV_MODE=false requires the gate | No proof, `DEV_MODE=false` | 401 |

### 1.2 Portal gate — AUTH-09 (SSF-11/12, `tests/test_watcher_proxy_gate.py`)

| # | Test | How | Expected |
|---|------|-----|----------|
| W-14 | Valid proof → portal identity | `X-Proxy-Token` = `SONGSURF_PROXY_SECRET` + `X-User-Name/Role/Id` | `sub` = exact pseudo, role lowercased, `uid` = portal UUID |
| W-15 | Missing / wrong proof | Same headers, proof absent, empty, wrong or non-ASCII | Identity headers ignored; wrong proof logged |
| W-16 | Secret not configured | `SONGSURF_PROXY_SECRET` empty | Headers never trusted, whatever the proof |
| W-17 | Incomplete identity | Valid proof without `X-User-Name` or `X-User-Role` (or blank name) | Rejected |
| W-18 | No proof → anonymous | Old `access_token` cookie; forged headers without proof on `/watcher/*` | Ignored; 401 |
| W-19 | Forwarded headers | Proxied request with forged `X-User-Email` / `X-Watcher-Token` | SongSurf gets the Watcher's own values + `X-User-Portal-Id`, never `X-Proxy-Token` / `X-User-Name` |
| W-20 | **Manual (NAS, after step 3)** — through the gate | Open `https://songsurf.rev0li.duckdns.org` logged in / logged out of the portal | Logged in: library of the right account; logged out: portal login |
| W-21 | **Manual (extension)** — portal session | Queue a song logged in, then logged out of the portal | Logged in: queued (the portal cookie is sent); logged out: clickable « Non connecté » toast that opens SongSurf |
| W-22 | Anonymous request | No proof: browser page; JSON / extension call; old `?token=` link | 401 « Passe par le portail » page (link to `REVAUTH_HOME_URL`); 401 `{ok: false, error: 'unauthenticated'}`; no cookie set |
| W-23 | Service locked | `SONGSURF_PROXY_SECRET` empty, valid-looking headers | 401 |
| W-24 | Logout | GET `/logout` | 302 → `REVAUTH_HOME_URL`, no `Set-Cookie` |

---

## 2. Auth — Watcher → SongSurf header injection

| # | Test | How | Expected |
|---|------|-----|----------|
| S-1 | `X-Watcher-Token` required | Send request directly to SongSurf `:8081` without header | 401 or 503 |
| S-2 | Wrong `X-Watcher-Token` | Send request to SongSurf with wrong token value | 401 |
| S-3 | Headers injected correctly | Authenticate via Watcher, check SongSurf receives `X-User-Id`, `X-User-Role`, `X-User-Email` | Headers match the gate identity |
| S-4 | Role lowercase | Gate sends `X-User-Role: Admin` (capitalized) | SongSurf receives `x-user-role: admin` |

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
| ST-2 | Member files deleted after ZIP | `test_ssf10_member_zip_still_purges_member_library`: prepare then download as Member | `/data/music/<uid>/` removed once the stream completes |
| ST-3 | Per-user isolation | `test_st3_user_isolation`: two users (different portal UUID) | Each sees only their own `/data/music/<uid>/` library |
| ST-5 | Storage key = portal UUID (SSF-03) | `test_ssf03_missing_or_invalid_portal_id_rejected`, `test_user_music_dir_rejects_invalid_uid` | No / invalid `X-User-Portal-Id` → 401, never a fallback on the pseudo |
| ST-6 | `.owner` file | `test_ssf03_owner_file_holds_pseudo` | `/data/music/<uid>/.owner` = exact pseudo, not listed in the library |
| ST-7 | Pseudo → UUID migration | `tests/test_migrate_to_uid.py` | Dry-run by default; `--apply` renames folders + cookies, writes `.owner`, removes the empty old admin mount point; conflicts reported, nothing moved |
| ST-4 | Path traversal blocked | Library endpoints with `../` in paths | 400 — chemin invalide |

---

## 5. ZIP flow

| # | Test | How | Expected |
|---|------|-----|----------|
| Z-1 | ZIP built in background (SSF-03) | POST `/api/prepare-zip` then poll `/api/zip-status` (`test_ssf03_zip_build_survives_as_ready`) | 202 `building` → `ready` with `count`, `size_mb`, `download_url`; never the server path |
| Z-2 | ZIP download | GET `/api/download-zip` once ready | File downloaded, `Content-Disposition: attachment`, state back to `idle` |
| Z-3 | ZIP not ready | GET `/api/download-zip` without prepare | 404 |
| Z-7 | ZIP state survives a restart | `test_zip_state_survives_restart` | `ready` kept; `building` → `error` « Export interrompu… » |
| Z-8 | Ready ZIP whose file vanished | `test_ssf03_zip_status_idle_when_ready_file_vanished` | `/api/zip-status` → `idle`, state cleared |
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
| A-1 | `/api/admin/extract-covers` requires admin | Call as Member | 403 — Admin requis |
| A-2 | Admin can call it | Call as Admin | 200 — covers extracted |

---

## 9. SSF-01 hardening (CORS, per-user cookies, request size, status isolation)

| # | Test | How | Expected |
|---|------|-----|----------|
| H-1 | CORS only for SongSurf Clip | `OPTIONS` with `Origin: null` / other `chrome-extension://…` / `https://evil.com` (`test_cors_*`) | 403, no `Access-Control-Allow-Origin` |
| H-2 | Extension ID pinned | `test_cors_extension_id_matches_manifest` | ID derived from manifest `key` = `SONGSURF_EXTENSION_ID` |
| H-3 | No cookies → blocked | `/api/extract`, `/api/preview`, `/api/download`, `/api/download-playlist`, `/api/queue-direct` without `<uid>.txt` | 403 `cookies_missing` + message pointing to the extension; no fallback on admin cookies |
| H-4 | Cookies stored per user | `/api/cookies/update` | `/data/cookies/<uid>.txt`, chmod 600, response carries `pseudo`; bad format → 400 |
| H-5 | Worker uses owner cookies | `test_ssf01_worker_*` | `cookiefile` = owner's file; file removed after queueing → clean error |
| H-6 | Request size cap | Body > 20 MB | 413 JSON "max 20 Mo" (not 500) |
| H-7 | `/api/status` isolation | Two members | Other member's `last_completed` / `last_error` / `current_download` never returned |
| H-10 | Clean stop (SSF-02) | `docker stop songsurf` on the NAS (`time`, then `docker inspect -f '{{.State.ExitCode}}'`) | < 2 s, exit 0; `test_ssf02_*` cover temp cleanup |
| H-11 | Healthcheck (SSF-02) | `docker inspect -f '{{.State.Health.Status}}' songsurf` on the NAS | `healthy` |
| H-9 | **Manual, real extension on the NAS** | Reload the unpacked extension (new fixed ID → re-enter the SongSurf URL in options), Sync cookies, queue a song | Popup shows "Cookies synchronisés pour <pseudo>"; download OK; a member without sync sees the blocking message |

---

## 10. SSF-03 — persistent queue, fairness, quotas

| # | Test | How | Expected |
|---|------|-----|----------|
| Q-1 | Round-robin between users | `test_ssf03_worker_alternates_between_members`, `test_queue_round_robin_between_users`, `test_rr_*` | alice album (3) + bob (1) → `a1, b1, a2, a3`; each user's order kept |
| Q-2 | Late user not stuck behind a big album | `test_late_user_is_served_before_the_rest_of_a_big_album` | bob's song passes right after the current song |
| Q-3 | Queue survives a restart | `test_queue_survives_restart_and_resumes_interrupted_song` | Song cut mid-download back to pending, round-robin pointer kept |
| Q-4 | Queue limit per user | `test_d9_rejects_when_queue_full` | 429 at `MAX_PENDING_JOBS` jobs for that user; another member can still queue |
| Q-5 | Daily quota per member, admin unlimited | `test_ssf03_daily_quota_per_member_admin_unlimited`, `test_daily_count_is_per_user_and_per_day` | 429 `daily_limit` (also `/api/queue-direct`); other member and admin OK; counter survives a restart |
| Q-6 | Who uses the worker | `test_ssf03_status_tells_who_uses_the_worker` | Member: no pseudo, `songs_before_mine`; admin: `owner` + `current` |
| Q-7 | Watcher busy probe | `test_ssf03_watcher_probe_gets_busy_state_without_identity` | Token only → 200 `{in_progress, queue_size}` (before SSF-03: 503, SongSurf could be stopped mid-batch) |
| Q-8 | **Manual (NAS)** — restart mid-batch | Queue an album, `docker restart songsurf` during a song | Logs « File reprise après redémarrage », the album finishes |
| Q-9 | **Manual (NAS)** — two members in parallel | Two accounts each queue an album | Songs alternate; each member sees « ton tour dans N morceaux » while the other's song runs |

---

## Integration checklist (pre-deploy to prod)

- [ ] W-20 / W-21 pass through the real portal gate
- [ ] `DEV_MODE=false` in `.env`
- [ ] `SONGSURF_PROXY_SECRET` same value in `.secrets` and in the secret Caddy reads on the VPS
- [ ] `REVAUTH_HOME_URL` points to the portal member space
- [ ] `ADMIN_UID` (NAS `.env`) = the admin's portal UUID — `docker compose config` refuses to start without it
- [ ] Pseudo → UUID migration run once (`docs/DEPLOY.md`), 0 conflict
- [ ] NAS firewall blocks port 8081 from WAN
- [ ] SongSurf port NOT published in `docker-compose.local.yml` (already done)
