# Carte fonctionnelle du frontend — SSF-05, étape 0

> État au 2026-10-26 (branche `feat/ssf-05`). Sert de base au découpage du frontend (SSF-05) puis au refactor backend (SSF-04) : ce que l'interface utilise vraiment dit quelles routes garder.
>
> Légende : ✅ essentiel · 🟡 secondaire (gardé, candidat à simplifier ou à mettre en retrait) · 🔁 doublon · 💀 mort (à supprimer)
> **Les 🔁 et 💀 ne sont supprimés qu'après validation.**

## Vue d'ensemble

| Zone | Fichier(s) | Lignes |
|---|---|---|
| Page Téléchargement `/` | `routes/+page.svelte` + 6 composants | ~1 400 |
| Page Métadonnées `/metadata` | `routes/metadata/+page.svelte` (script 768 · balisage 755 · style 670) | **2 194** |
| Coquille (tous écrans) | `routes/+layout.svelte`, `Header`, `Toast`, `ConfirmModal`, `HelpModal`, `WatcherInactivity` | ~630 |
| Partagé | `lib/api.js`, `lib/stores.js`, `lib/utils.js` | ~300 |
| Styles globaux | `lib/styles/*.css` | ~580 |

Stack : Svelte 4.2, SvelteKit 2.9, Vite 5.4, adapter-static.

---

## 1. Coquille (présente sur les deux pages)

| Élément | Rôle | Statut |
|---|---|---|
| `+layout.svelte` — polling `/api/status` toutes les 1,5 s | Alimente progression, file, toasts de fin/erreur | ✅ |
| `Header` — « ← Mon espace », logo, pseudo, onglets Téléchargement / Métadonnées | Navigation | ✅ |
| `Header` — bascule clair/sombre | Confort | 🟡 |
| `Header` — bouton « ? » → `HelpModal` (tutoriel, 2 catégories × 3 étapes, ouvert seul à la 1re visite) | Aide | 🟡 |
| `Toast` | Retours d'action | ✅ |
| `ConfirmModal` (`confirmAction()`) | Confirmations destructives (ZIP, suppression) | ✅ |
| `WatcherInactivity` — avertissement avant mise en veille + « Je suis là » (`/watcher/inactivity-status`, `/watcher/keepalive`) | Évite une coupure pendant l'usage | ✅ |

## 2. Page Téléchargement `/`

| Élément | Rôle | Statut |
|---|---|---|
| `DownloadPanel` — champ URL + « Analyser » (`/api/extract`) | Point d'entrée principal | ✅ |
| `DownloadPanel` — édition titre/artiste/album (ou artiste/album/année + liste des titres) puis « Ajouter à la file » | Corriger avant de télécharger | ✅ |
| `ProgressZone` — barre de progression, titre en cours, « worker occupé par… » | Suivi | ✅ |
| `UpcomingQueue` — titres **en attente côté serveur** (les miens), groupés par album | Suivi de la vraie file | ✅ |
| `UrlQueue` — file **côté navigateur** : envoie chaque élément (`/api/download`, `/api/download-playlist`) puis affiche En attente / Envoi / Téléchargement / Terminé / Erreur | Depuis que le serveur possède la file (SSF-03), elle **double** `UpcomingQueue` : deux listes « file d'attente » à l'écran. Son seul rôle propre est d'afficher l'**erreur d'envoi** (cookies manquants, quota, file pleine) | 🔁 à fusionner avec `UpcomingQueue` : l'ajout envoie directement, l'erreur passe en toast |
| `LibraryTree` — bouton **ZIP** (membres) avec avancement | Seul endroit pour exporter sa bibliothèque | ✅ |
| `LibraryTree` — arborescence artistes/albums/titres, filtre, glisser-déposer titre → album et album → artiste | Même fonction que la colonne gauche de `/metadata`, en moins complet | 🔁 à retirer de l'accueil (lien « Voir ma bibliothèque » vers `/metadata`) ; le bouton ZIP reste |

## 3. Page Métadonnées `/metadata`

### 3.1 Navigation
| Élément | Statut |
|---|---|
| Colonne gauche : arbre artistes → albums → titres, filtre, repliable (rail) | ✅ |
| Glisser-déposer titre → album, album → artiste (`move`, `move-folder`) | ✅ (ranger, c'est le cœur de la page) |
| Persistance localStorage `ssf.meta.*` (arbre ouvert, colonne repliée, sélection, défilement) | ✅ |
| Accueil : galerie des artistes (photos) | ✅ |
| Fil d'Ariane 🏠 › artiste › album | ✅ |
| Titre précédent / suivant dans l'album (flèches + clavier) | ✅ |
| Playlists « à plat » (dossiers sans album, héritage) dans l'arbre | 🟡 mode retiré en 2026-06, ne sert que pour d'anciens dossiers |

### 3.2 Panneau artiste
| Élément | API | Statut |
|---|---|---|
| Photo d'artiste (affichage + envoi, collage) | `artist-picture`, `artist-cover/upload` | 🟡 |
| Grille des albums + badges de complétude (genre, année, n° de piste manquants) | `album-status` | ✅ |
| Genre de l'artiste appliqué à tous ses albums | `set-artist-genre` | 🟡 |
| Audit iTunes (recommandations cochables puis appliquer) | `audit/artist`, `audit/apply` | 🟡 puissant mais avancé : à mettre en retrait (« Outils ») |
| Supprimer l'artiste — **admin** | `delete-folder` | ✅ (admin) |

### 3.3 Panneau album
| Élément | API | Statut |
|---|---|---|
| Pochette (affichage + envoi) | `folder-cover`, `album-cover/upload` | ✅ |
| Liste des pistes triée par n° réel (TRCK) | `album-tracks` | ✅ |
| « 🔢 Numéroter les pistes » (glisser-déposer puis enregistrer) | `renumber-album` | 🟡 |
| Supprimer l'album — **admin** | `delete-folder` | ✅ (admin) |

### 3.4 Panneau titre
| Élément | API | Statut |
|---|---|---|
| Édition des tags principaux (titre, artiste, album, année, n°, genre…) + Enregistrer | `song-meta`, `song-meta/save` | ✅ |
| Alerte « champs manquants pour Jellyfin » | — | ✅ |
| Champs secondaires (repliés) | `song-meta/save` | 🟡 |
| « Appliquer ce champ à tout l'album » | `song-meta/save` × N | 🟡 utile, à garder discret |
| Bloc « Fichier » (chemin, taille) en lecture seule | — | 🟡 |
| Tags TXXX (MusicBrainz, ReplayGain…) en lecture seule | — | 🟡 technique |
| « Plus de détails » : audio (débit, mode, encodeur) | — | 🟡 technique |
| Pochette du titre (aperçu + envoi, collage) | `song-cover/upload` | 🟡 doublon partiel de la pochette d'album |

---

## 4. Code mort (💀)

| Élément | Où |
|---|---|
| `extractYouTubeVideoId`, `resolveCoverCandidates`, `bustUrl` (appelées nulle part) | `lib/utils.js` |
| 22 classes CSS globales jamais utilisées : `badge-primary btn-brand empty-state empty-state-icon header-nav progress-subtext progress-text toggle-row toggle-slider toggle-switch` · `dl-count dl-folder-icon dl-item folder-actions main-grid option-card option-toggle-row selected-folder side-column toggle-description` · `container` | `lib/styles/{components,dashboard,layouts}.css` |
| Champ `thumbnail_candidates` lu par personne côté front (cf. `resolveCoverCandidates`) | réponse de `/api/extract` |

---

## 5. Conséquences pour le backend (SSF-04)

32 routes `/api` dans `server/app.py`.

| Appelant | Routes |
|---|---|
| **Frontend** | `me`, `status`, `extract`, `download`, `download-playlist`, `prepare-zip`, `zip-status`, `download-zip`, `library`, `library/move`, `move-folder`, `delete-folder`, `folder-cover`, `artist-picture`, `song-meta`, `song-meta/save`, `song-cover/upload`, `album-cover/upload`, `artist-cover/upload`, `album-tracks`, `album-status`, `renumber-album`, `set-artist-genre`, `audit/artist`, `audit/apply` |
| **Extension** | `cookies/update`, `preview`, `queue-direct` (+ `/watcher/loading`) |
| **rev0auth** (côté serveur) | `admin/dl-logs` (pages admin « SongSurf logs / activité ») |
| **curl / automatisation** (gardé exprès) | `admin/genre-backfill`, `admin/genre-backfill/status` |
| **Personne** 💀 | `admin/extract-covers` |

Découpage naturel du backend qui en découle : **téléchargement** (extract, download*, queue-direct, preview, status) · **bibliothèque** (library, move*, delete-folder, images) · **métadonnées** (song-meta*, album-*, renumber, set-artist-genre, audit*) · **export** (ZIP) · **compte** (me, cookies) · **admin** (dl-logs, genre-backfill).

---

## 6. Propositions à valider avant le découpage

1. 💀 Supprimer le code mort de la section 4 (et la route `admin/extract-covers` côté backend, dans SSF-04).
2. 🔁 Fusionner `UrlQueue` dans `UpcomingQueue` : une seule « file d'attente », celle du serveur ; une erreur d'envoi devient un toast.
3. 🔁 Retirer l'arborescence de la page d'accueil (garder le bouton ZIP et un lien vers `/metadata`).
4. 🟡 Rien d'autre n'est supprimé : les éléments secondaires restent, leur mise en retrait relève de la refonte visuelle (SSF-07).
