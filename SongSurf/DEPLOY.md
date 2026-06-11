# Guide de déploiement — SongSurf

Déploiement sur NAS Synology via Docker Compose, accessible depuis l'extérieur via Tailscale + reverse proxy VPS.

> **Déploiement courant** : une fois la première installation faite, utilise `make deploy-nas` depuis la machine de dev (rsync + rebuild + restart en une commande) — voir [`../deploy_action.md`](../deploy_action.md) et [`../deploy_troubleshooting.md`](../deploy_troubleshooting.md) pour les pièges Synology.

---

## 0. Toggle global Local/NAS

Le projet intègre un switch via variables d'environnement :

- `DEPLOY_TARGET=local` : mode dev (bridge Docker + ports publiés en localhost)
- `DEPLOY_TARGET=nas` : mode production (`network_mode: host`)

Fichiers utilisés :

- `docker-compose.yml` (base commune)
- `docker-compose.local.yml` / `docker-compose.nas.yml` (overrides)
- `docker/compose-switch.sh` (sélectionne le bon combo selon `DEPLOY_TARGET`)

```bash
make up            # démarre selon DEPLOY_TARGET du .env
make up-local      # force le mode local
make up-nas        # force le mode NAS
make config        # vérifier la config résolue
make logs          # suivre les logs
make down          # arrêter
```

---

## Prérequis

- NAS Synology avec Docker (DSM 7+), accès SSH
- (Optionnel) Tailscale pour l'accès VPN
- (Optionnel) VPS avec reverse proxy (Caddy/Nginx) + domaine pour l'accès public
- Un service d'auth émettant un JWT HS256 (rev0auth) — ou `DEV_MODE=true` pour un usage local sans auth

---

## 1. Préparer le NAS (première fois)

```bash
mkdir -p /volume1/docker/songsurf
cd /volume1/docker/songsurf

# Dossiers de données avec les bons droits (uid container = 1000)
mkdir -p data/music data/temp logs
chmod 777 data/music data/temp logs
```

> ⚠️ Le `chmod 777` est requis si l'uid NAS diffère de 1000 (uid du container `songsurf`). `make init-dirs` le fait automatiquement.

---

## 2. Copier les fichiers

Depuis la machine de dev, la commande tout-en-un :

```bash
make deploy-nas NAS_USER=<user> NAS_HOST=<ip> NAS_DIR=/volume1/docker/songsurf
```

Elle rsync le projet (en excluant `data/`, `logs/`, `.env`, `.secrets`) puis rebuild et relance les containers. `.env` et `.secrets` restent sur le NAS entre les déploiements — les copier une seule fois :

```bash
scp .env .secrets <user>@<nas>:/volume1/docker/songsurf/
```

---

## 3. Générer les secrets

Ne jamais mettre de secrets dans `docker-compose.yml`. Utiliser le générateur interactif :

```bash
make secrets
```

| Fichier | Contenu | Permissions |
|---------|---------|-------------|
| `.env` | Config non-secrète (ports, timeouts, mode, `AUTH_EVENTS_URL`) | 644 |
| `.secrets` | `AUTH_JWT_SECRET`, `WATCHER_SECRET`, `SONGSURF_EVENTS_SECRET`, clés Flask | 600 |

Les deux sont chargés par Docker Compose via `env_file`. Ne jamais committer `.secrets`.

**Pour la prod avec rev0auth :** copier la valeur `AUTH_JWT_SECRET` de rev0auth dans `.secrets` (identique octet par octet), renseigner `AUTH_SERVICE_LOGIN_URL` dans `.env` et vérifier `DEV_MODE=false`. Détails : [`../documentation/REV0AUTH_INTEGRATION.md`](../documentation/REV0AUTH_INTEGRATION.md).

**Événements d'activité (optionnel) :** le NAS pousse connexions/téléchargements vers le dashboard admin rev0auth (`/japprends/songsurf-activity`). Sur un NAS existant, ne pas relancer le wizard (il écraserait `.env`/`.secrets`) — ajouter à la main :

```bash
# .env
AUTH_EVENTS_URL=https://rev0li.duckdns.org/japprends/api/songsurf-events
# .secrets — identique à SONGSURF_EVENTS_SECRET dans auth/.secrets (VPS)
SONGSURF_EVENTS_SECRET=<64 hex>
```

⚠️ **Déployer l'auth (VPS) en premier** : l'endpoint d'ingestion doit exister avant d'activer `AUTH_EVENTS_URL` côté NAS. Si l'auth est injoignable, les événements sont spoolés dans `logs/events-pending-*.jsonl` et rejoués toutes les 5 min (URL vide = tracking désactivé, aucun envoi).

---

## 4. Build & démarrage

```bash
cd /volume1/docker/songsurf
./docker/compose-switch.sh up -d --build
./docker/compose-switch.sh logs -f
```

Le portail Watcher est disponible sur `http://<IP-NAS>:<WATCHER_PORT>`.

---

## 5. Mise à jour

Tout changement de code (backend Python **ou** frontend SvelteKit — le frontend est buildé dans l'image Docker multi-stage) :

```bash
make deploy-nas        # depuis la machine de dev
# ou sur le NAS :
./docker/compose-switch.sh up -d --build
```

---

## 6. Accès Tailscale / VPN

En mode `nas`, les services utilisent `network_mode: host`. Avec Tailscale installé sur le NAS, le portail est accessible via l'IP Tailscale : `http://<tailscale-ip>:<WATCHER_PORT>`.

---

## 7. Reverse proxy public (VPS)

```
Internet → DNS → VPS (Caddy/Nginx + TLS) → Tailscale → NAS (Watcher)
```

Exemple Caddy :

```caddyfile
songsurf.mondomaine.tld {
    reverse_proxy <ip-tailscale-nas>:<WATCHER_PORT>
}
```

Exemple Nginx :

```nginx
location / {
    proxy_pass         http://<ip-tailscale-nas>:<WATCHER_PORT>;
    proxy_set_header   Host $host;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 300s;   # téléchargements longs
}
```

> Le cookie `access_token` doit être partagé entre le sous-domaine auth et le sous-domaine SongSurf (`COOKIE_DOMAIN=.mondomaine.tld` côté rev0auth).

---

## 8. Logs

```bash
./docker/compose-switch.sh logs -f          # logs techniques temps réel
cat logs/activity.log                        # journal d'activité lisible
cat logs/downloads.log                       # journal des téléchargements (pseudo | artiste | album | titre)
```

---

## 9. Dépannage

| Problème | Solution |
|---|---|
| Port non accessible | Vérifier `WATCHER_PORT` dans `.env` + firewall NAS + `make ps` |
| `Permission denied: /app/logs/…` | `chmod 777 data/music data/temp logs` (uid container ≠ uid host) |
| `yt-dlp` échoue (403, throttling) | Synchroniser les cookies YouTube via l'extension navigateur, ou `docker compose restart` pour forcer la mise à jour de yt-dlp |
| Boucle de redirection vers le login | `AUTH_JWT_SECRET` différent entre rev0auth et SongSurf — vérifier caractère par caractère |
| 503 sans redirection | `AUTH_SERVICE_LOGIN_URL` vide dans `.env` |
| Frontend pas à jour après deploy | Rebuild manquant : `--build` obligatoire (le frontend est compilé dans l'image) |

Pièges spécifiques Synology (rsync, PATH ssh, sudo) : [`../deploy_troubleshooting.md`](../deploy_troubleshooting.md).

---

## 10. Sécurité

- Le port 8081 (SongSurf) ne doit **jamais** être exposé au WAN — seul Watcher reçoit du trafic
- SongSurf rejette toute requête sans `X-Watcher-Token` valide (comparaison à temps constant)
- URLs validées (HTTPS + domaines YouTube/YouTube Music uniquement)
- Les containers tournent sous uid 1000 (non-root)
- `restart: on-failure` pour ne pas redémarrer sur arrêt manuel
