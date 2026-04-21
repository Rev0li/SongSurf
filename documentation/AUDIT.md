# Audit — SongSurf v1.0

> Analysis date: April 2026 | Scope: full codebase before stable public release

---

## What Is Working Well

| Component | Status | Notes |
|---|---|---|
| Watcher auth proxy | Solid | Brute-force (5 attempts → 15 min lockout), shared-secret injection |
| YouTubeDownloader | Solid | yt-dlp progress hooks, FFmpeg auto-detect, duration guard (9000s) |
| MusicOrganizer | Solid | ID3 tags, featuring detection, JPEG album art, filesystem organization |
| Admin download queue | OK | `threading.Queue`, one download at a time, cancel flag |
| Guest session lifecycle | OK | TTL, quota, deferred ZIP cleanup, 120s post-ZIP grace |
| URL validation | OK | Regex + YouTube/YouTube Music domain allowlist |
| Docker non-root | OK | `uid 1000`, healthcheck on `/ping`, `restart: on-failure` |
| CSS design system | Solid | Token-based, zero duplication, mobile-first |

---

## Bugs & Technical Debt

### BUG-01 — Song vs. Playlist Detection (Critical)

**Files:** `app.py` — `/api/extract` and `/api/guest/extract`

The current heuristic:
```python
is_playlist = ('/playlist?list=' in url or '/browse/' in url) and '/watch?' not in url
```

YouTube Music frequently appends `&list=` after `?v=` on single tracks served within a playlist context. This causes a single song to be misidentified as a playlist, triggering a multi-track download.

**Correct rule:**
- URL contains `/watch?v=` → always a single song (parameter `v` present)
- URL contains `/playlist?list=` without `/watch?` → playlist/album
- URL contains `/browse/` → album

**Recommended fix** (implement in `downloader.py`, use from `app.py`):
```python
def _detect_type(self, url: str) -> str:
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if 'v' in qs:
        return 'song'
    if 'list' in qs or '/browse/' in parsed.path:
        return 'playlist'
    return 'song'
```
Apply identically to both admin and guest extract routes.

---

### DEBT-01 — Dead `cleanup()` JS Function

**File:** `SongSurf/static/js/pages/dashboard-admin.js`

The `/api/cleanup` route is protected by `@login_required` (no security risk), but the frontend `cleanup()` function is orphaned — the button was removed from the HTML but the JS remains. It should be deleted to reduce confusion.

**Action:** Remove `cleanup()` function and all calls from the JS. Keep the `/api/cleanup` route as an internal maintenance endpoint (not exposed in the UI).

---

### DEBT-02 — Misleading `SONGSURF_PASSWORD` Warning Log

**File:** `SongSurf/server/app.py` (~line 77)

In Watcher mode, `SONGSURF_PASSWORD` is intentionally left empty. The current warning fires unconditionally and pollutes logs in production.

**Current:**
```python
if not DASHBOARD_PASSWORD:
    print("⚠️  Aucune auth admin configurée ! Dashboard non protégé.")
```

**Fixed (already applied in current code — verify still in place):**
```python
if not WATCHER_SECRET and not DASHBOARD_PASSWORD:
    print("⚠️  Aucune auth configurée ! Dashboard non protégé en mode standalone.")
```

---

### DEBT-03 — `get_stats()` Unused in Organizer

**File:** `SongSurf/server/organizer.py`

`get_stats()` is a legacy method that scans the music library to produce summary counts (songs, albums, artists). It is not called from any active route. It creates a divergence between what is shown and what exists, and adds maintenance surface.

**Action:** Remove `get_stats()`. When a proper library module is introduced, reimplement it there.

---

### DEBT-04 — Guest Library Not Reflecting `music_guest` Correctly

**File:** `SongSurf/server/app.py` — guest library route

Guest session library data does not accurately reflect the contents of `/data/music_guest/<session_id>/`. The folder browsing logic pulls stale or incorrect paths.

**Action:** Fix the guest library endpoint to scope the file tree to the authenticated guest's session directory only.

---

### DEBT-05 — Album Art Not Extracted for Guest Downloads

**File:** `SongSurf/server/organizer.py` / `downloader.py`

Admin downloads correctly extract and store the JPEG album art thumbnail alongside the MP3. Guest downloads do not replicate this — no cover is saved to the guest session folder.

**Action:** Apply the same post-download cover extraction logic for guest sessions.

---

### DEBT-06 — Navigation Loop in Loading Screen (Known, In-Progress)

**Files:** `watcher/watcher.py`, `SongSurf/templates/pages/loading.html`, `dashboard-admin.js`

Under certain conditions (browser refresh during loading, SongSurf startup delay, cookie edge cases), the loading screen enters an infinite redirect loop. The root cause is split redirect authority between the backend (Watcher 302s) and frontend (`setInterval` polling `/watcher/ready`).

**Plan:** Define a single authority for redirect decisions (backend preferred), normalize API error codes (401/403/5xx), and remove contradictory JS redirect logic. See `migration/09_next_session_api_routes.md` for the full remediation plan.

---

### DEBT-07 — `localStorage` Used for Tutorial State

**File:** `SongSurf/templates/pages/guest_dashboard.html`

```javascript
localStorage.setItem('songsurf_tuto_done', '1');
```

Functional in standard browsers. Silently fails in private browsing or certain mobile configurations, causing the tutorial overlay to always show. Acceptable for now — note the dependency.

---

## Security Considerations

| Area | Status | Notes |
|---|---|---|
| Brute-force protection | OK | 5 attempts → 15 min IP lockout in Watcher |
| URL injection | OK | YouTube/YouTube Music domain allowlist + regex validation before passing to yt-dlp |
| yt-dlp errors to guest | OK | Error messages from yt-dlp are not forwarded to guest responses |
| Non-root container | OK | Both images run as `uid 1000` |
| Secret rotation | Low risk | `WATCHER_SECRET` is env-injected; not in code or logs |
| No file size limit enforcement at extract | Addressed | `MAX_DURATION_SECONDS` guard in downloader (default 9000s = 2h30) |
| `/api/cleanup` not in UI | OK | Route is `@login_required`; dead JS cleaned up per DEBT-01 |
| Session cookies | OK | `FLASK_SECRET_KEY` is environment-injected; `permanent_session_lifetime = 7 days` |

**Outstanding security items:**

- **Rate limiting on `/api/extract`** — no throttle on the yt-dlp metadata call. An authenticated user can hammer it. Add per-session rate limiting for guest users at minimum.
- **ZIP bomb risk** — a guest session with `GUEST_MAX_SONGS=0` (unlimited) and no `MAX_DURATION_SECONDS` override could accumulate significant disk usage before the ZIP is prepared. Consider enforcing a per-session disk quota.

---

## Bottlenecks

| Area | Risk | Notes |
|---|---|---|
| Single download queue | Low | Intentional; one download at a time prevents disk/CPU contention. Acceptable for personal/small-team use. |
| Guest cleanup thread (30s sleep) | Low | Files may persist up to 30s past TTL. Not a user-facing issue. |
| yt-dlp info extraction blocking | Medium | `POST /api/extract` is synchronous and can take 2–5s for large playlists. No timeout enforced. Consider async or a timeout wrapper. |
| Album scan on library load | Medium | `GET /api/library` walks the full `/data/music` tree on every request. With a large library, this can be slow. No caching layer exists. |
| Prefetch thread (no cancellation on new URL) | Low | If a user pastes a new URL while prefetch is running, the old prefetch continues until completion. Low impact; cancellation endpoint exists but JS doesn't call it proactively. |

---

## Remediation Priority

| Priority | Item | Effort |
|---|---|---|
| P0 — Blocker | BUG-01 Song vs. playlist detection | Small — ~20 lines |
| P1 — Should fix | DEBT-04 Guest library path | Small |
| P1 — Should fix | DEBT-05 Album art for guests | Small |
| P1 — Should fix | DEBT-06 Loading screen loop | Medium |
| P2 — Cleanup | DEBT-01 Dead cleanup() JS | Trivial |
| P2 — Cleanup | DEBT-02 Log warning condition | Trivial |
| P2 — Cleanup | DEBT-03 Remove get_stats() | Trivial |
| P3 — Hardening | Rate limiting on /api/extract (guest) | Small |
| P3 — Hardening | Per-session disk quota for guests | Medium |
| P3 — Hardening | Async or timeout on /api/extract | Medium |
