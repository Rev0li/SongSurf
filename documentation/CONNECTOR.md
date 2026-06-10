# CONNECTOR — SongSurf ↔ rev0auth

Integration contract between the two projects. **Status: implemented** (Phase 3 done). Keep this file in sync if either side changes its auth interface.

- SongSurf repo: `~/dev/rev0Univers/SongSurf/`
- Auth repo: `~/dev/rev0Univers/auth/`

---

## How the integration works

```
Browser
  │  cookie: access_token=<JWT>
  ▼
Watcher (WATCHER_PORT)
  │  validates JWT locally (HS256, AUTH_JWT_SECRET — shared secret)
  │  extracts claims → injects headers
  ▼
SongSurf :8081
  │  verifies X-Watcher-Token, trusts X-User-* headers (no re-validation)
  ▼
  /data/music/<pseudo>/   ← admin: permanent · member: deleted after ZIP export
```

`pseudo` is derived from the email local part (sanitized); the admin role always maps to `ADMIN_PSEUDO` (default `rev0admin`).

---

## JWT contract (issued by rev0auth)

Issued at login as an **HttpOnly cookie** named `access_token`.

### Claims (all required by Watcher)

| Claim | Type | Example | Notes |
|---|---|---|---|
| `sub` | string | `"550e8400-…"` | Stable user identifier |
| `email` | string | `"alice@example.com"` | Used to derive the library folder name |
| `role` | string | `"Admin"` / `"Member"` | Lowercased by Watcher; controls storage persistence |
| `token_type` | string | `"access"` | Refresh tokens are rejected |
| `exp` | int | unix ts | Expiry (access ≈ 15 min) |

### Signing

- Algorithm: **HS256**
- Secret: `AUTH_JWT_SECRET` — **must be byte-identical** in `auth/.secrets` (VPS) and `SongSurf/SongSurf/.secrets` (NAS). Rotation requires restarting both stacks (see root `rev0Univers/CLAUDE.md`).

### Cookie

```
Set-Cookie: access_token=<JWT>; HttpOnly; Secure; SameSite=Lax; Path=/
```

In production the cookie must be shared across subdomains (`COOKIE_DOMAIN=.<root-domain>`) so the browser sends it to the SongSurf host — see `REV0AUTH_INTEGRATION.md`.

---

## Headers injected by Watcher into every SongSurf request

```
X-Watcher-Token:  <WATCHER_SECRET>    internal shared secret (constant-time checked)
X-User-Id:        <sub claim>
X-User-Role:      <role claim, lowercased>
X-User-Email:     <email claim>
```

SongSurf rejects any request without a valid `X-Watcher-Token` (401), which is why port 8081 must never be reachable from outside the host.

---

## Storage model

| Role | Folder | Cleanup |
|---|---|---|
| `admin` | `/data/music/<ADMIN_PSEUDO>/` | Never deleted |
| `member` | `/data/music/<pseudo>/` | Deleted after the user downloads their ZIP (`/api/download-zip`) |

Both roles use the same dashboard; only the post-ZIP cleanup differs.

---

## Failure modes

| Situation | Watcher behavior |
|---|---|
| No cookie / invalid / expired JWT | 302 → `AUTH_SERVICE_LOGIN_URL` (browser) or 503 (API callers) |
| `AUTH_SERVICE_LOGIN_URL` unset | 503 unavailable page |
| `AUTH_JWT_SECRET` empty | every request 503 + warning in logs (no crash) |
| `token_type != "access"` | rejected |
| `DEV_MODE=true` | full bypass with local admin dev user — never in production |
