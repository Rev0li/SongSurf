# rev0auth ↔ SongSurf — Guide d'intégration

Ce fichier explique concrètement comment les deux projets interagissent en local
et en production, et quoi configurer de chaque côté.

Contrat JWT → voir `CONNECTOR.md`.  
Architecture SongSurf → voir `ARCHITECTURE.md`.

---

## Vue d'ensemble du flux

```
Browser
  │
  │  1. Arrive sur SongSurf sans cookie
  ▼
Watcher :9000  ──── redirect ────►  rev0auth Web :3000  (portal /login)
                                          │
                                          │  2. Login (pseudo + password)
                                          │  3. Set-Cookie: access_token=<JWT HS256>
                                          │     (HttpOnly, SameSite=Lax [+ Domain en prod])
                                          │
  ◄──────────────── redirect back ────────┘  (vers /home/friend ou SongSurf direct)
  │
  │  4. Requête avec cookie access_token
  ▼
Watcher :9000
  │  validate_jwt(cookie)  →  claims { sub, role, email }
  │  inject headers X-User-Id / X-User-Role / X-User-Email
  ▼
SongSurf :8081  (fait confiance aux headers, pas de re-validation)
```

---

## Variables d'environnement partagées

| Variable | rev0auth | SongSurf Watcher | Description |
|---|---|---|---|
| `AUTH_JWT_SECRET` | Signe le JWT | Vérifie le JWT | **Doit être identique des deux côtés** |
| `COOKIE_DOMAIN` | Attr. `Domain=` du cookie | — | Vide en local, `.rev0univers.com` en prod |
| `AUTH_SERVICE_LOGIN_URL` | — | URL redirect si pas de cookie | ex: `https://auth.rev0univers.com/portal` |
| `DEV_MODE` | — | `true` = bypass JWT | **Toujours `false` en test réel et en prod** |

---

## Local — Docker Compose (les deux projets sur localhost)

### Architecture locale

```
localhost:3000  →  rev0auth web  (portal, dashboard admin, password-check)
localhost:8080  →  rev0auth API  (JWT, PostgreSQL)
localhost:5432  →  PostgreSQL    (via docker-compose rev0auth)

localhost:9000  →  SongSurf Watcher  (proxy auth + lifecycle)
localhost:8081  →  SongSurf app      (interne, non exposé directement)
```

Pas de conflit de ports : rev0auth API sur 8080, Watcher sur 9000.

### 1. Configurer rev0auth

Dans `auth-selfhost-rust/.env` :

```dotenv
POSTGRES_PASSWORD=devpassword123
AUTH_JWT_SECRET=dev-jwt-secret-min-32-bytes-local-only-change-on-prod

ADMIN_DASH_PASSWORD=admin
ADMIN_DASH_PSEUDO=admin
ADMIN_DASH_SEED=secret

WEBAUTHN_RP_ID=localhost
WEBAUTHN_RP_ORIGIN=http://localhost:3000

COOKIE_DOMAIN=      # vide en local — cookie reste sur localhost
```

Lancer :

```bash
cd auth-selfhost-rust
make launch-all        # build Docker + démarre postgres/api/web en arrière-plan
make status            # vérifier que les 3 containers sont up
docker compose logs -f # suivre les logs
```

### 2. Configurer SongSurf

Dans `SongSurf/SongSurf/.env` :

```dotenv
DEPLOY_TARGET=local
WATCHER_PORT=9000
DEV_MODE=false                                        # ← ne pas oublier
AUTH_SERVICE_LOGIN_URL=http://localhost:3000/portal   # ← redirect si pas de cookie
```

Dans `SongSurf/SongSurf/.secrets` :

```dotenv
AUTH_JWT_SECRET=dev-jwt-secret-min-32-bytes-local-only-change-on-prod
# ↑ strictement identique à auth-selfhost-rust/.env
```

Lancer :

```bash
cd SongSurf/SongSurf
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
# ou : make up  (si Makefile gère le merge des fichiers)
```

### 3. Flux de test

1. Ouvrir `http://localhost:3000/portal` → se connecter avec un compte admin
2. Dashboard admin → onglet Users → accorder `access_songsurf` à l'utilisateur test
3. Se déconnecter puis se reconnecter avec cet utilisateur
4. DevTools → Application → Cookies → vérifier `access_token` présent sur `localhost`
5. Ouvrir `http://localhost:9000` → Watcher doit valider le cookie et afficher SongSurf

### 4. Vérification rapide via curl

```bash
# Copier la valeur du cookie depuis DevTools
TOKEN="eyJ..."

# Le Watcher doit retourner la page SongSurf (200), pas une redirect (302)
curl -sI -H "Cookie: access_token=$TOKEN" http://localhost:9000/
# Attendu: HTTP/1.1 200 OK  (ou une page SongSurf)
# Si 302 → location: localhost:3000 : le JWT n'est pas validé (secret incorrect ?)

# Vérifier les claims injectés en headers (endpoint debug si disponible)
curl -s -H "Cookie: access_token=$TOKEN" http://localhost:9000/api/me | python3 -m json.tool
# Attendu: {"sub": "ton_pseudo", "role": "member", "email": ""}
```

---

## Production — VPS (auth) + NAS Synology (SongSurf) + Caddy

### Architecture prod

```
Internet
  │
  ▼
Caddy (VPS)  ─── auth.rev0univers.com  ──►  rev0auth web :3000  (container)
             └── songsurf.rev0univers.com ─► NAS via Tailscale  ──► Watcher :9000
```

Les deux sous-domaines partagent la même racine `.rev0univers.com` → le cookie
peut être partagé grâce à `COOKIE_DOMAIN=.rev0univers.com`.

### Cookie cross-domain — pourquoi c'est nécessaire

Sans `COOKIE_DOMAIN`, le cookie `access_token` est émis sur `auth.rev0univers.com`
et le navigateur ne l'envoie **jamais** à `songsurf.rev0univers.com`.

Avec `COOKIE_DOMAIN=.rev0univers.com` (point initial = tous les sous-domaines),
le cookie est envoyé aux deux. Le flag `Secure` est ajouté automatiquement
quand `WEBAUTHN_RP_ORIGIN` commence par `https://`.

### 1. Configurer rev0auth (VPS)

Dans `.env` sur le VPS (à côté de `docker-compose.yml`) :

```dotenv
POSTGRES_PASSWORD=<mot de passe fort>
AUTH_JWT_SECRET=<secret 32+ octets, identique côté SongSurf>

ADMIN_DASH_PASSWORD=<mot de passe admin fort>
ADMIN_DASH_PSEUDO=<pseudo admin>
ADMIN_DASH_SEED=<seed secret>
ADMIN_DASH_TOTP_SECRET=<base32 TOTP si 2FA activé>

WEBAUTHN_RP_ID=auth.rev0univers.com
WEBAUTHN_RP_ORIGIN=https://auth.rev0univers.com

COOKIE_DOMAIN=.rev0univers.com    # ← partage le cookie avec songsurf.rev0univers.com
```

Lancer sur le VPS :

```bash
docker compose up -d
```

### 2. Caddyfile (VPS)

```caddyfile
auth.rev0univers.com {
    reverse_proxy localhost:3000
}

songsurf.rev0univers.com {
    reverse_proxy <ip-tailscale-nas>:9000
}
```

### 3. Configurer SongSurf (NAS)

Dans `SongSurf/SongSurf/.env` sur le NAS :

```dotenv
DEPLOY_TARGET=nas
WATCHER_PORT=9000
DEV_MODE=false
AUTH_SERVICE_LOGIN_URL=https://auth.rev0univers.com/portal
```

Dans `SongSurf/SongSurf/.secrets` sur le NAS :

```dotenv
AUTH_JWT_SECRET=<identique à rev0auth .env>
WATCHER_SECRET=<secret interne watcher↔songsurf>
WATCHER_FLASK_SECRET_KEY=<clé Flask>
SONGSURF_FLASK_SECRET_KEY=<clé Flask>
```

Lancer sur le NAS :

```bash
cd SongSurf/SongSurf
docker compose -f docker-compose.yml -f docker-compose.nas.yml up -d
```

### 4. Flux prod attendu

1. Utilisateur ouvre `https://songsurf.rev0univers.com`
2. Watcher : pas de cookie → redirect vers `https://auth.rev0univers.com/portal`
3. Utilisateur se connecte sur rev0auth
4. rev0auth set-cookie : `access_token=<JWT>; Domain=.rev0univers.com; Secure; HttpOnly; SameSite=Lax`
5. Navigateur renvoie le cookie automatiquement sur `songsurf.rev0univers.com`
6. Watcher valide le JWT, injecte les headers, proxifie vers SongSurf

---

## Checklist avant de tester

### Local

- [ ] `AUTH_JWT_SECRET` identique dans `auth-selfhost-rust/.env` et `SongSurf/.secrets`
- [ ] `DEV_MODE=false` dans `SongSurf/.env`
- [ ] `AUTH_SERVICE_LOGIN_URL=http://localhost:3000/portal` dans `SongSurf/.env`
- [ ] `COOKIE_DOMAIN=` vide dans `auth-selfhost-rust/.env`
- [ ] rev0auth : `make launch-all` + `make status` → 3 containers up
- [ ] SongSurf : `docker compose ... up -d` → watcher + songsurf up
- [ ] Dans le dashboard admin rev0auth : user test a `access_songsurf = true`

### Production

- [ ] `AUTH_JWT_SECRET` identique sur VPS et NAS
- [ ] `COOKIE_DOMAIN=.rev0univers.com` dans rev0auth `.env` (VPS)
- [ ] `WEBAUTHN_RP_ORIGIN=https://auth.rev0univers.com` (active le flag Secure)
- [ ] `AUTH_SERVICE_LOGIN_URL=https://auth.rev0univers.com/portal` sur NAS
- [ ] Caddy configuré pour les deux sous-domaines
- [ ] Tailscale actif entre VPS et NAS

---

## Dépannage

| Symptôme | Cause probable | Fix |
|---|---|---|
| Watcher redirige en boucle vers auth | `AUTH_JWT_SECRET` différent des deux côtés | Vérifier que les deux valeurs sont identiques caractère par caractère |
| Watcher retourne 503 (pas de redirect) | `AUTH_SERVICE_LOGIN_URL` vide | Renseigner l'URL dans `SongSurf/.env` |
| Cookie présent mais Watcher rejette | `token_type` ≠ `"access"` ou `exp` dépassé | Se déconnecter et se reconnecter pour obtenir un token frais |
| Cookie absent après login | `access_songsurf = false` sur cet user | Dashboard admin → accorder l'accès SongSurf |
| Cookie présent en local mais pas en prod | `COOKIE_DOMAIN` pas configuré | Ajouter `COOKIE_DOMAIN=.rev0univers.com` dans rev0auth `.env` (VPS) |
| SongSurf accessible sans login en dev | `DEV_MODE=true` | Passer à `DEV_MODE=false` pour tester le flux réel |
