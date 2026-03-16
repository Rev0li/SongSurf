# Guide de déploiement — SongSurf

Déploiement sur NAS Synology via Docker Compose, accessible depuis l'extérieur via Tailscale + reverse proxy OVH/DuckDNS.

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

# Créer les dossiers de données
mkdir -p data/music data/music_guest data/temp data/temp_guest logs
```

---

## 2. Cloner / Copier les fichiers

Copier tout le contenu du projet dans `/volume1/docker/SongSurf/` :

```
SongSurf/
├── Dockerfile
├── docker-compose.yml
├── docker/
│   └── entrypoint.sh
└── python-server/
    ├── app.py
    ├── downloader.py
    ├── organizer.py
    ├── requirements.txt
    └── templates/
        ├── dashboard.html
        ├── guest_dashboard.html
        └── login.html
```
```bash
cp SongSurf/Dockerfile SongSurf/docker-compose.yml /volume1/docker/SongSurf/ && \
cp SongSurf/docker/entrypoint.sh /volume1/docker/SongSurf/docker/ && \
cp SongSurf/python-server/app.py \
   SongSurf/python-server/downloader.py \
   SongSurf/python-server/organizer.py \
   SongSurf/python-server/requirements.txt \
   /volume1/docker/SongSurf/python-server/ && \
cp SongSurf/python-server/templates/dashboard.html \
   SongSurf/python-server/templates/guest_dashboard.html \
   SongSurf/python-server/templates/login.html \
   /volume1/docker/SongSurf/python-server/templates/
```

Pense à créer les dossiers d'abord si ils n'existent pas encore :

```bash
mkdir -p /volume1/docker/SongSurf/docker \
         /volume1/docker/SongSurf/python-server/templates
```
---

## 3. Configurer les mots de passe

Éditer `docker-compose.yml` et changer les valeurs suivantes :

```yaml
environment:
  - SONGSURF_PASSWORD=VotreMotDePasseAdmin        # ← OBLIGATOIRE
  - FLASK_SECRET_KEY=UneCléAléatoireSecurisée     # ← OBLIGATOIRE (32+ chars)
  - SONGSURF_GUEST_PASSWORD=MotDePasseInvité      # ← laisser vide pour désactiver les guests
  - GUEST_MAX_SONGS=10
  - GUEST_SESSION_TTL=3600
```

> ⚠️ Ne jamais laisser les valeurs par défaut en production.

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

# Build de l'image
docker compose build

# Démarrage en arrière-plan
docker compose up -d

# Voir les logs
docker compose logs -f

 sudo docker-compose up -d && sudo docker logs -f songsurf
```

Le serveur est disponible sur : `http://<IP-NAS>:8080`

---

## 6. Mise à jour

Quand vous modifiez `app.py`, `downloader.py` ou `organizer.py` :

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Quand vous modifiez uniquement les templates HTML (pas de rebuild nécessaire car monté en volume) :
```bash
# Aucune action requise — les templates sont rechargés automatiquement
```

---

## 7. Accès Tailscale / VPN

SongSurf utilise `network_mode: host` pour accéder directement au réseau du NAS.  
Avec Tailscale installé sur le NAS, il est accessible via l'IP Tailscale : `http://<tailscale-ip>:8080`

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
docker compose logs -f

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
| Port 8080 non accessible | Vérifier le firewall NAS + `docker compose ps` |
| Permission denied sur `/data/plex_music` | Vérifier les droits du dossier Plex (`chmod -R 777` ou `chown 1000`) |
| `yt-dlp` échoue | `docker compose restart` pour forcer la mise à jour |
| MusicBrainz timeout | Scan Beets ralenti par rate-limiting (1 req/s), attendre |
| Session guest expirée pendant DL | Le nettoyage est différé 120s après le téléchargement ZIP |

---

## 12. Sécurité

- Les mots de passe admin et guest sont distincts
- Brute-force protégé : blocage 15 min après 5 tentatives
- Les URLs sont validées (YouTube/YouTube Music uniquement)
- Les erreurs yt-dlp ne sont **pas** exposées aux guests
- Le serveur tourne sous l'uid 1000 (non-root)
- `restart: on-failure` pour ne pas redémarrer sur arrêt manuel
