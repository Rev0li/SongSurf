# Guide de déploiement — SongSurf

Déploiement sur NAS Synology via Docker Compose, accessible depuis l'extérieur via Tailscale + reverse proxy VPS.

> **Déploiement courant** : une fois la première installation faite, utilise `make deploy-nas` depuis `SongSurf/SongSurf/` (rsync + rebuild + restart en une commande, `make deploy-nas-dry` pour prévisualiser). Les pièges Synology sont regroupés en [§11](#11-pièges-synology-make-deploy-nas).

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

# Cookies YouTube par utilisateur (make deploy-nas le crée aussi s'il manque)
mkdir -p data/cookies && chmod 700 data/cookies
```

> ⚠️ Le `chmod 777` est requis si l'uid NAS diffère de 1000 (uid du container `songsurf`). `make init-dirs` le fait automatiquement.

---

## 2. Copier les fichiers

Depuis la machine de dev, la commande tout-en-un :

```bash
make deploy-nas                     # NAS_HOST par défaut = alias SSH nas-songsurf
make deploy-nas NAS_USER=<user> NAS_HOST=<ip> NAS_DIR=/volume1/docker/songsurf
```

`NAS_HOST` vaut par défaut `nas-songsurf`, l'alias de `~/.ssh/config` : son `HostName` pointe sur l'**IP Tailscale** du NAS, stable et joignable hors LAN (l'IP LAN change avec le DHCP). Aucune IP n'est écrite dans le repo, qui est public.

Elle rsync le projet (en excluant `data/`, `logs/`, `.env`, `.secrets`), crée `data/cookies` s'il manque, puis rebuild et relance les containers. `.env` et `.secrets` restent sur le NAS entre les déploiements — les copier une seule fois :

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
| `.secrets` | `AUTH_JWT_SECRET`, `WATCHER_SECRET`, `SONGSURF_EVENTS_SECRET`, `SONGSURF_PROXY_SECRET`, clés Flask | 600 |

Les deux sont chargés par Docker Compose via `env_file`. Ne jamais committer `.secrets`.

**Pour la prod avec rev0auth :** copier la valeur `AUTH_JWT_SECRET` de rev0auth dans `.secrets` (identique octet par octet), renseigner `AUTH_SERVICE_LOGIN_URL` dans `.env` et vérifier `DEV_MODE=false`. Contrat JWT : [`CONNECTOR.md`](CONNECTOR.md).

**Porte du portail (AUTH-09) :** sur un NAS existant, ajouter à la main dans `.secrets` `SONGSURF_PROXY_SECRET=<valeur>` (`openssl rand -hex 32`), la même valeur que le fichier secret lu par Caddy sur le VPS, puis redéployer. Vide = porte ignorée, seul le JWT marche. Contrat et ordre de bascule : [`CONNECTOR.md`](CONNECTOR.md).

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
| `yt-dlp` échoue (403, throttling) | Synchroniser les cookies YouTube via l'extension navigateur, ou monter yt-dlp : `make bump-ytdlp` puis `make deploy-nas` (version épinglée, plus de mise à jour au boot) |
| Boucle de redirection vers le login | `AUTH_JWT_SECRET` différent entre rev0auth et SongSurf — vérifier caractère par caractère |
| 503 sans redirection | `AUTH_SERVICE_LOGIN_URL` vide dans `.env` |
| Frontend pas à jour après deploy | Rebuild manquant : `--build` obligatoire (le frontend est compilé dans l'image) |

Pièges spécifiques Synology (rsync, PATH ssh, socket Docker) : voir [§11](#11-pièges-synology-make-deploy-nas).

---

## 10. Sécurité

- Le port 8081 (SongSurf) ne doit **jamais** être exposé au WAN — seul Watcher reçoit du trafic
- SongSurf rejette toute requête sans `X-Watcher-Token` valide (comparaison à temps constant)
- URLs validées (HTTPS + domaines YouTube/YouTube Music uniquement)
- Les containers tournent sous uid 1000 (non-root)
- `restart: on-failure` pour ne pas redémarrer sur arrêt manuel

---

## 11. Pièges Synology (`make deploy-nas`)

Problèmes réels rencontrés lors de la mise en place de `make deploy-nas` sur Synology DSM. Le `Makefile` (section `deploy-nas`) intègre déjà tous ces correctifs.

### 11.1 rsync — Permission denied (auth)

**Symptôme**
```
Permission denied, please try again.
rsync: connection unexpectedly closed (code 12)
```

**Cause** : Le dossier `~/.ssh/` n'existait pas sur le NAS — `ssh-copy-id` avait échoué silencieusement.

**Solution**
```bash
# Créer le dossier .ssh sur le NAS
ssh -p 22 rev0li08@<ip-du-nas> "mkdir -p ~/.ssh && chmod 700 ~/.ssh"

# Copier la clé publique
cat ~/.ssh/nas_songsurf.pub | ssh -p 22 rev0li08@<ip-du-nas> \
  "cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

---

### 11.2 rsync — Permission denied (service Synology)

**Symptôme** : SSH avec clé fonctionne (`ssh nas-songsurf "echo ok"` = ok) mais rsync échoue quand même avec "Permission denied".

**Cause** : Synology patche son binaire rsync pour vérifier que le service rsync DSM est activé, même en mode SSH.

**Solution** : DSM → Panneau de configuration → Services de fichiers → onglet **rsync** → cocher "Activer le service rsync" (port 22) → Apply.

---

### 11.3 docker-compose introuvable (PATH SSH non-interactif)

**Symptôme**
```
[compose-switch] Aucun moteur Compose trouvé.
```

**Cause** : `/usr/local/bin` n'est pas dans le PATH des sessions SSH non-interactives sur Synology. `docker-compose` est pourtant bien à `/usr/local/bin/docker-compose`.

**Solution** : Préfixer le PATH dans la commande SSH du Makefile :
```bash
PATH=/usr/local/bin:/var/packages/Docker/target/usr/bin:$PATH
```

---

### 11.4 Variables secrets non interpolées (docker-compose V1)

**Symptôme**
```
Missing mandatory value for "environment" option: WATCHER_FLASK_SECRET_KEY is required
```

**Cause** : Docker-compose V1 (`1.28.5`) ne charge pas `env_file` pour l'interpolation des variables dans `docker-compose.yml` — seulement pour les env vars du container. Le `${VAR:?message}` dans `environment:` nécessite que la variable soit dans le shell.

**Solution** : Sourcer `.env` et `.secrets` avant docker-compose avec `set -a` :
```bash
set -a && . ./.env && . ./.secrets && set +a && docker-compose ...
```
`set -a` exporte automatiquement toutes les variables sourcées vers les sous-processus.

---

### 11.5 docker introuvable (PATH SSH non-interactif)

**Symptôme**
```
sh: docker: command not found
```

**Cause** : Docker (installé via le package DSM "Docker") est dans `/var/packages/Docker/target/usr/bin/`, absent du PATH SSH.

**Solution** : Inclus dans le PATH du Makefile :
```bash
PATH=/usr/local/bin:/var/packages/Docker/target/usr/bin:$PATH
```

Vérification : `ssh nas-songsurf "PATH=/var/packages/Docker/target/usr/bin:\$PATH docker ps"`

---

### 11.6 Permission refusée sur le socket Docker

**Symptôme**
```
PermissionError: [Errno 13] Permission denied
docker.errors.DockerException: Error while fetching server API version
```

**Cause** : `/var/run/docker.sock` appartient à `root:root` (660). `rev0li08` n'est pas dans le groupe root.

**Solution** : Tâche planifiée DSM exécutée au démarrage en tant que `root` :

DSM → Panneau de configuration → Planificateur de tâches → Créer → Tâche déclenchée → Script défini par l'utilisateur

- **Utilisateur** : `root`
- **Événement** : Démarrage
- **Script** :
```bash
chown root:administrators /var/run/docker.sock
chmod 660 /var/run/docker.sock
```

`rev0li08` est dans le groupe `administrators` (gid=101) — ce changement lui donne accès au socket.
Exécuter la tâche manuellement après création pour l'appliquer sans reboot.

> Cette tâche est nécessaire à chaque redémarrage du NAS car `/var/run/` est recréé au boot.

### Récapitulatif de la configuration NAS actuelle

| Élément | Valeur |
|---|---|
| Host (`NAS_HOST`) | alias SSH `nas-songsurf` (dans `~/.ssh/config`, `HostName` = IP Tailscale du NAS) |
| User | `rev0li08` |
| Port SSH | `22` |
| Clé SSH | `~/.ssh/nas_songsurf` |
| Dossier deploy | `/volume1/docker/songsurf/` |
| docker-compose | `/usr/local/bin/docker-compose` (v1.28.5) |
| docker | `/var/packages/Docker/target/usr/bin/docker` |
| `.env` / `.secrets` | Sur le NAS uniquement — jamais dans git, exclus du rsync, copiés une fois via `scp` |

---

## 12. Plus tard — CI/CD automatique

Piste : un runner GitHub Actions auto-hébergé sur le NAS (connexion **sortante** vers GitHub, aucun port entrant). Sur `git push main`, le runner exécute `make deploy-nas` localement.
