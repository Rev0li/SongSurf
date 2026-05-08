# SongSurf — Next Session

## 1. Audit Docker + Makefile

### Points à vérifier / nettoyer

**`compose-switch.sh`**
- Fonctionne, mais c'est une couche d'indirection supplémentaire.
- Alternative plus simple : remplacer par un alias `COMPOSE_FILE` dans le Makefile directement (natif Docker Compose, pas de script bash).
- À décider : garder le script ou simplifier.

**Makefile — targets à ajouter / revoir**
- `make clean` manquant → supprimer les images Docker locales, vider `data/temp`, purger les builds
- `make reset` = `down` + `clean` + `up` (full wipe pour repartir propre)
- `make logs-watcher` / `make logs-songsurf` — logs par container séparé (pratique)
- `make shell` — ouvrir un shell dans le container songsurf pour debug

**Problème de permissions `.svelte-kit/output`**
- Le dossier est créé par le build Docker (root) → `make build` local ensuite échoue sur `rmdir` (permission denied)
- Fix : ajouter `.svelte-kit/output/` au `.gitignore` + `make clean` doit `sudo rm -rf` ce dossier, OU construire le frontend hors Docker en local (`make frontend-build`), puis builder l'image sans la step Node (deux Dockerfile séparés : dev / prod)

---

### Mode Local vs Mode NAS — clarifier

**Objectif** : deux modes clairement séparés, sans ambiguïté.

| | Local (dev) | NAS (prod) |
|---|---|---|
| Réseau | Bridge Docker | `network_mode: host` |
| Port Watcher | `127.0.0.1:8080` | 0.0.0.0:8080 (NAS firewall bloque) |
| Port SongSurf | Non exposé (interne) | Non exposé (NAS firewall bloque :8081) |
| `DEV_MODE` | `true` (bypass auth) | `false` (JWT obligatoire) |
| `TARGET_URL` | `http://songsurf:8081` | `http://localhost:8081` |
| Data | `./data/` (local) | `/volume1/...` ou chemin NAS |

**À faire :**
- Créer un `.env.local` et un `.env.nas` templates (en plus du `.env.example` générique)
- Makefile : `make up-local` et `make up-nas` → sélection explicite sans dépendre du `.env`
- Revoir si `docker-compose.nas.yml` a besoin d'un volume path NAS hardcodé (sinon mettre en variable)

---

## 2. Connexion avec rev0auth (token JWT)

### État actuel

Le Watcher est **déjà câblé** pour accepter les JWT HS256 de rev0auth. Il suffit de configurer deux variables + résoudre le routing.

**Variables à brancher (dans `.secrets`) :**
```
AUTH_JWT_SECRET=<même valeur que JWT_SECRET dans rev0auth>
AUTH_SERVICE_LOGIN_URL=http://<adresse-auth>/auth/login
```

**Claims JWT attendus par le Watcher :**
```json
{
  "sub": "user-uuid",
  "role": "admin | member",
  "email": "user@example.com",
  "token_type": "access",
  "exp": 1234567890
}
```
→ Vérifier que rev0auth émet bien `token_type: "access"` et `role` dans ses tokens (sinon patch côté watcher.py `_validate_jwt`).

**Cookie attendu :** `access_token` (HttpOnly) — le Watcher lit `request.cookies.get('access_token')`.

---

### Problème de routing à résoudre

rev0auth tourne sur `:8080` ET le Watcher aussi → **conflit de port**.

**Option A — Ports différents (le plus simple)**
- rev0auth → `:8082` (ou `:3000`)
- Watcher SongSurf → `:8080` (inchangé)
- `AUTH_SERVICE_LOGIN_URL=http://localhost:8082/auth/login`
- Le cookie `access_token` est posé sur le domaine auth (`:8082`), SongSurf est sur (`:8080`) → **cookie non partagé entre ports différents** → ne fonctionnera pas directement en dev.

**Option B — Reverse proxy commun (propre, prod-ready)**
- Un Nginx ou Caddy en frontal sur `:80`/`:443`
- `/auth/*` → rev0auth
- `/*` → Watcher SongSurf
- Cookie posé sur le même domaine → partagé correctement
- C'est l'architecture cible pour le NAS

**Option C — rev0auth redirige vers SongSurf après login (court-terme)**
- rev0auth login réussit → pose le cookie → redirige vers `http://localhost:8080`
- Fonctionne en local si les deux services sont sur `localhost` (même domaine, ports différents mais cookie sur `localhost` sans port)
- À tester : les navigateurs modernes partagent-ils le cookie `localhost:8080` / `localhost:8082` ? Réponse : **oui**, `localhost` sans port dans le cookie = partagé entre tous les ports localhost.

**→ Recommandation pour commencer** : Option C en dev (ports différents, même localhost), Option B en prod NAS.

---

### Checklist d'intégration

- [ ] Vérifier les claims émis par rev0auth (`token_type`, `role`) — lire `crates/api/src/` côté auth
- [ ] Aligner `AUTH_JWT_SECRET` = `JWT_SECRET` de rev0auth (même valeur dans les deux `.secrets`)
- [ ] Tester avec `DEV_MODE=false` + `AUTH_JWT_SECRET` set + rev0auth qui tourne
- [ ] Vérifier que le cookie `access_token` est bien posé sur `localhost` (pas sur `127.0.0.1`) pour le partage inter-port
- [ ] Ajouter `AUTH_SERVICE_LOGIN_URL` dans `.env.example` (décommenter la ligne Phase 3)
- [ ] Tester le redirect : accès SongSurf sans cookie → redirect login → login → cookie posé → redirect SongSurf → accès OK

---

## 3. Rappel — Fixes livrés cette session

- **Queue persistante** : `urlQueue` store Svelte — survive à la navigation metadata ↔ dashboard
- **Artiste albums** : condition `'unknown artist'` ajoutée dans `extract_playlist_metadata` — le fallback première chanson se déclenche maintenant correctement
- **Mode Playlist caché** : toggle masqué dans `DownloadPanel.svelte` (`display:none`)
