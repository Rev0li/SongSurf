# Local integration test — rev0auth + SongSurf

## Port map

| Service        | Port  | Env var override        |
|----------------|-------|-------------------------|
| rev0auth API   | 9000  | `API_BIND_ADDR`         |
| rev0auth web   | 3000  | `WEB_BIND_ADDR`         |
| Watcher        | 8080  | (fixed)                 |
| SongSurf       | 8081  | (fixed)                 |
| SvelteKit dev  | 5173  | (Vite)                  |

rev0auth API is moved to 9000 to avoid conflict with Watcher on 8080.

---

## 1 — Shared secret

Pick any random string and use it in both projects:

```bash
export AUTH_JWT_SECRET="change_me_to_something_random_and_long"
```

---

## 2 — Start rev0auth

```bash
cd ~/dev/rev0auth

# API on port 9000 (avoids conflict with Watcher on 8080)
API_BIND_ADDR=0.0.0.0:9000 AUTH_JWT_SECRET=$AUTH_JWT_SECRET \
  ~/.cargo/bin/cargo run -p rev0auth-api

# Web portal on port 3000 (separate terminal)
WEB_BIND_ADDR=0.0.0.0:3000 API_URL=http://localhost:9000 \
  ~/.cargo/bin/cargo run -p rev0auth-web
```

Login page will be at: `http://localhost:3000/portal`

---

## 3 — Start SongSurf (no Docker)

```bash
cd ~/dev/bot_music/SongSurf/server

DEV_MODE=false \
AUTH_JWT_SECRET=$AUTH_JWT_SECRET \
AUTH_SERVICE_LOGIN_URL=http://localhost:3000/portal \
WATCHER_SECRET=local_dev_secret \
FLASK_SECRET_KEY=local_flask_key \
python app.py
```

---

## 4 — Start Watcher (no Docker)

```bash
cd ~/dev/bot_music/SongSurf/watcher

DEV_MODE=false \
AUTH_JWT_SECRET=$AUTH_JWT_SECRET \
AUTH_SERVICE_LOGIN_URL=http://localhost:3000/portal \
WATCHER_SECRET=local_dev_secret \
FLASK_SECRET_KEY=local_watcher_key \
TARGET_URL=http://localhost:8081 \
python watcher.py
```

---

## 5 — Start SvelteKit dev server (optional, for hot-reload)

```bash
cd ~/dev/bot_music/SongSurf/frontend
npm run dev
# → http://localhost:5173 (proxies /api → :8081)
```

Or skip this and hit Watcher directly at `http://localhost:8080`.

---

## 6 — Test flow

1. Open `http://localhost:8080` — should redirect to `http://localhost:3000/portal`
2. Sign up / log in via rev0auth
3. On success, rev0auth sets `access_token` cookie (HttpOnly, Path=/)
4. Navigate back to `http://localhost:8080` — Watcher validates JWT, proxies to SongSurf
5. SvelteKit dashboard loads, `/api/me` returns `{ sub, role, email }`

### Quick curl check (after login in browser)

```bash
# Grab cookie from browser DevTools → Application → Cookies → access_token
TOKEN="<paste token here>"

curl -s -H "Cookie: access_token=$TOKEN" http://localhost:8080/api/me | jq
# Expected: {"sub": "...", "role": "member", "email": "..."}

curl -s -H "Cookie: access_token=$TOKEN" http://localhost:8080/api/status | jq
```

---

## Checklist

- [ ] `AUTH_JWT_SECRET` same value in both `.env` files
- [ ] rev0auth API runs on 9000, web on 3000
- [ ] Watcher on 8080 redirects unauthenticated to `http://localhost:3000/portal`
- [ ] After login, SongSurf dashboard accessible at `http://localhost:8080`
- [ ] `/api/me` returns correct role (`member` or `admin`)
- [ ] `/api/download` works end-to-end (queue, progress, file written)
