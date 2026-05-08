# SongSurf — Fonctionnalités futures

## Auto-suggestions de métadonnées

Enrichir automatiquement les tags ID3 (artiste, album, année, genre, ISRC…)
en interrogeant des bases de données musicales open-source.

### Projets / APIs à évaluer

| Projet | Ce qu'il apporte | Langage client |
|---|---|---|
| **MusicBrainz** | Base open-source la plus complète. Artiste, album, date, label, ISRC, type de release. | `python-musicbrainzngs` |
| **AcoustID + Chromaprint** | Fingerprinting audio → identifier un morceau sans métadonnées. | `pyacoustid` + `fpcalc` |
| **Beets** | Outil de gestion de biblio qui auto-tag via MusicBrainz/AcoustID. Peut servir de backend. | CLI Python (intégrable) |
| **Last.fm API** | Tags communautaires, genres, artistes similaires, pochettes. | `pylast` |
| **Discogs API** | Discographie complète, numéro de catalogue, labels, variantes de releases. | `discogs_client` |
| **ListenBrainz** | Statistiques d'écoute, recommandations open-source. | REST API |

### Flux envisagé

1. L'utilisateur lance un "scan suggestions" sur un album ou une chanson.
2. SongSurf calcule l'empreinte audio (AcoustID/Chromaprint) si disponible,
   sinon cherche par titre + artiste dans MusicBrainz.
3. Les suggestions sont affichées dans un panneau dans l'onglet Métadonnées
   (champ par champ, avec score de confiance).
4. L'utilisateur accepte/rejette chaque suggestion avant sauvegarde.

### Contraintes

- Toutes les APIs ont des rate-limits — mettre en cache les réponses.
- AcoustID nécessite `fpcalc` (binaire Chromaprint) dans le container.
- MusicBrainz demande un User-Agent personnalisé dans les headers.
- Les données MusicBrainz sont sous licence CC0 (libre de droits).

### Priorité suggérée

1. MusicBrainz par titre/artiste (pas besoin d'audio) — rapide à implémenter
2. AcoustID fingerprinting — identification robuste pour les albums sans tags
3. Pochettes via Cover Art Archive (lié à MusicBrainz, CC0)
