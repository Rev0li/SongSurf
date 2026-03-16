# Guide de dÃ©ploiement â€” SongSurf

DÃ©ploiement sur NAS Synology via Docker Compose, accessible depuis l'extÃ©rieur via Tailscale + reverse proxy OVH/DuckDNS.

---

## PrÃ©requis

- NAS Synology avec Docker (DSM 7+)
- AccÃ¨s SSH au NAS
- Docker + Docker Compose installÃ©s
- (Optionnel) Tailscale pour l'accÃ¨s VPN
- (Optionnel) VPS avec reverse proxy + DuckDNS pour l'accÃ¨s public

---

## 1. PrÃ©parer le NAS

```bash
# CrÃ©er le dossier du projet
mkdir -p /volume1/docker/SongSurf
cd /volume1/docker/SongSurf

# CrÃ©er les dossiers de donnÃ©es
mkdir -p data/music data/music_guest data/temp data/temp_guest logs
```

---

## 2. Cloner / Copier les fichiers

Copier tout le contenu du projet dans `/volume1/docker/SongSurf/` :

```
SongSurf/
â”œâ”€â”€ Dockerfile
â”œâ”€â”€ docker-compose.yml
â”œâ”€â”€ docker/
â”‚   â””â”€â”€ entrypoint.sh
â””â”€â”€ python-server/
    â”œâ”€â”€ app.py
    â”œâ”€â”€ downloader.py
    â”œâ”€â”€ organizer.py
    â”œâ”€â”€ requirements.txt
    â””â”€â”€ templates/
        â”œâ”€â”€ dashboard.html
        â”œâ”€â”€ guest_dashboard.html
        â””â”€â”€ login.html
```

---

## 3. Configurer les mots de passe

Ã‰diter `docker-compose.yml` et changer les valeurs suivantes :

```yaml
environment:
  - SONGSURF_PASSWORD=VotreMotDePasseAdmin        # â† OBLIGATOIRE
  - FLASK_SECRET_KEY=UneClÃ©AlÃ©atoireSecurisÃ©e    # â† OBLIGATOIRE (32+ chars)
  - SONGSURF_GUEST_PASSWORD=MotDePasseInvitÃ©     # â† laisser vide pour dÃ©sactiver les guests
  - GUEST_MAX_SONGS=10
  - GUEST_SESSION_TTL=3600
```

> âš ï¸ Ne jamais laisser les valeurs par dÃ©faut en production.

---

## 4. Configurer le dossier Plex

Si vous utilisez Plex sur le NAS, configurez le volume de destination :

```yaml
volumes:
  # Remplacer par le chemin rÃ©el de votre bibliothÃ¨que Plex Music
  - /volume1/plex_media/music:/data/plex_music
```

VÃ©rifier les droits :
```bash
ls -la /volume1/plex_media/music
# Doit afficher drwxrwxrwx (ou au moins rwx pour others / uid 1000)
```

---

## 5. Build & DÃ©marrage

```bash
cd /volume1/docker/SongSurf

# Build de l'image
docker compose build

# DÃ©marrage en arriÃ¨re-plan
docker compose up -d

# Voir les logs
docker compose logs -f
```

Le serveur est disponible sur : `http://<IP-NAS>:8080`

---

## 6. Mise Ã  jour

Quand vous modifiez `app.py`, `downloader.py` ou `organizer.py` :

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Quand vous modifiez uniquement les templates HTML (pas de rebuild nÃ©cessaire car montÃ© en volume) :
```bash
# Aucune action requise â€” les templates sont rechargÃ©s automatiquement
```

---

## 7. AccÃ¨s Tailscale / VPN

SongSurf utilise `network_mode: host` pour accÃ©der directement au rÃ©seau du NAS.  
Avec Tailscale installÃ© sur le NAS, il est accessible via l'IP Tailscale : `http://<tailscale-ip>:8080`

---

## 8. Reverse Proxy OVH + DuckDNS

Sur votre VPS (ex: Nginx) :

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
        proxy_read_timeout 300s;   # Important pour les tÃ©lÃ©chargements longs
    }
}
```

---

## 9. Workflow d'utilisation Admin

### TÃ©lÃ©chargement normal (Artist/Album/Titre)
1. Coller un lien YouTube Music dans l'input
2. Cliquer **Extraire** â†’ vÃ©rifier/modifier les mÃ©tadonnÃ©es
3. Cliquer **TÃ©lÃ©charger** (Mode Playlist **dÃ©sactivÃ©**)
4. Les fichiers arrivent dans `data/music/Artist/Album/`

### TÃ©lÃ©chargement playlist (Album/Titre)
1. Coller un lien de playlist YouTube Music
2. **Activer** le toggle **Mode Playlist**
3. Cliquer **TÃ©lÃ©charger**
4. Les fichiers arrivent dans `data/music/NomPlaylist/`

### Valider les mÃ©tadonnÃ©es (Beets)
1. Aller dans l'onglet **MÃ©tadonnÃ©es**
2. Cliquer **Analyser** â†’ MusicBrainz propose des corrections
3. Valider/ignorer par album ou par champ
4. Cliquer **Appliquer tout**
5. Cliquer **DÃ©placer vers Plex** (pour la bibliothÃ¨que normale)

### Envoyer les playlists vers Plex
1. Aller dans l'onglet **MÃ©tadonnÃ©es**
2. La section **Dossiers Playlist** apparaÃ®t automatiquement si des playlists sont prÃ©sentes
3. Cliquer **Envoyer dans Mes Music (Plex)**

---

## 10. Logs

```bash
# Logs techniques en temps rÃ©el
docker compose logs -f

# Journal d'activitÃ© lisible
cat /volume1/docker/SongSurf/logs/activity.log
```

Format du journal d'activitÃ© :
```
2026-03-16 14:23:01 | ðŸŽ­ CONNEXION  | Alice | session abc12345
2026-03-16 14:25:12 | ðŸŽµ DOWNLOAD   | Alice | The Weeknd - Blinding Lights
2026-03-16 14:26:30 | ðŸ§¹ FIN SESSION | Alice | 1 chanson(s) | raison: tÃ©lÃ©chargement ZIP effectuÃ©
```

---

## 11. DÃ©pannage

| ProblÃ¨me | Solution |
|---|---|
| Port 8080 non accessible | VÃ©rifier le firewall NAS + `docker compose ps` |
| Permission denied sur `/data/plex_music` | VÃ©rifier les droits du dossier Plex (`chmod -R 777` ou `chown 1000`) |
| `yt-dlp` Ã©choue | `docker compose restart` pour forcer la mise Ã  jour |
| MusicBrainz timeout | Scan Beets ralenti par rate-limiting (1 req/s), attendre |
| Session guest expirÃ©e pendant DL | Le nettoyage est diffÃ©rÃ© 120s aprÃ¨s le tÃ©lÃ©chargement ZIP |

---

## 12. SÃ©curitÃ©

- Les mots de passe admin et guest sont distincts
- Brute-force protÃ©gÃ© : blocage 15 min aprÃ¨s 5 tentatives
- Les URLs sont validÃ©es (YouTube/YouTube Music uniquement)
- Les erreurs yt-dlp ne sont **pas** exposÃ©es aux guests
- Le serveur tourne sous l'uid 1000 (non-root)
- `restart: on-failure` pour ne pas redÃ©marrer sur arrÃªt manuel
