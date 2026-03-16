# SongSurf ðŸŽµ

Dashboard web de tÃ©lÃ©chargement musical via YouTube Music, dÃ©ployÃ© sur NAS Synology avec Docker.

## FonctionnalitÃ©s

### Admin
- **TÃ©lÃ©chargement** : URL YouTube Music (chanson ou playlist)
- **Mode Playlist** : structure `Album/Titre.mp3` (toggle)
- **Mode Normal** : structure `Artiste/Album/Titre.mp3` avec auto-dÃ©tection des featurings
- **MÃ©tadonnÃ©es (Beets)** : scan MusicBrainz + corrections manuelles des tags ID3
- **DÃ©placer vers Plex** : dÃ©place la bibliothÃ¨que normale vers le dossier Plex aprÃ¨s validation
- **Envoyer dans Mes Music** : dÃ©place les playlists vers Plex (onglet MÃ©tadonnÃ©es)
- **Queue bridÃ©e** : 1 tÃ©lÃ©chargement Ã  la fois, file d'attente visible
- **Logs** : activity.log lisible + logs techniques console

### Guest
- AccÃ¨s par mot de passe sÃ©parÃ©
- Quota configurable (dÃ©faut : 10 chansons/session)
- Session TTL configurable (dÃ©faut : 1 heure)
- Mode Playlist disponible
- TÃ©lÃ©chargement ZIP en 1 clic
- Pop-up expiration 5 min avant la fin de session (prolonger ou tÃ©lÃ©charger)
- URL validÃ©es (YouTube Music uniquement, protection injection)

## Structure du projet

```
SongSurf/
â”œâ”€â”€ Dockerfile
â”œâ”€â”€ docker-compose.yml
â”œâ”€â”€ docker/
â”‚   â””â”€â”€ entrypoint.sh          # Mise Ã  jour yt-dlp au dÃ©marrage
â”œâ”€â”€ python-server/
â”‚   â”œâ”€â”€ app.py                 # Serveur Flask (routes admin + guest + beets)
â”‚   â”œâ”€â”€ downloader.py          # Wrapper yt-dlp
â”‚   â”œâ”€â”€ organizer.py           # Organisation des MP3 (normal + playlist)
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â””â”€â”€ templates/
â”‚       â”œâ”€â”€ dashboard.html     # Dashboard admin
â”‚       â”œâ”€â”€ guest_dashboard.html
â”‚       â””â”€â”€ login.html
â””â”€â”€ DEPLOY.md
```

## Variables d'environnement

| Variable | DÃ©faut | Description |
|---|---|---|
| `SONGSURF_PASSWORD` | *(requis)* | Mot de passe admin |
| `FLASK_SECRET_KEY` | *(requis)* | ClÃ© secrÃ¨te Flask |
| `SONGSURF_GUEST_PASSWORD` | â€” | Mot de passe guest (vide = dÃ©sactivÃ©) |
| `GUEST_MAX_SONGS` | `10` | Quota de chansons par session guest (0 = illimitÃ©) |
| `GUEST_SESSION_TTL` | `3600` | DurÃ©e de session guest en secondes |
| `PLEX_MUSIC_DIR` | `/data/plex_music` | Chemin interne Docker vers le dossier Plex |
| `TZ` | `Europe/Paris` | Fuseau horaire |

## Modes de structure musicale

| Mode | Structure | Cas d'usage |
|---|---|---|
| Normal (dÃ©faut) | `Artist/Album/Title.mp3` | Albums studio |
| Playlist | `Album/Title.mp3` | Playlists YouTube |

> Les dossiers Playlist sont **ignorÃ©s par Beets** et dÃ©placÃ©s sÃ©parÃ©ment via le bouton **Envoyer dans Mes Music**.

## Volumes Docker

| Volume hÃ´te | Volume conteneur | Description |
|---|---|---|
| `./data/music` | `/data/music` | BibliothÃ¨que admin (source avant Plex) |
| `./data/music_guest/<sid>` | `/data/music_guest` | Fichiers guest |
| `./data/temp` | `/data/temp` | TÃ©lÃ©chargements temporaires admin |
| `./data/temp_guest/<sid>` | `/data/temp_guest` | Temporaires guest |
| `./logs` | `/app/logs` | Logs (activity.log) |
| `./python-server/templates` | `/app/templates` | Templates (live reload sans rebuild) |
| `/volume1/plex_media/music` | `/data/plex_music` | Destination Plex |

## API Routes principales

### Admin
| MÃ©thode | Route | Description |
|---|---|---|
| POST | `/api/extract` | Extraire les mÃ©tadonnÃ©es d'une URL |
| POST | `/api/download` | Ajouter une chanson Ã  la queue |
| POST | `/api/download-playlist` | Ajouter une playlist Ã  la queue |
| GET | `/api/status` | Ã‰tat de la queue admin |
| GET | `/api/stats` | Statistiques de la bibliothÃ¨que |
| GET | `/api/playlists` | Lister les dossiers playlist |
| POST | `/api/move-to-plex` | DÃ©placer la biblio normale vers Plex |
| POST | `/api/move-playlists-to-plex` | DÃ©placer les playlists vers Plex |
| POST | `/api/beets/scan` | Scanner la bibliothÃ¨que MusicBrainz |
| POST | `/api/beets/apply` | Appliquer les corrections de tags |
| GET | `/api/beets/status` | Ã‰tat du scan/apply Beets |

### Guest
| MÃ©thode | Route | Description |
|---|---|---|
| POST | `/api/guest/extract` | Extraire les mÃ©tadonnÃ©es |
| POST | `/api/guest/download` | Ajouter Ã  la queue guest |
| GET | `/api/guest/status` | Ã‰tat de la queue guest |
| POST | `/api/guest/prepare-zip` | CrÃ©er le ZIP |
| GET | `/api/guest/download-zip` | TÃ©lÃ©charger le ZIP |
| POST | `/api/guest/extend-session` | Prolonger la session d'1 heure |
