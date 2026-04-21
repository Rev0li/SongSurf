# 🎵 SongSurf — Audit & Roadmap v1.0 Stable

> **Date :** Avril 2026  
> **Auteur :** Senior Web Dev  
> **Périmètre :** Codebase complète avant passage en version stable publique

---

## Table des matières

1. [Vue d'ensemble de l'architecture](#1-vue-densemble-de-larchitecture)
2. [Ce qui fonctionne bien ✅](#2-ce-qui-fonctionne-bien-)
3. [Problèmes identifiés 🔴](#3-problèmes-identifiés-)
4. [Simplifications recommandées 🧹](#4-simplifications-recommandées-)
5. [Plan de migration Auth](#5-plan-de-migration-auth)
6. [Actions fichier par fichier](#6-actions-fichier-par-fichier)
7. [Priorités & checklist](#7-priorités--checklist)

---

## 1. Vue d'ensemble de l'architecture

```
Internet
   │
   ▼
[Watcher :8080]  ← toujours actif, auth + proxy
   │
   └── démarre à la demande ──▶ [SongSurf :8081]
                                      │
                                 ┌────┴────┐
                                 │ Admin   │  /data/music
                                 │ Guest   │  /data/music_guest/<sid>
                                 └─────────┘
```

**Stack :** Python 3.11 / Flask / yt-dlp / FFmpeg / Mutagen / Docker Compose  
**Déploiement cible :** NAS Synology + Tailscale + reverse proxy OVH/DuckDNS/caddy

---

## 2. Ce qui fonctionne bien ✅

| Composant | État | Note |
|---|---|---|
| Watcher (proxy + auth) | ✅ Solide | Brute-force, inactivité, token partagé |
| YouTubeDownloader | ✅ Solide | yt-dlp, progress hook, FFmpeg auto-detect |
| MusicOrganizer | ✅ Solide | Featuring detect, tags ID3, pochette JPEG |
| Queue admin (1 DL à la fois) | ✅ OK | threading.Queue, cancel_flag |
| Sessions Guest + cleanup | ✅ OK | TTL, ZIP, nettoyage différé |
| Validation URL YouTube | ✅ OK | Regex + domaine whitelist |
| Anti brute-force login | ✅ OK | 5 tentatives → blocage 15 min |
| Dockerfile non-root | ✅ OK | uid 1000, healthcheck |

---

## 3. Problèmes identifiés 🔴

### 3.1 🔴 CRITIQUE — Logique détection Single vs Playlist cassée

**Fichier :** `app.py` routes `/api/extract` et `/api/guest/extract`

**Problème actuel :**
```python
is_playlist = ('/playlist?list=' in url or '/browse/' in url) and '/watch?' not in url
```

Cette détection est fragile. YouTube Music colle souvent `&list=` après le `?v=` sur une chanson issue d'une playlist. La logique actuelle rate ces cas et peut traiter une chanson seule comme une playlist ou l'inverse.

**Règle métier correcte :**
- URL contient `/watch?v=` → **toujours une chanson seule** (1 song)
- URL contient `/playlist?list=` **sans** `/watch?` → **playlist/album**
- URL contient `/browse/` → **album**

**Fix recommandé dans `downloader.py` — `_normalize_url` :**
```python
def _detect_type(self, url: str) -> str:
    """Retourne 'song' ou 'playlist'."""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if 'v' in qs:
        return 'song'   # /watch?v= → toujours une chanson
    if 'list' in qs or '/browse/' in parsed.path:
        return 'playlist'
    return 'song'       # fallback safe
```

Et dans `app.py`, remplacer la détection inline par :
```python
is_playlist = downloader._detect_type(url) == 'playlist'
```

Appliquer **identiquement** dans les routes admin ET guest.

---

### 3.2 🔴 IMPORTANT — Bouton "Nettoyer les fichiers temporaires" exposé côté UI

**Fichier :** `dashboard.html`

Le bouton "Cleanup" (`/api/cleanup`) est actuellement dans le JS mais n'apparaît plus dans le HTML visible. **Vérifier qu'il n'est pas accessible** via une route non protégée. La route est bien `@login_required` côté serveur → OK pour la sécurité, mais le code JS mort doit être nettoyé.

**Action :** Supprimer la fonction `cleanup()` et tout appel dans le JS frontend. Garder la route `/api/cleanup` en interne si besoin de maintenance Docker.

---

### 3.3 🟡 MOYEN — Stats dashboard : onglet "Bibliothèque" 

**Fichier :** `dashboard.html`

**Action :** Supprimer la référence à l'onglet Métadonnées / Bibliothèque. Cette feature sera un module séparé plus tard.

---

### 3.4 🟡 MOYEN — `get_stats()` doit disparaître du périmètre

**Fichier :** `dashboard.html` + `organizer.py`

La méthode `get_stats()` n'apporte pas de valeur utile à la version actuelle. Elle entretient une divergence entre le backend et le dashboard, alors que la bibliothèque n'est pas encore un vrai module produit.

**Action :** supprimer `get_stats()` et retirer toute dépendance UI ou backend associée.

---

### 3.5 🟡 MOYEN — `SONGSURF_PASSWORD` vide en mode Watcher mais warning trompeur

**Fichier :** `app.py` ligne ~60

```python
if not DASHBOARD_PASSWORD:
    print("⚠️  SONGSURF_PASSWORD non défini ! Le dashboard admin sera non protégé.")
```

En mode Watcher (production), `SONGSURF_PASSWORD` est volontairement vide. Ce warning pollue les logs et peut induire en erreur.

**Fix :**
```python
if not WATCHER_SECRET and not DASHBOARD_PASSWORD:
    print("⚠️  Aucune auth configurée ! Dashboard non protégé.")
```

---

### 3.6 🟡 MOYEN — Pas de limite de taille sur les fichiers téléchargés

**Fichier :** `downloader.py`

Aucune vérification de la durée ou taille avant téléchargement. Un utilisateur peut lancer le téléchargement d'une vidéo de 10h.

**Fix recommandé :**
```python
MAX_DURATION_SECONDS = int(os.getenv('MAX_DURATION_SECONDS', '900'))  # 15 min
j'aimerai mettre 2h30 Max (pour pouvoir dl les mix dj).
ajouter un text a coter de "🔗 Coller un lien YouTube Music" pour informer l utilisateur
# Dans extract_metadata(), vérifier avant download :
if info.get('duration', 0) > MAX_DURATION_SECONDS:
    raise ValueError(f"Vidéo trop longue ({info['duration']}s > {MAX_DURATION_SECONDS}s max)")
```

---

### 3.7 🟢 MINEUR — `localStorage` utilisé dans `guest_dashboard.html`

```javascript
localStorage.setItem('songsurf_tuto_done', '1');
```

Fonctionne en navigateur standard, mais peut poser problème en navigation privée ou sur certains appareils. Acceptable pour un tuto onboarding, mais noter la dépendance.

---

## 4. Simplifications recommandées 🧹

### 4.1 Garder temporairement l'auth interne

Le système actuel gère deux niveaux d'auth :
- **Watcher** : gère la session Flask + mot de passe admin/guest
- **SongSurf** : a sa propre auth en mode standalone

**Décision pour cette version :**
ne rien supprimer maintenant. L'auth interne reste en place tant que les services d'auth externes ne sont pas prêts.

**Plan migration futur :**
1. Le docker Auth externe fournit un JWT ou cookie signé
2. Le Watcher valide ce token (plus de formulaire login dans Watcher)
3. `login.html`, les routes `/guest/login`, `/administrator`, `login_required` dans SongSurf → **supprimés**
4. SongSurf ne reçoit plus que des requêtes avec `X-Watcher-Token` valide

**Priorité actuelle :** stabiliser et simplifier l'existant, pas migrer l'auth.

---

### 4.2 Mettre la bibliothèque de côté

La bibliothèque / Beets n'est pas dans le périmètre de la version à venir. Il faut retirer les références visibles et éviter d'exposer une feature incomplète dans le dashboard.

| Fichier | Élément à supprimer |
|---|---|
| `dashboard.html` | Onglet / commentaire Bibliothèque ou Métadonnées |
| `dashboard.html` | Logique JS de tabs si elle ne sert plus |
| `app.py` | Toute référence fonctionnelle à la bibliothèque |

---

### 4.3 Nettoyer les fichiers temporaires — retirer le bouton, garder la logique

**Comportement voulu :**
- Suppression automatique des fichiers `temp/` après chaque téléchargement réussi (déjà fait dans `organizer.py` via `file_path.unlink()`)
- Nettoyage au démarrage du conteneur (déjà fait dans `entrypoint.sh` via `mkdir -p`)
- **Supprimer** toute référence UI au cleanup manuel

**Action dans `dashboard.html` :** Supprimer la fonction JS `cancelDownload` → garder uniquement l'annulation en cours. Supprimer `resetUI` appel cleanup.

---

### 4.4 Garder "Téléchargements récents", ajouter le bouton ZIP

La section "Téléchargements récents" existe déjà. Elle doit rester visible côté admin et guest, avec les musiques listées dans les deux vues. Le bouton ZIP doit être présent sur les deux tableaux de bord pour garder un comportement cohérent; la différence reste la cible du ZIP selon le contexte.

**À garder / afficher dans `dashboard.html` :**
```
✅ Téléchargements récents
─────────────────────────
🎵 The Weeknd - Blinding Lights    ✓  [album/Artist]
🎵 Louise Attaque - Amours         ✓  [album/Artist]

[📦 Télécharger mon ZIP]
```

**Logique côté serveur (`app.py`) :**
- Maintenir une liste `recent_downloads` (max 20 entrées) dans `download_status`
- Route `/api/download-zip` admin et guest → zipper la bonne cible selon la session
- Après le ZIP admin → **ne pas supprimer** la bibliothèque
- Après le ZIP guest → supprimer les fichiers uniquement en fin de session, pas immédiatement après le ZIP
- Plus tard, lever la limite de durée de session Guest
- Après 1 heure d'inactivité, afficher un message: "Etes-vous toujours là ? Le Docker va s'arrêter."
- Si aucune réaction après 15 minutes, forcer l'arrêt du Docker

---

### 4.5 Supprimer `get_stats()` dans `organizer.py`

La méthode ne doit plus être portée par la roadmap immédiate. On enlève la dette technique au lieu de la prolonger avec un affichage partiel.

**Action :** supprimer `get_stats()` et ne conserver que les helpers réellement utilisés par l'organisation des fichiers.
---

## 5. Plan de migration Auth

```
MAINTENANT (v1.0)           FUTUR (v2.0)
──────────────────          ──────────────────────────────
Watcher                     Docker Auth (externe)
  ├── login.html      ──▶     portail auth unifié
  ├── /administrator  ──▶     supprimé
  ├── /guest/login    ──▶     supprimé
  └── session Flask   ──▶     JWT validé par Watcher

SongSurf                    SongSurf
  ├── login_required  ──▶     garde uniquement X-Watcher-Token check
  ├── guest_required  ──▶     garde uniquement X-Watcher-Token check
  └── /login, /logout ──▶     supprimés
```

**Le Watcher reste** — il continue de :
- Vérifier le token JWT reçu du docker Auth
- Injecter `X-Watcher-Token`, `X-User-Role`, `X-Guest-Session-Id`
- Contrôler le cycle de vie du container SongSurf (start/stop/inactivité)
- Les dossier sessions seront garder pour chaque User. (avec chacun leurs logs)  

---

## 6. Actions fichier par fichier

### `downloader.py`
- [ ] Ajouter `_detect_type(url)` → remplacer la détection inline dans `app.py`
- [ ] Ajouter `MAX_DURATION_SECONDS` check dans `extract_metadata()`
- [ ] Rien d'autre à supprimer

### `organizer.py`
- [ ] Supprimer `get_stats()`

### `app.py`
- [ ] Corriger la détection `is_playlist` (admin + guest) → utiliser `downloader._detect_type()`
- [ ] Corriger le warning `SONGSURF_PASSWORD` (conditionner sur `WATCHER_SECRET`)
- [ ] Ajouter `recent_downloads` list dans `download_status` (max 20)
- [ ] Ajouter route `/api/download-zip` admin
- [ ] Supprimer les prints/logs redondants sur le mode Watcher

### `dashboard.html`
- [ ] Supprimer la référence à la bibliothèque / métadonnées
- [ ] Supprimer la fonction JS `cleanup()`
- [ ] Garder la section "Téléchargements récents"
- [ ] Ajouter le bouton ZIP admin et le garder aussi côté guest
- [ ] Simplifier les tabs si elles ne servent plus

### `guest_dashboard.html`
- [ ] Aucune modification structurelle — logique ZIP déjà correcte
- [ ] Vérifier que `localStorage` tuto ne bloque rien en mode privé

### `login.html`
- [ ] Aucune modification — sera supprimé lors de la migration Auth

### `watcher.py`
- [ ] Ajouter la configuration d'inactivité: avertissement après 1h, arrêt forcé après 15 min sans réaction
- [ ] Aucune autre modification — architecture solide

### `docker-compose.yml`
- [ ] Aucune modification — configuration correcte

### `entrypoint.sh`
- [ ] Aucune modification

---

## 7. Roadmap en 3 phases

### Phase 1 — Stabilisation v1.0

- [ ] Fix détection song vs playlist (`_detect_type`) dans `downloader.py` + `app.py` (admin + guest)
- [ ] Supprimer le code mort : bibliothèque, fonction cleanup() UI, `get_stats()`
- [ ] Corriger le warning `SONGSURF_PASSWORD` en mode Watcher
- [ ] Ajouter `MAX_DURATION_SECONDS` dans le downloader
- [ ] Garder le dashboard simple, sans onglet Bibliothèque

### Phase 2 — Finition produit

- [ ] Ajouter le bouton ZIP admin dans `dashboard.html` + route backend
- [ ] Finaliser la section "Téléchargements récents" sur admin et guest
- [ ] Garder le ZIP Guest lié à la fin de session
- [ ] Ajouter l'avertissement d'inactivité après 1 heure
- [ ] Forcer l'arrêt du Docker après 15 minutes sans réaction
- [ ] Ajouter la configuration Watcher pour que le timer n'arrête pas le Docker au bout d'une heure, mais déclenche d'abord un avertissement puis un arrêt différé

### Phase 3 — Évolution future

- [ ] Garder la migration Auth externe pour plus tard : docker Auth → Watcher → SongSurf
- [ ] Lever la limite de durée des sessions Guest
- [ ] Repenser la bibliothèque comme module séparé si le besoin revient
- [ ] Ajouter le rate limiting sur `/api/extract` pour éviter l'abus de l'API yt-dlp

---

## Résumé exécutif

Le projet est **globalement sain** pour une v1.0. L'architecture Watcher + SongSurf est bien pensée et la séparation des responsabilités est claire.

**Le seul bug bloquant** est la détection song/playlist qui utilise une heuristique fragile sur l'URL. Ce bug peut faire télécharger une playlist entière au lieu d'une chanson ou l'inverse — il doit être corrigé avant le release stable.

Les autres points sont soit du nettoyage cosmétique, soit des features manquantes déjà identifiées dans la roadmap. Le code guest (session, quota, ZIP, cleanup) est particulièrement bien implémenté.
