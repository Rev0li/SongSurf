# SongSurf — Notes de version

## Intégration rev0auth : dossiers music par utilisateur

SongSurf s'intègre maintenant avec **rev0auth** pour isoler la bibliothèque de chaque membre.

### Comment ça marche

Quand rev0auth accorde l'accès SongSurf à un utilisateur, un token JWT signé est transmis au Watcher. Le Watcher valide ce token et transmet le `pseudo` à SongSurf via l'en-tête `X-Watcher-Token`.

SongSurf utilise le `pseudo` pour ranger les téléchargements dans un sous-dossier dédié :

```
/data/music/
  ├─ revoli/
  │    └─ Artist/Album/Title.mp3
  ├─ alice/
  │    └─ Artist/Album/Title.mp3
  └─ bob/
       └─ Artist/Album/Title.mp3
```

### Ce qui persiste à travers les déploiements

| Données | Stocké où | Survit aux mises à jour |
|---|---|---|
| Bibliothèque music | Volume Docker `/data/music` | ✅ Oui |
| Sessions guest | Volume Docker `/data/music_guest` | ✅ Oui |
| Comptes utilisateurs | PostgreSQL (`web_users`) | ✅ Oui |
| Messages / wall | PostgreSQL (`web_messages`, `web_wall_posts`) | ✅ Oui |
| Permissions d'accès | PostgreSQL (`web_users.access_songsurf`) | ✅ Oui |

Les volumes Docker et la base PostgreSQL ne sont **jamais touchés** lors d'un `docker compose up --no-deps --build api web`. Seuls les conteneurs `api` et `web` sont recréés — les données restent intactes.

### Flux d'accès

```
Utilisateur rev0auth
  └─ Demande accès SongSurf (star + follow GitHub)
       └─ Admin approuve → access_songsurf = true
            └─ rev0auth génère un JWT avec { pseudo, role: "member" }
                 └─ Watcher valide → SongSurf isole dans /data/music/<pseudo>/
```

### Mode guest (sans compte)

Sans compte rev0auth, l'utilisateur accède en mode **guest** :
- Quota limité (`GUEST_MAX_SONGS`)
- Session temporaire (TTL `GUEST_SESSION_TTL`, défaut 3600 s)
- Fichiers regroupés dans `/data/music_guest/<session_id>/`
- Export ZIP automatique à la fin de la session

### Éditeur de métadonnées

Les fichiers téléchargés sont des MP3 avec tags ID3 écrits par Mutagen (`Artist/Album/Title`).
Si les tags sont incomplets ou incorrects, recommande :

- **beets** — correction automatique via MusicBrainz
- **MusicBrainz Picard** — correction manuelle assistée (GUI)
- **Mp3tag** — éditeur simple par lot (Windows/Wine)

---

## Déploiement CI/CD

Le workflow GitHub Actions (`deploy.yml`) reconstruit uniquement les conteneurs `api` et `web` :

```bash
docker compose up -d --no-deps --build --force-recreate api web
```

La base PostgreSQL reste active — aucune donnée perdue entre deux déploiements.
