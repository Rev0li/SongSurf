# SongSurf 🎵

Dashboard web de téléchargement musical via YouTube Music, déployé sur NAS Synology avec Docker.

## Fonctionnalités

### Admin
- **Téléchargement** : URL YouTube Music (chanson ou playlist)
- **Mode Playlist** : structure `Album/Titre.mp3` (toggle)
- **Mode Normal** : structure `Artiste/Album/Titre.mp3` avec auto-détection des featurings
- **Métadonnées (Beets)** : scan MusicBrainz + corrections manuelles des tags ID3
- **Déplacer vers Plex** : déplace la bibliothèque normale vers le dossier Plex après validation
- **Envoyer dans Mes Music** : déplace les playlists vers Plex (onglet Métadonnées)
- **Queue bridée** : 1 téléchargement à la fois, file d'attente visible
- **Logs** : activity.log lisible + logs techniques console

### Guest
- Accès par mot de passe séparé
- Quota configurable (défaut : 10 chansons/session)
- Session TTL configurable (défaut : 1 heure)
- Mode Playlist disponible
- Téléchargement ZIP en 1 clic
- Pop-up expiration 5 min avant la fin de session (prolonger ou télécharger)
- URLs validées (YouTube Music uniquement, protection injection)

## Structure du projet

```
SongSurf/
├── Dockerfile
├── docker-compose.yml
├── docker/
│   └── entrypoint.sh          # Mise à jour yt-dlp au démarrage
├── python-server/
│   ├── app.py                 # Serveur Flask (routes admin + guest + beets)
│   ├── downloader.py          # Wrapper yt-dlp
│   ├── organizer.py           # Organisation des MP3 (normal + playlist)
│   ├── requirements.txt
│   └── templates/
│       ├── dashboard.html     # Dashboard admin
│       ├── guest_dashboard.html
│       └── login.html
└── DEPLOY.md
```

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `SONGSURF_PASSWORD` | *(requis)* | Mot de passe admin |
| `FLASK_SECRET_KEY` | *(requis)* | Clé secrète Flask |
| `SONGSURF_GUEST_PASSWORD` | – | Mot de passe guest (vide = désactivé) |
| `GUEST_MAX_SONGS` | `10` | Quota de chansons par session guest (0 = illimité) |
| `GUEST_SESSION_TTL` | `3600` | Durée de session guest en secondes |
| `PLEX_MUSIC_DIR` | `/data/plex_music` | Chemin interne Docker vers le dossier Plex |
| `TZ` | `Europe/Paris` | Fuseau horaire |

## Modes de structure musicale

| Mode | Structure | Cas d'usage |
|---|---|---|
| Normal (défaut) | `Artist/Album/Title.mp3` | Albums studio |
| Playlist | `Album/Title.mp3` | Playlists YouTube |

> Les dossiers Playlist sont **ignorés par Beets** et déplacés séparément via le bouton **Envoyer dans Mes Music**.

## Volumes Docker

| Volume hôte | Volume conteneur | Description |
|---|---|---|
| `./data/music` | `/data/music` | Bibliothèque admin (source avant Plex) |
| `./data/music_guest/<sid>` | `/data/music_guest` | Fichiers guest |
| `./data/temp` | `/data/temp` | Téléchargements temporaires admin |
| `./data/temp_guest/<sid>` | `/data/temp_guest` | Temporaires guest |
| `./logs` | `/app/logs` | Logs (activity.log) |
| `./python-server/templates` | `/app/templates` | Templates (live reload sans rebuild) |
| `/volume1/plex_media/music` | `/data/plex_music` | Destination Plex |

## API Routes principales

### Admin
| Méthode | Route | Description |
|---|---|---|
| POST | `/api/extract` | Extraire les métadonnées d'une URL |
| POST | `/api/download` | Ajouter une chanson à la queue |
| POST | `/api/download-playlist` | Ajouter une playlist à la queue |
| GET | `/api/status` | État de la queue admin |
| GET | `/api/stats` | Statistiques de la bibliothèque |
| GET | `/api/playlists` | Lister les dossiers playlist |
| POST | `/api/move-to-plex` | Déplacer la biblio normale vers Plex |
| POST | `/api/move-playlists-to-plex` | Déplacer les playlists vers Plex |
| POST | `/api/beets/scan` | Scanner la bibliothèque MusicBrainz |
| POST | `/api/beets/apply` | Appliquer les corrections de tags |
| GET | `/api/beets/status` | État du scan/apply Beets |

### Guest
| Méthode | Route | Description |
|---|---|---|
| POST | `/api/guest/extract` | Extraire les métadonnées |
| POST | `/api/guest/download` | Ajouter à la queue guest |
| GET | `/api/guest/status` | État de la queue guest |
| POST | `/api/guest/prepare-zip` | Créer le ZIP |
| GET | `/api/guest/download-zip` | Télécharger le ZIP |
| POST | `/api/guest/extend-session` | Prolonger la session d'1 heure |
