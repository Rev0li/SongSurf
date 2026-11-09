# CONNECTOR — SongSurf ↔ rev0auth

Integration contract between the two projects. **Status: implemented** — portal gate (AUTH-09: SSF-11 then SSF-12, the JWT is gone). Keep this file in sync if either side changes its auth interface.

- SongSurf repo: `~/dev/rev0Univers/SongSurf/`
- Auth repo: `~/dev/rev0Univers/auth/`

---

## How the integration works

```
Browser ──portal session cookie──► Caddy (VPS) ── forward_auth ──► portal
                                     │ no session → 302 to portal login (navigation) / 401 (API)
                                     │ no SongSurf access → 403
                                     ▼ access granted
                                  SongSurf :SONGSURF_PORT (X-User-Name, X-User-Role, X-User-Id, X-Proxy-Token)
                                     │ checks X-Proxy-Token, then trusts X-User-* (no re-validation)
                                     ▼
                                  /data/music/<uid>/      ← admin: permanent · member: deleted after ZIP export
```

Requests that don't reach SongSurf through Caddy never get an identity: no login redirect in SongSurf (Caddy does it), just a 401 JSON (API / extension) or a « passe par le portail » page.

---

## Headers sent by Caddy to SongSurf

| Header | Content |
|---|---|
| `X-User-Name` | exact pseudo (original case), unique, immutable → becomes `sub` |
| `X-User-Role` | `guest` · `member` · `mod` · `admin` (lowercased by SongSurf) |
| `X-User-Id` | portal UUID, stable → `uid`, the **storage key** (required) |
| `X-Proxy-Token` | proof that the request comes from Caddy |

Caddy strips client-sent `X-User-*` and the portal session cookie, and adds `X-Proxy-Token` itself. Exempted from the gate, and sent **without** proof nor identity (SongSurf sees an anonymous request): CORS preflights (`OPTIONS`), and `GET`/`HEAD` on the home-screen files `/manifest.json`, `/favicon.svg`, `/apple-touch-icon.png`, `/icon-192.png`, `/icon-512.png`, `/icon-maskable-512.png` — the phone fetches them without the session (AUTH-31). Renaming or adding an icon means updating that list in the Caddyfile.

### Proof

- Secret: `SONGSURF_PROXY_SECRET` (`openssl rand -hex 32`) — **must be byte-identical** in `SongSurf/SongSurf/.secrets` (NAS) and the secret file Caddy reads on the VPS. Rotation = update both, restart both.
- SongSurf compares it with `hmac.compare_digest` (`user_from_portal_headers()` in `server/auth/portal.py`). Missing or wrong → the `X-User-*` are ignored (SongSurf listens on the home network — any LAN device could otherwise claim to be admin); a wrong proof is logged.
- Empty secret → service locked (every request 401), warning at boot.

`sub` is the exact pseudo, used only for display, logs and activity events. Everything stored per user (library, cookies, queue, quota, ZIP) is keyed by the **portal UUID** (SSF-03), admin included — unique and stable by construction, never derived from the pseudo. A request without a valid UUID is refused by SongSurf.

---

## Former Watcher hop (removed in SSF-16, 2026-11)

Until SSF-16 a separate **Watcher** container checked the proof, then re-sent the identity to SongSurf as `X-Watcher-Token` / `X-User-Id` (pseudo) / `X-User-Portal-Id` (UUID), and started/stopped SongSurf on demand. SongSurf now checks the proof itself and runs continuously; those internal headers open nothing anymore. Caddy did not change: SongSurf listens on the port the Watcher used.

---

## Logout

`/logout` redirects to `REVAUTH_HOME_URL` (the portal's member space). The session belongs to the portal: SongSurf has no cookie to clear. Downloads keep running.

---

## Browser extension

SongSurf Clip has a host permission on the SongSurf domain so Chrome sends the portal cookie (`SameSite=Lax`). A 401, a redirect to another origin (portal login) or a network error means "not connected": clickable toast / popup state that opens SongSurf in a tab.

---

## Storage model

| Role | Folder | Cleanup |
|---|---|---|
| `admin` | `/data/music/<ADMIN_UID>/` — on the NAS, the Jellyfin music folder mounted there | Never deleted, no ZIP export (SSF-10) |
| `member` | `/data/music/<uid>/` | Deleted after the user downloads their ZIP (`/api/download-zip`) |

Each folder holds a `.owner` file with the pseudo, so the NAS stays readable. Cookies: `/data/cookies/<uid>.txt`.

---

## Failure modes

| Situation | SongSurf behavior |
|---|---|
| No / wrong `X-Proxy-Token` | identity ignored → 401 JSON (API, extension) or 401 « passe par le portail » page |
| `SONGSURF_PROXY_SECRET` empty | every request 401 + warning in logs (no crash) |
| Proof valid but `X-User-Name` or `X-User-Role` missing | rejected (401) |
| `DEV_MODE=true` | full bypass with local admin dev user — never in production |

---

## History

- Phase 3 (until 2026-10): rev0auth signed an HS256 JWT (`AUTH_JWT_SECRET`) handed over as `?token=`, kept by the Watcher (removed in SSF-16) in an `access_token` cookie.
- AUTH-09 switch (2026-10-20): SSF-11 accepted both, SSF-12 removed the JWT (`?token=`, cookie, `AUTH_JWT_SECRET`, `AUTH_SERVICE_LOGIN_URL`, `make token`, `login_success` / `login_rejected` events).
- SSF-16 (2026-11): Watcher removed, SongSurf checks `X-Proxy-Token` itself and runs continuously (`WATCHER_SECRET`, `container_start` / `container_stop` events gone).
