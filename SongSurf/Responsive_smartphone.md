# Responsive Smartphone — SongSurf

Scope : frontend SvelteKit (`frontend/src/`) + watcher templates (`watcher/templates/`)
Priorité : future — à planifier en coordination avec le doc rev0auth

---

## État actuel des breakpoints

Des media queries existent déjà mais elles sont partielles :

| Fichier | Breakpoint | Ce qui est couvert |
|---|---|---|
| `layouts.css` | `max-width: 900px` | `.url-group` passe en 1 colonne (input + bouton empilés) |
| `dashboard.css` | `max-width: 1100px` | `.metadata-layout` passe en 1 colonne |
| `dashboard.css` | `max-width: 900px` | `.main-grid` passe en 1 colonne (ProgressZone + Library empilés) |
| `DownloadPanel.svelte` | `max-width: 900px` | `.metadata-layout` interne passe en 1 colonne |

Tout le reste est desktop-only. Aucune couverture sous 480px.

---

## Breakpoints cibles (à unifier avec rev0auth)

| Nom  | Largeur       | Usage                      |
|------|---------------|----------------------------|
| `sm` | < 480 px      | Téléphone portrait          |
| `md` | 480 – 768 px  | Téléphone paysage / tablette |
| `lg` | > 768 px      | Desktop (état actuel)      |

---

## Points de douleur identifiés

### 1. Header — `components.css` + `+layout.svelte`
**Problème** : `.header-nav` contient badge email + 3 liens + toggle thème + déconnexion.
Sur `sm` ça déborde horizontalement sans wrap.

```
.header { justify-content: space-between; padding: s3 s6; }
.header-nav { display: flex; gap: s3; }  ← pas de flex-wrap
```

**À faire** :
- [ ] Sous `sm` : masquer le badge email ou le tronquer (`max-width` + ellipsis)
- [ ] Sous `sm` : regrouper les liens secondaires (Métadonnées, Soutenir, Déconnexion) dans un menu hamburger, ou les passer en 2 lignes avec `flex-wrap`
- [ ] Garder toujours visible : logo + toggle thème

---

### 2. Inputs — `font-size: 15px` → risque de zoom iOS
**Problème** : `.form-input { font-size: 15px }` dans `components.css`.
iOS Safari zoome automatiquement sur tout input < 16px.

**À faire** :
- [ ] Passer `.form-input { font-size: 16px }` (ou `max(16px, 15px)` via `clamp`)

---

### 3. Touch targets trop petits
**Problème** : `.btn-sm { padding: 6px 12px; font-size: 13px }` — zone tactile ~32px de haut.
Minimum recommandé : 44px (Apple HIG / Google Material).

**À faire** :
- [ ] Sous `sm` : `.btn-sm { padding: 10px 14px }` ou surcharger en `min-height: 44px`
- [ ] Vérifier aussi les boutons d'action de la library (`.folder-actions`) : 2px 4px de padding — invisible sur mobile

---

### 4. Dashboard — `DownloadPanel.svelte`
**Ce qui marche** : le `url-group` (input + bouton Analyser) empile déjà à 900px ✓

**Problèmes restants** :
- [ ] Panneau métadonnées : `metadata-layout` empile à 900px ✓ mais `compact-row` (Artiste / Album côte à côte) n'empile qu'à 1100px — sur `sm` ils sont serrés
- [ ] Boutons `.metadata-actions` : "Ajouter à la file" + "Annuler" — vérifier qu'ils sont bien `btn-block` sur `sm`
- [ ] Cover preview : se retrouve après les champs quand `metadata-layout` empile — logiquement elle devrait passer au-dessus

---

### 5. Dashboard — `LibraryTree.svelte`
**Problèmes** :
- [ ] `.lib-name { max-width: 200px }` et `.lib-song-name { max-width: 220px }` — valeur fixe. Sur `sm` la colonne est plus étroite, les noms seront tronqués très tôt. Passer en `max-width: 50vw` ou `min-width: 0; flex: 1` + `overflow: hidden`
- [ ] `.song-item` affiche nom + hint "glisser" + bouton — sur mobile le drag-and-drop n'existe pas, le hint est inutile. Masquer `.lib-drag-hint` sur `sm`
- [ ] `max-height: 560px` sur `.library-tree` — sur mobile la hauteur doit être plus courte ou défilante dans la page

---

### 6. Notification de téléchargement terminé — `+page.svelte`
```css
.dl-notif { position: fixed; bottom: 24px; right: 24px; max-width: 300px; min-width: 200px; }
```
**Problème** : sur `sm` (< 360px de large), `min-width: 200px` + `right: 24px` = déborde à gauche.

**À faire** :
- [ ] Sous `sm` : `right: 12px; left: 12px; max-width: none; min-width: unset`

---

### 7. Page `/donation` — `donation/+page.svelte`
Plus un probleme car supprimer

---

### 8. Page `/metadata` — `metadata/+page.svelte`
(Page la plus complexe — full audit à faire lors de la lecture)

**Patterns à risque visibles sans lecture complète** :
- [ ] Layout 2 colonnes (arbre bibliothèque à gauche / panneau d'édition à droite) — aucun breakpoint pour ça actuellement
- [ ] Drag-and-drop entre albums/artistes — non applicable sur mobile → à désactiver ou remplacer par boutons
- [ ] Formulaires d'édition de métadonnées : vérifier longueur des inputs sur `sm`

---

### 9. Watcher — `loading.html` / `unavailable.html`
**État actuel** : `loading.html` a `viewport` meta ✓ et layout centré flex ✓ — fonctionnel sur mobile.
Peu de CSS, peu de risque.

**À faire** :
- [ ] Vérifier `unavailable.html` (non lu) — même pattern ?
- [ ] `h1 { font-size: 22px }` — OK sur mobile

---

## Règles générales (identiques rev0auth)

- Zones tactiles : min `44 × 44 px`
- Pas de `hover`-only UX
- `font-size: 16px` minimum sur tous les `input`, `textarea`, `select` pour éviter le zoom iOS
- Éviter `overflow: hidden` sur `body` sauf modales
- Préférer `min-height` à `height` fixe

---

## Ordre de priorité suggéré

1. `font-size: 16px` sur les inputs — 5 min, bloquant iOS
2. Header nav — visible sur toutes les pages, impact fort
3. Touch targets `.btn-sm` et `.folder-actions`
4. `.dl-notif` overflow sur très petits écrans
5. Dashboard principal (DownloadPanel, Library) — usage quotidien
6. Page `/donation`
7. Page `/metadata` — plus complexe, audit complet requis

---

## Notes techniques

- Le CSS est organisé en 4 fichiers globaux (`design-system`, `components`, `layouts`, `dashboard`) + styles scoped dans chaque `.svelte`. Les media queries peuvent aller dans les fichiers globaux OU dans le `<style>` du composant — à décider lors de la refonte.
- Pas de framework CSS (Tailwind etc.) — tout est vanilla, on reste dans cette logique.
- Le thème dark/light est géré via `html.dark` class — les media queries `prefers-color-scheme` ne sont pas utilisées. À garder en tête si on ajoute du CSS responsive.
