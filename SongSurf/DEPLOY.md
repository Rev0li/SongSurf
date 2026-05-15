# Guide de déploiement — SongSurf

Déploiement sur NAS Synology via Docker Compose, accessible depuis l'extérieur via Tailscale + reverse proxy OVH/DuckDNS.

---

## 0. Toggle global Local/NAS (recommandé)

Le projet intègre un switch global via variables d'environnement :

- `DEPLOY_TARGET=local` : mode dev/local (bridge + ports publiés)
- `DEPLOY_TARGET=nas` : mode NAS/live (`network_mode: host`)

Fichiers utilisés :

- `docker-compose.yml` (base commune)
- `docker-compose.nas.yml` (override NAS)
- `docker/compose-switch.sh` (lance le bon combo automatiquement)

### Configuration rapide

1. Générer `.env` et `.secrets` (clés + mots de passe) :

```bash
make secrets
```

Le script demande le mode déploiement, les mots de passe, et génère toutes les clés cryptographiques automatiquement. Deux fichiers sont créés : `.env` (config, 644) et `.secrets` (clés, chmod 600 — ne jamais committer).

2. Vérifier les valeurs dans `.env` si nécessaire :

- `DEPLOY_TARGET=local` ou `DEPLOY_TARGET=nas`
- `WATCHER_PORT` (port d'écoute Watcher, défaut : 8080)
- `AUTH_SERVICE_LOGIN_URL` (à remplir quand rev0auth sera en ligne)

3. Vérifier la config résolue :

```bash
./docker/compose-switch.sh config
```

### Commandes standard

```bash
# Démarrer selon DEPLOY_TARGET défini dans .env
./docker/compose-switch.sh up -d --build

# Voir les logs
./docker/compose-switch.sh logs -f

# Arrêter
./docker/compose-switch.sh down
```

### Forcer un mode ponctuel sans modifier .env

```bash
DEPLOY_TARGET=local ./docker/compose-switch.sh up -d
DEPLOY_TARGET=nas   ./docker/compose-switch.sh up -d
```

### Rollback de mode (NAS -> Local ou Local -> NAS)

```bash
./docker/compose-switch.sh down
DEPLOY_TARGET=local ./docker/compose-switch.sh up -d
```

Remplace `local` par `nas` pour l'opération inverse.

---

## Prérequis

- NAS Synology avec Docker (DSM 7+)
- Accès SSH au NAS
- Docker + Docker Compose installés
- (Optionnel) Tailscale pour l'accès VPN
- (Optionnel) VPS avec reverse proxy + DuckDNS pour l'accès public

---

## 1. Préparer le NAS

```bash
# Créer le dossier du projet
mkdir -p /volume1/docker/SongSurf
cd /volume1/docker/SongSurf

# Créer les dossiers de données avec les bons droits (uid container = 1000)
mkdir -p data/music data/music_guest data/temp logs
chmod 777 data/music data/music_guest data/temp logs
```

> ⚠️ Le `chmod 777` est requis si l'uid NAS diffère de 1000 (uid du container `songsurf`). `make init-dirs` le fait automatiquement si tu déploies depuis une machine avec Make.

---

## 2. Cloner / Copier les fichiers

La méthode recommandée est de copier (ou cloner) le dépôt complet dans `/volume1/docker/SongSurf/`.

Exemple en Git :

```bash
cd /volume1/docker
git clone <url-du-repo> SongSurf
cd SongSurf
```

Exemple sans Git (depuis une machine locale) :

```bash
rsync -av --delete SongSurf/ <user>@<nas>:/volume1/docker/SongSurf/
```

Ensuite, configure simplement `.env` puis utilise `docker/compose-switch.sh`.
---

## 3. Générer les secrets

Ne jamais éditer `docker-compose.yml` pour y mettre des secrets. Utiliser le générateur interactif :

```bash
make secrets
```

Il crée deux fichiers :

| Fichier | Contenu | Permissions |
|---------|---------|-------------|
| `.env` | Config non-secrète (ports, timeouts, mode) | 644 |
| `.secrets` | Clés Flask, WATCHER_SECRET, mots de passe, JWT | 600 |

Les deux fichiers sont chargés automatiquement par Docker Compose via `env_file`. Ne jamais committer `.secrets`.

**Pour la prod avec rev0auth (Phase 3) :** après avoir lancé rev0auth, copier sa valeur `AUTH_JWT_SECRET` dans `.secrets`, puis renseigner `AUTH_SERVICE_LOGIN_URL` dans `.env` et mettre `DEV_MODE=false`.

---

## 4. Configurer le dossier Plex

Si vous utilisez Plex sur le NAS, configurez le volume de destination :

```yaml
volumes:
  # Remplacer par le chemin réel de votre bibliothèque Plex Music
  - /volume1/plex_media/music:/data/plex_music
```

Vérifier les droits :
```bash
ls -la /volume1/plex_media/music
# Doit afficher drwxrwxrwx (ou au moins rwx pour others / uid 1000)
```

---

## 5. Build & Démarrage

```bash
cd /volume1/docker/SongSurf

# Démarrage en arrière-plan (respecte DEPLOY_TARGET)
./docker/compose-switch.sh up -d --build

# Voir les logs
./docker/compose-switch.sh logs -f
```

Le portail Watcher est disponible sur : `http://<IP-NAS>:<WATCHER_PORT>` (défaut : 8080)

---

## 6. Mise à jour

Quand vous modifiez `app.py`, `downloader.py` ou `organizer.py` :

```bash
./docker/compose-switch.sh down
./docker/compose-switch.sh up -d --build
```

Le frontend est SvelteKit — tout changement de code nécessite un rebuild Docker :
```bash
./docker/compose-switch.sh up -d --build
```

---

## 7. Accès Tailscale / VPN

En mode `nas`, les services utilisent `network_mode: host` pour accéder directement au réseau du NAS.  
En mode `local`, les services restent en bridge Docker avec ports publiés.  
Avec Tailscale installé sur le NAS, le portail est accessible via l'IP Tailscale : `http://<tailscale-ip>:8080`

---

## 8. Reverse Proxy OVH + DuckDNS

Architecture réseau :

```
Internet (utilisateur)
        │
        ▼
  DuckDNS (DNS public)
  mondomaine.duckdns.org
        │
        ▼
   VPS OVH (Nginx)
   Reverse proxy → port SongSurf
        │
        │  Tailscale (tunnel chiffré)
        │
        ▼
   NAS Synology
   Docker SongSurf → port 8080
```

Exemple de configuration Nginx sur le VPS :

```nginx
server {
    listen 443 ssl;
    server_name songsurf.votredomaine.duckdns.org;

    ssl_certificate     /etc/letsencrypt/live/votredomaine.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/votredomaine.duckdns.org/privkey.pem;

    location / {
        proxy_pass         http://<tailscale-ip-NAS>:8080;
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 300s;   # Important pour les téléchargements longs
    }
}
```

---

## 9. Workflow d'utilisation Admin

### Téléchargement normal (Artist/Album/Titre)
1. Coller un lien YouTube Music dans l'input
2. Cliquer **Extraire** → vérifier/modifier les métadonnées
3. Cliquer **Télécharger** (Mode Playlist **désactivé**)
4. Les fichiers arrivent dans `data/music/Artist/Album/`

### Téléchargement playlist (Album/Titre)
1. Coller un lien de playlist YouTube Music
2. **Activer** le toggle **Mode Playlist**
3. Cliquer **Télécharger**
4. Les fichiers arrivent dans `data/music/NomPlaylist/`

### Valider les métadonnées (Beets)
1. Aller dans l'onglet **Métadonnées**
2. Cliquer **Analyser** → MusicBrainz propose des corrections
3. Valider/ignorer par album ou par champ
4. Cliquer **Appliquer tout**
5. Cliquer **Déplacer vers Plex** (pour la bibliothèque normale)

### Envoyer les playlists vers Plex
1. Aller dans l'onglet **Métadonnées**
2. La section **Dossiers Playlist** apparaît automatiquement si des playlists sont présentes
3. Cliquer **Envoyer dans Mes Music (Plex)**

---

## 10. Logs

```bash
# Logs techniques en temps réel
./docker/compose-switch.sh logs -f

# Journal d'activité lisible
cat /volume1/docker/SongSurf/logs/activity.log
```

Format du journal d'activité :
```
2026-03-16 14:23:01 | 🎭 CONNEXION   | Alice | session abc12345
2026-03-16 14:25:12 | 🎵 DOWNLOAD    | Alice | The Weeknd - Blinding Lights
2026-03-16 14:26:30 | 🧹 FIN SESSION | Alice | 1 chanson(s) | raison: téléchargement ZIP effectué
```

---

## 11. Dépannage

| Problème | Solution |
|---|---|
| Port non accessible | Vérifier `WATCHER_PORT` dans `.env` + firewall NAS + `docker compose ps` |
| `Permission denied: /app/logs/...` | `chmod 777 data/music data/music_guest data/temp logs` (uid container ≠ uid host) |
| Permission denied sur `/data/plex_music` | Vérifier les droits du dossier Plex (`chmod -R 777` ou `chown 1000`) |
| `yt-dlp` échoue | `docker compose restart` pour forcer la mise à jour |
| MusicBrainz timeout | Scan Beets ralenti par rate-limiting (1 req/s), attendre |
| Session guest expirée pendant DL | Le nettoyage est différé 120s après le téléchargement ZIP |
| Boucle de login infinie (prod) | Vérifier `AUTH_JWT_SECRET` dans `.secrets` + `AUTH_SERVICE_LOGIN_URL` dans `.env` |

---

## 12. Sécurité

- Les mots de passe admin et guest sont distincts
- Brute-force protégé : blocage 15 min après 5 tentatives
- Les URLs sont validées (YouTube/YouTube Music uniquement)
- Les erreurs yt-dlp ne sont **pas** exposées aux guests
- Le serveur tourne sous l'uid 1000 (non-root)
- `restart: on-failure` pour ne pas redémarrer sur arrêt manuel
