# Carte fonctionnelle du frontend

> État au 2026-11-02, après SSF-13 (#27) : interface mobile first façon appli de musique.
> Historique : SSF-05 avait découpé l'ancienne page `/metadata` (2 194 lignes) et migré vers Svelte 5 ;
> SSF-13 remplace cette page et la page Téléchargement par deux onglets « Ajouter » et « Ma musique ».

Stack : Svelte 5.57 (runes), SvelteKit 2.70, Vite 5.4, adapter-static, Node 22 (image Docker). `npm run check` = `svelte-check` (0 erreur, 0 avertissement attendus).

## Principes (décisions SSF-13)

- L'interface suit le parcours de l'utilisateur : **Ajouter → Ma musique → Récupérer**, plus les dossiers.
- **2 onglets** en bas sur mobile (en haut sur ordinateur, ≥ 900 px) : « Ajouter » (`/`) et « Ma musique » (`/library`).
- Navigation **en pile** dans Ma musique : accueil → artiste (`?artist=`) → album (`?album=`), bouton Retour. Plus de colonne latérale ni de glisser-déposer : « Déplacer vers… ».
- Les actions s'ouvrent dans des **panneaux du bas** ; le bouton Retour du téléphone ferme le panneau (entrée d'historique « peu profonde », `lib/ui/sheets.js`).
- **Mode expert = admin uniquement** (aussi bloqué côté serveur, 403 `admin_only`) : numérotation des pistes, audit iTunes, genre de l'artiste, suppression, tous les champs ID3 / TXXX / détails du fichier.
- Toute modification qui touche plusieurs fichiers passe par une **fenêtre qui explique le changement** (avant → après, De → Vers).
- Genres proposés **en anglais** (comme Jellyfin et les genres iTunes) : sélecteur en cascade, 22 styles + précision facultative (`lib/library/genres.js`).
- Photos d'artiste : ajout manuel uniquement (pas de recherche automatique).

## Arborescence

| Zone | Fichiers |
|---|---|
| Coque | `routes/+layout.svelte` (polling `/api/status` 1,5 s, rafraîchit Ma musique quand un titre se termine), `components/shell/{TopBar,TabBar,MiniBar}.svelte`, `Toast`, `ConfirmModal`, `components/sheets/SheetHost.svelte` |
| Ajouter `/` | `routes/+page.svelte`, `components/add/{AddForm,DownloadList}.svelte`, `lib/downloads.js` |
| Ma musique `/library` | `routes/library/+page.svelte`, `components/library/{LibraryHome,ArtistView,CoverFlow,AlbumView,TrackRow}.svelte`, `lib/library/{data,actions,genres}.js` |
| Panneaux | `components/sheets/` : `Account`, `Menu` (« ⋯ »), `TrackEdit`, `AlbumEdit`, `Move`, `FillWizard` (« À remplir »), `Recover` (ZIP), `Tool` (outils experts) |
| Briques d'interface | `components/ui/{Icon,Cover,Sheet,GenrePicker}.svelte` |
| Outils experts (inchangés depuis SSF-05) | `components/metadata/{ArtistAudit,AlbumReorder,ArtistGenre,SongDetails}.svelte` + `lib/styles/metadata.css` (préfixe `.meta-layout`) + `lib/metadata/id3.js` |
| Styles | `lib/styles/design-system.css` (jetons), `components.css`, `layouts.css`, `app.css` (coque, listes, grilles, panneaux) |
| Ancienne adresse | `routes/metadata/+page.svelte` → redirige vers `/library` |

## 1. Coque

| Élément | Rôle |
|---|---|
| Barre du haut | « ‹ Mon espace » (`/logout` : retour au portail, les téléchargements continuent), logo, rond du compte (thème, retour au portail) ; porte les onglets sur ordinateur |
| Onglets du bas | Ajouter / Ma musique ; « Ma musique » touché depuis une sous-page ramène à l'accueil |
| Mini-barre | L'ajout en cours : un album = « Titre 4 sur 12 » + sa barre (ne recule jamais), « +N ajouts » s'il y en a d'autres ; ou « en attente, ton tour dans N titres » ; visible partout sauf sur Ajouter ; un appui ouvre Ajouter |
| Toasts, fenêtre de confirmation | Inchangés (l'avertissement d'inactivité a disparu avec le Watcher, SSF-16) |
| Webapp (écran d'accueil) | `static/manifest.json` (plein écran, `start_url` `/`) chargé avec `crossorigin="use-credentials"` (sinon Caddy refuse sans cookie du portail), icônes `icon-192/512.png`, `icon-maskable-512.png`, `apple-touch-icon.png`, `favicon.svg` ; balises `apple-mobile-web-app-*` dans `src/app.html`. Icônes PNG redessinées depuis le favicon (fond rose plein, note noire) |

## 2. Ajouter `/`

| Élément | API |
|---|---|
| Champ du lien : collage natif (appui long → Coller) ou Entrée → analyse automatique | `extract` |
| Bouton « Coller le lien copié » : lit le presse-papiers (autorisation demandée la 1re fois) ; refus → explique l'appui long | — |
| Fiche : pochette, titre / album, artiste, année ; « Corriger les infos avant d'ajouter » replié (titre, artiste, album, année) ; aperçu des titres d'un album | — |
| Ajouter | `download`, `download-playlist` |
| Ajouts restants aujourd'hui (membres) | `status` (`daily_count`, `daily_limit`) |
| « En cours » : une ligne par ajout — un album = une seule ligne « 3 / 12 titres » avec le titre en cours et une barre qui avance titre après titre (estimation au temps du serveur, transition linéaire de 1,4 s ≈ intervalle du polling) —, échecs regroupés par album (Réessayer / Tout réessayer avec l'URL renvoyée par le serveur, Retirer), terminés de la session regroupés par album, affichés une fois l'album fini (Voir → page de l'album), « Effacer les terminés » | `status` (`jobs`, `current_percent`, `current_download`, `pending`, `last_completed`, `last_error.url`) ; historique gardé en `sessionStorage` (`ssf.dl.history`) |
| « Comment faire ? » quand rien n'est en cours | — |

## 3. Ma musique `/library`

### 3.1 Accueil
| Élément | API |
|---|---|
| Recherche permissive (accents, casse, ponctuation, ordre des mots : « angele » trouve Angèle ; un album se trouve aussi par son artiste, un titre par son artiste ou son album, `matcher()` dans `lib/utils.js`) ; Artistes / Albums / Titres (titres affichés par 200) | `library` (arbre mis en cache dans `ssf.lib.tree`) |
| « À remplir » : albums aux infos manquantes (année, n° de piste, genre) → assistant | `todo` |
| « Récupérer ma musique » (membres) → panneau en 3 étapes (préparer, télécharger, bibliothèque vidée seulement si le fichier est complet) | `prepare-zip`, `zip-status`, `download-zip` |

### 3.2 Artiste / album
| Élément | API |
|---|---|
| Albums de l'artiste en **Cover Flow** façon iPod (par défaut : pochette de face, deux piles inclinées, reflets sur fond noir) ou en grille : bouton à droite de « Albums » (dès 2 albums), choix mémorisé dans `ssf.artist.view`. Bascule animée (`lib/ui/coverMorph.js`) : les pochettes s'envolent en se dispersant puis se posent dans l'autre affichage (côté Cover Flow, dans sa vraie perspective 3D), le fond noir s'évapore ou se condense ; ~1 s, désactivée si « réduire les animations ». Ouvrir un album (pochette de face du Cover Flow, grille artiste ou grille Albums de l'accueil) : la pochette s'envole et se pose à sa place en haut de la page album, le reste de la page entre en cascade ; en repartant (bouton retour, lien artiste, retour du navigateur), elle revient se poser dans le Cover Flow / la grille (`lib/ui/albumZoom.js` : `zoomFrom` avant la navigation, `land()` dans l'`afterNavigate` de `routes/library/+page.svelte` ; la cible `[data-zoom-hero]` / `[data-morph] .cover` est relue à chaque image, la copie suit les changements de défilement). Mouvement « surf » libre (moteur maison, pas de défilement natif) : glisser au doigt / à la souris avec élan, molette et pavé tactile continus (la molette verticale rend la main à la page aux extrémités) ; aucun aimant pendant le mouvement, la pochette la plus visible ne se recentre qu'après 2,5 s sans geste ; toucher la pochette de face ouvre l'album, une autre la ramène au centre ; flèches au clavier ; au retour d'un album, reprise sur le même | — |
| Photo d'artiste, pochette d'album (affichage, changement, Ctrl+V) | `artist-picture`, `folder-cover`, `artist-cover/upload`, `album-cover/upload` |
| Liste des titres triée par n° réel, ⚠ si année ou n° manquant | `album-tracks` (titre, n°, artistes, année, genres) |
| « Modifier l'album » : nom (tags **et** dossier), année, genre sur tous les titres, fenêtre avant → après | `album-tags/save` |
| « À remplir » sur un album incomplet | `album-tracks`, `album-tags/save`, `song-meta/save` |
| Menus « ⋯ » : Modifier, Changer la pochette / photo, Déplacer vers… ; admin : Numéroter les pistes, Vérifier avec iTunes, Genre de l'artiste, Supprimer | `move`, `move-folder`, `renumber-album`, `audit/*`, `set-artist-genre`, `delete-song`, `delete-folder` |

### 3.3 Panneaux
| Panneau | Contenu |
|---|---|
| Modifier les infos | Membre : titre, artiste(s), année, n° de piste (n sur total), genre (cascade) ; l'album s'affiche avec « Déplacer vers… » (changer le tag seul séparerait dossier et Jellyfin). Admin : codes ID3, « Mode expert » (artiste de l'album, disque, compositeur…, TXXX, fichier, pochette par titre) |
| Déplacer vers… | Titre : artiste puis album ; album : artiste. Fenêtre De → Vers ; le serveur met TALB + TPE2 au dossier cible et ne remplace que l'artiste principal dans TPE1 (featurings gardés) |
| À remplir | Album par album, seules les infos manquantes ; année et genre écrits sur tout l'album, numéros libres proposés ; genre suggéré depuis les autres albums de l'artiste ; Passer / Enregistrer ; bilan final |

## 4. Routes utilisées par le frontend

`me`, `status`, `extract`, `download`, `download-playlist`, `prepare-zip`, `zip-status`, `download-zip`, `library`, `library/todo`, `library/move`, `move-folder`, `delete-folder`, `delete-song`, `folder-cover`, `artist-picture`, `song-meta`, `song-meta/save`, `song-cover/upload`, `album-cover/upload`, `artist-cover/upload`, `album-tracks`, `album-status` (suggestion de genre, outil genre), `album-tags/save`, `renumber-album`, `set-artist-genre`, `audit/artist`, `audit/apply`.
Extension : `cookies/update`, `preview`, `queue-direct`. rev0auth : `admin/dl-logs`.
