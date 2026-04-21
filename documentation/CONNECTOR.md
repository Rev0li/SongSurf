# CONNECTOR — SongSurf ↔ auth-selfhost-rust

This file documents the integration contract between the two projects.  
It is the single source of truth for both sides; keep it in sync when either project changes its auth interface.

**SongSurf repo:** `~/dev/bot_music/`  
**Auth repo:** `~/dev/rev0auth/` (branch `feature/saas-dashboard-clean-1`)

---

## How the Integration Works

```
Browser
  │
  │  cookie: access_token=<JWT>
  ▼
Watcher :8080
  │  reads cookie → validates JWT (HMAC HS256, shared secret)
  │  extracts claims → injects headers
  ▼
SongSurf :8081
  │  trusts headers (no re-validation)
  ▼
  /data/music/<user_sub>/   ← permanent (Admin role)
  /data/music/<user_sub>/   ← deleted after ZIP download (Member role)
```

---

## JWT Contract (issued by auth-selfhost-rust)

The auth service issues JWTs at `POST /auth/login` as **HttpOnly cookies** (`access_token`).

### Claims

| Claim | Type | Example | Notes |
|---|---|---|---|
| `sub` | string (UUID) | `"550e8400-e29b-41d4-..."` | Stable user identifier — used as folder name |
| `email` | string | `"alice@example.com"` | Display name fallback |
| `role` | string enum | `"Admin"` or `"Member"` | Controls storage persistence |
| `token_type` | string | `"access"` | Always `"access"` for access tokens |
| `iat` | int (Unix) | `1713400000` | Issued at |
| `exp` | int (Unix) | `1713400900` | Expiry (access = 15 min, refresh = 7 days) |

### Signing

- Algorithm: **HS256**
- Secret: shared via `JWT_SECRET` environment variable (same value in both services)

### Cookie Format

```
Set-Cookie: access_token=<JWT>; HttpOnly; Secure; SameSite=Lax; Path=/
```

A separate CSRF token cookie is set without `HttpOnly` for double-submit validation (not required by SongSurf since it's not a browser-managed CSRF target — SongSurf receives server-to-server headers from Watcher).

---

## Watcher Integration (TODO — Phase 3)

Watcher must be updated to validate the JWT instead of a form password.

### Required env vars (Watcher)

```dotenv
# Shared with auth-selfhost-rust — must be identical
JWT_SECRET=<same value as auth service JWT_SECRET>

# Auth service base URL (for /auth/me fallback if needed)
# AUTH_SERVICE_URL=http://auth:8000
```

### Validation logic (Python, to add in watcher.py)

```python
import jwt as pyjwt  # pip install PyJWT

JWT_SECRET = os.getenv('JWT_SECRET', '')

def _validate_jwt(token: str) -> dict | None:
    """
    Validates an HS256 JWT and returns claims, or None if invalid.
    Install: pip install PyJWT
    """
    # TODO Phase 3: replace Watcher password auth with this
    try:
        claims = pyjwt.decode(
            token,
            JWT_SECRET,
            algorithms=['HS256'],
            options={'require': ['sub', 'role', 'exp']},
        )
        if claims.get('token_type') != 'access':
            return None
        return claims
    except pyjwt.PyJWTError:
        return None

def _extract_jwt_from_request() -> str | None:
    """Reads JWT from the access_token HttpOnly cookie."""
    return request.cookies.get('access_token')
```

### Replace login check in proxy catch-all (watcher.py)

```python
# Current (password-based):
role = session.get('role')
if not role:
    return redirect(ADMIN_LOGIN_PATH)

# Phase 3 replacement:
token = _extract_jwt_from_request()
claims = _validate_jwt(token) if token else None
if not claims:
    return redirect(AUTH_SERVICE_LOGIN_URL)  # redirect to auth service login page

role = claims['role'].lower()   # 'admin' or 'member'
user_sub = claims['sub']
user_email = claims.get('email', '')
```

### Headers injected by Watcher into every SongSurf request

```
X-Watcher-Token:   <WATCHER_SECRET>   ← existing, unchanged
X-User-Id:         <sub claim>         ← NEW: used as folder name
X-User-Role:       <role claim>        ← existing, now sourced from JWT
X-User-Email:      <email claim>       ← NEW: for display/logging
```

---

## SongSurf Integration (TODO — Phase 3)

SongSurf reads the injected headers — no JWT validation needed here.

### Required env var changes

```dotenv
# Remove: SONGSURF_PASSWORD, SONGSURF_GUEST_PASSWORD
# Keep:   WATCHER_SECRET  (still used to verify requests come from Watcher)
```

### New user identity decorator (to add in app.py)

```python
def get_user_identity() -> dict:
    """
    Extracts user identity from Watcher-injected headers.
    Returns dict with sub, role, email.
    # TODO Phase 3: replace login_required / guest_required decorators with this
    """
    return {
        'sub':   request.headers.get('X-User-Id', ''),
        'role':  request.headers.get('X-User-Role', 'member').lower(),
        'email': request.headers.get('X-User-Email', ''),
    }
```

### Storage routing logic (to add in app.py)

```python
def _user_music_dir(user_sub: str) -> Path:
    """
    Returns the music directory for a given user.
    # TODO Phase 3: replace MUSIC_DIR / GUEST_MUSIC_DIR split with this
    """
    return MUSIC_DIR / user_sub

def _is_permanent_user(role: str) -> bool:
    """
    Admin role = files never deleted.
    Member role = files deleted after ZIP download.
    # TODO Phase 3: replaces admin/guest distinction
    """
    return role == 'admin'
```

---

## Auth Service Endpoint Needed

The auth service currently has **no `/validate` or `/me` endpoint**. Watcher validates the JWT locally using the shared `JWT_SECRET` (Option B agreed).

If the secret ever needs to be rotated without a redeploy, add this to auth-selfhost-rust:

```rust
// TODO Phase 3 (optional): add to auth-selfhost-rust routes
// GET /auth/me  →  returns {sub, email, role} from a valid cookie
// This allows Watcher to validate without sharing JWT_SECRET
```

---

## Storage Model (Phase 3 target)

| User role | Folder | Cleanup |
|---|---|---|
| `Admin` | `/data/music/<sub>/` | Never deleted |
| `Member` | `/data/music/<sub>/` | Deleted after user downloads their ZIP |

Both roles use the same dashboard. The only difference is post-ZIP cleanup behavior.

---

## Phase 3 Checklist

- [ ] Add `PyJWT` to `watcher/requirements.txt`
- [ ] Add `JWT_SECRET` to `.env.example` and docker-compose
- [ ] Implement `_validate_jwt()` + `_extract_jwt_from_request()` in `watcher.py`
- [ ] Replace session-based auth in Watcher with JWT validation
- [ ] Inject `X-User-Id` and `X-User-Email` headers from Watcher
- [ ] Update `login_required` decorator in `app.py` to read `X-User-Id`
- [ ] Replace `MUSIC_DIR` / `GUEST_MUSIC_DIR` split with `_user_music_dir(sub)`
- [ ] Remove TTL cleanup thread (Member files kept until ZIP download)
- [ ] Add ZIP-triggered cleanup: when Member downloads ZIP, schedule folder deletion
- [ ] Remove `SONGSURF_PASSWORD`, `SONGSURF_GUEST_PASSWORD` from config
- [ ] Remove Watcher login forms (`/administrator`, `/guest/login` routes)
- [ ] Update `documentation/ARCHITECTURE.md` to reflect new auth flow
