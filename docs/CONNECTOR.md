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

## Portal gate (AUTH-09 — transition in progress)

Contract written by the rev0auth side (ticket AUTH-09). SongSurf side: **SSF-11** (Watcher accepts both the gate and the JWT) then **SSF-12** (JWT removed).

```
Browser ──portal session cookie──► Caddy (VPS) ── forward_auth ──► portal
                                     │ no session → 302 to portal login (navigation) / 401 (API)
                                     │ no SongSurf access → 403
                                     ▼ access granted
                                  Watcher  (X-User-Name, X-User-Role, X-User-Id, X-Proxy-Token)
```

| Header | Content |
|---|---|
| `X-User-Name` | exact pseudo (original case), unique, immutable → becomes `sub` |
| `X-User-Role` | `guest` · `member` · `mod` · `admin` (lowercased by the Watcher) |
| `X-User-Id` | portal UUID, stable → forwarded to SongSurf as `X-User-Portal-Id` (not used yet) |
| `X-Proxy-Token` | proof that the request comes from Caddy |

Caddy strips client-sent `X-User-*` and the portal session cookie, and adds `X-Proxy-Token` itself. The Watcher checks it with `hmac.compare_digest` against `SONGSURF_PROXY_SECRET`: missing or wrong → the `X-User-*` are ignored (the Watcher listens on the home network — any LAN device could otherwise claim to be admin). An empty secret disables the gate. `CORS` preflights (`OPTIONS`) are exempted by Caddy.

Switch order (no downtime): 1) generate `SONGSURF_PROXY_SECRET` (`openssl rand -hex 32`), set it on the NAS (`.secrets`) and on the VPS · 2) **SSF-11** deployed (both accepted) · 3) gate applied on the VPS · 4) portal: plain links, no JWT · 5) **SSF-12**: JWT removed from SongSurf · 6) portal/VPS: `AUTH_JWT_SECRET` removed.

The SongSurf Clip extension sends the portal cookie (host permission on the SongSurf domain) and treats a 401, a redirect to another origin (portal login) or a network error as "not connected": clickable toast / popup state that opens SongSurf in a tab.

---

## JWT contract (issued by rev0auth — removed in SSF-12)

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

In production the cookie must be shared across subdomains (`COOKIE_DOMAIN=.<root-domain>`) so the browser sends it to the SongSurf host — see `DEPLOY.md` §7.

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
