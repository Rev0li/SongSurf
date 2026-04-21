# 🎵 SongSurf — Architecture Frontend V2

## 📋 Vue d'ensemble

Architecture CSS/JS modulaire préparée pour la migration Rust (Axum + Tera).  
Remplace le système actuel (CSS inline, 70% de duplication) par une architecture maintenable et scalable.

---

## 🏗️ Principes de design

### 1. Design System Token-Based
Toutes les valeurs de design (couleurs, espacements, typographie) sont centralisées dans des variables CSS.

```css
/* Avant */
button { color: rgba(255,255,255,0.85); padding: 14px 24px; }

/* Après */
button { color: var(--color-text-secondary); padding: var(--space-3) var(--space-6); }
```

**Avantages :**
- Changement de thème en 1 seul endroit
- Cohérence visuelle garantie
- Mode sombre/clair facile à implémenter

### 2. Composants Atomiques
Chaque élément UI est un composant réutilisable indépendant.

```html
<!-- Un bouton = 1 classe -->
<button class="btn btn-primary">Action</button>

<!-- Une card = 1 classe -->
<div class="card">...</div>

<!-- Un input = 1 classe -->
<input class="form-input" type="text">
```

### 3. Séparation des Responsabilités

```
HTML  → Structure sémantique uniquement
CSS   → Apparence et layout
JS    → Interactions et logique métier
```

### 4. Mobile-First Responsive

Tous les composants sont responsive par défaut avec des breakpoints standardisés :

```css
/* Mobile: 0-640px    → Base styles */
/* Tablet: 640-1024px → Ajustements layout */
/* Desktop: 1024px+   → Layout large écran */
```

---

## 📂 Structure des fichiers

```
songsurf-frontend/
├── static/
│   ├── css/
│   │   ├── design-system.css    ⭐ Variables + tokens (160 lignes)
│   │   ├── components.css        ⭐ Composants UI (450 lignes)
│   │   ├── layouts.css           ⭐ Structure page (320 lignes)
│   │   └── pages/
│   │       ├── dashboard.css     Styles page admin
│   │       ├── guest.css         Styles page guest
│   │       └── auth.css          Styles authentification
│   ├── js/
│   │   ├── api.js                ⭐ Client HTTP (180 lignes)
│   │   ├── components/
│   │   │   ├── progress-bar.js   Barre de progression
│   │   │   ├── modal.js          Gestion modales
│   │   │   └── toast.js          Notifications
│   │   └── pages/
│   │       ├── dashboard.js      Logique admin
│   │       └── guest.js          Logique guest
│   └── images/
│       └── icons/
└── templates/
    ├── base.html                 ⭐ Layout de base
    ├── components/
    │   ├── header.html           Header réutilisable
    │   ├── session-bar.html      Barre de session
    │   └── metadata-card.html    Card métadonnées
    └── pages/
        ├── dashboard.html        Page admin
        ├── guest.html            Page guest
        ├── login.html            Page connexion
        └── loading.html          Page chargement
```

---

## 🎨 Design System (design-system.css)

### Variables CSS disponibles

#### Couleurs
```css
--color-bg-primary      : #0a0a0f    /* Fond principal */
--color-bg-secondary    : #13131a    /* Fond secondaire */
--color-surface-1       : rgba(...)  /* Surface niveau 1 */
--color-border-1        : rgba(...)  /* Bordure niveau 1 */
--color-text-primary    : #ffffff    /* Texte principal */
--color-text-muted      : rgba(...)  /* Texte atténué */
--color-primary         : #7c3aed    /* Accent principal */
--color-success         : #10b981    /* Succès */
--color-error           : #ef4444    /* Erreur */
--gradient-brand        : linear-gradient(135deg, #ff3b6d, #7c3aed)
```

#### Espacements
```css
--space-1: 4px
--space-2: 8px
--space-3: 12px
--space-4: 16px
--space-6: 24px
--space-8: 32px
```

#### Radius
```css
--radius-sm : 6px
--radius-md : 8px
--radius-lg : 10px
--radius-xl : 12px
--radius-2xl: 16px
--radius-3xl: 20px
```

#### Typographie
```css
--font-size-xs  : 11px
--font-size-sm  : 12px
--font-size-base: 13px
--font-size-md  : 14px
--font-size-lg  : 15px
--font-size-xl  : 16px
--font-size-2xl : 18px
--font-size-3xl : 20px
```

### Usage
```html
<style>
  .my-component {
    padding: var(--space-4);
    background: var(--color-surface-1);
    border-radius: var(--radius-xl);
    color: var(--color-text-secondary);
  }
</style>
```

---

## 🧩 Composants (components.css)

### Boutons

```html
<!-- Variantes -->
<button class="btn btn-primary">Action principale</button>
<button class="btn btn-brand">Action secondaire</button>
<button class="btn btn-success">Succès</button>
<button class="btn btn-ghost">Neutre</button>
<button class="btn btn-danger">Danger</button>

<!-- Tailles -->
<button class="btn btn-primary btn-sm">Petit</button>
<button class="btn btn-primary">Normal</button>
<button class="btn btn-primary btn-lg">Grand</button>
<button class="btn btn-primary btn-block">Pleine largeur</button>

<!-- État désactivé -->
<button class="btn btn-primary" disabled>Désactivé</button>
```

### Cards

```html
<div class="card">
  <div class="card-header">
    <h2 class="card-title">Titre</h2>
  </div>
  <div class="card-body">
    <p>Contenu principal de la card.</p>
  </div>
  <div class="card-footer">
    <button class="btn btn-primary">Action</button>
  </div>
</div>

<!-- Variantes -->
<div class="card card-elevated">Card avec ombre</div>
<div class="card card-interactive">Card cliquable</div>
```

### Forms

```html
<div class="form-group">
  <label class="form-label">Libellé</label>
  <input type="text" class="form-input" placeholder="Placeholder...">
</div>

<div class="form-group">
  <label class="form-label">Message</label>
  <textarea class="form-textarea" placeholder="Votre message..."></textarea>
</div>

<!-- Input avec icône -->
<div class="input-group">
  <span class="input-icon">🔍</span>
  <input type="text" class="form-input" placeholder="Rechercher...">
</div>
```

### Alerts

```html
<div class="alert alert-success">Opération réussie !</div>
<div class="alert alert-error">Une erreur est survenue.</div>
<div class="alert alert-warning">Attention à cette action.</div>
<div class="alert alert-info">Information utile.</div>
```

### Badges

```html
<span class="badge badge-primary">🔐 Admin</span>
<span class="badge badge-success">🎭 Guest</span>
<span class="badge badge-warning">⚠️ Quota</span>
```

### Progress Bar

```html
<div class="progress">
  <div class="progress-bar" style="width: 75%;"></div>
</div>

<!-- Variantes -->
<div class="progress">
  <div class="progress-bar success" style="width: 100%;"></div>
</div>
<div class="progress">
  <div class="progress-bar error" style="width: 30%;"></div>
</div>
```

### Modal

```html
<div class="modal-overlay active">
  <div class="modal">
    <div class="modal-header">
      <div class="modal-icon">⚠️</div>
      <h2 class="modal-title">Confirmation</h2>
    </div>
    <div class="modal-body">
      Êtes-vous sûr de vouloir continuer ?
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost">Annuler</button>
      <button class="btn btn-primary">Confirmer</button>
    </div>
  </div>
</div>
```

### Spinner

```html
<div class="spinner"></div>
<div class="spinner spinner-sm"></div>
<div class="spinner spinner-lg"></div>
```

### Toggle Switch

```html
<div class="toggle">
  <label class="toggle-label">Activer la fonctionnalité</label>
  <label class="toggle-switch">
    <input type="checkbox">
    <span class="toggle-slider"></span>
  </label>
</div>
```

### Stats Cards

```html
<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-value">1,234</div>
    <div class="stat-label">Artistes</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">5,678</div>
    <div class="stat-label">Albums</div>
  </div>
  <div class="stat-card">
    <div class="stat-value">89,012</div>
    <div class="stat-label">Titres</div>
  </div>
</div>
```

### Empty State

```html
<div class="empty-state">
  <div class="empty-state-icon">📭</div>
  <h3 class="empty-state-title">Aucune musique</h3>
  <p class="empty-state-text">Téléchargez votre première chanson.</p>
</div>
```

---

## 📐 Layouts (layouts.css)

### Header

```html
<header class="header">
  <div class="header-brand">
    <span class="header-logo">🎵</span>
    <h1 class="header-title">SongSurf</h1>
  </div>
  <nav class="header-nav">
    <a href="/logout" class="btn btn-ghost btn-sm">Déconnexion</a>
  </nav>
</header>
```

### Main Container

```html
<!-- Container normal (640px max) -->
<main class="main">
  <!-- Contenu -->
</main>

<!-- Container large (1024px max) -->
<main class="main main-wide">
  <!-- Contenu -->
</main>

<!-- Container pleine largeur -->
<main class="main main-full">
  <!-- Contenu -->
</main>
```

### Grids

```html
<!-- Grid 2 colonnes -->
<div class="grid grid-2">
  <div>Colonne 1</div>
  <div>Colonne 2</div>
</div>

<!-- Grid 3 colonnes -->
<div class="grid grid-3">
  <div>Col 1</div>
  <div>Col 2</div>
  <div>Col 3</div>
</div>

<!-- Grid auto (responsive) -->
<div class="grid grid-auto">
  <div>Item 1</div>
  <div>Item 2</div>
  <div>Item 3</div>
</div>
```

### Flex Utilities

```html
<div class="flex gap-4">
  <div>Item 1</div>
  <div>Item 2</div>
</div>

<div class="flex-between">
  <div>Gauche</div>
  <div>Droite</div>
</div>

<div class="flex-center">
  <div>Centré verticalement et horizontalement</div>
</div>
```

---

## 🔌 API Client (api.js)

### Usage de base

```js
// GET request
const stats = await api.getStats();
console.log(stats);

// POST request
const data = await api.download(url, metadata);

// Gestion d'erreur
try {
  await api.extractMetadata(url);
} catch (error) {
  console.error('Erreur:', error.message);
}
```

### Méthodes disponibles

#### Admin
```js
api.getStats()                        // Récupérer stats bibliothèque
api.getStatus()                       // Statut téléchargement actuel
api.extractMetadata(url)              // Extraire métadonnées YouTube
api.download(url, metadata, mode)     // Lancer un téléchargement
api.downloadPlaylist(url, meta, mode) // Télécharger une playlist
api.cancel()                          // Annuler téléchargement
api.cleanup()                         // Nettoyer fichiers temp
```

#### Guest
```js
api.getGuestStatus()                        // Statut guest
api.guestExtractMetadata(url)               // Extraire (guest)
api.guestDownload(url, metadata, mode)      // Télécharger (guest)
api.guestDownloadPlaylist(url, meta, mode)  // Playlist (guest)
api.guestPrepareZip()                       // Préparer ZIP
api.extendGuestSession()                    // Prolonger session
api.guestCancel()                           // Annuler (guest)
```

### Requêtes custom

```js
// GET personnalisé
const data = await api.get('/api/custom-endpoint');

// POST personnalisé
const result = await api.post('/api/custom', { key: 'value' });
```

---

## 📄 Templates (base.html)

### Structure de base

```html
{% extends "base.html" %}

{% block title %}Ma Page — SongSurf{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/ma-page.css') }}">
{% endblock %}

{% block body %}
<header class="header">
  <!-- Header content -->
</header>

<main class="main">
  <!-- Page content -->
</main>
{% endblock %}

{% block extra_js %}
<script src="{{ url_for('static', filename='js/pages/ma-page.js') }}"></script>
{% endblock %}
```

### Variables disponibles

```html
<!-- Flask/Jinja2 -->
{{ url_for('static', filename='css/design-system.css') }}
{{ stats.songs }}
{% if user.is_admin %}...{% endif %}
{% for item in items %}...{% endfor %}

<!-- Tera (Rust) — syntaxe identique -->
{{ url_for(path="static/css/design-system.css") }}
{{ stats.songs }}
{% if user.is_admin %}...{% endif %}
{% for item in items %}...{% endfor %}
```

---

## 🚀 Migration depuis V1

Voir **[MIGRATION.md](./MIGRATION.md)** pour le guide complet de migration.

**Résumé rapide :**

1. Copier les nouveaux fichiers CSS/JS
2. Créer `base.html`
3. Migrer page par page (login → dashboard → guest)
4. Remplacer le CSS inline par les classes de composants
5. Extraire le JS dans des fichiers séparés
6. Utiliser `api.js` pour les requêtes HTTP

**Gain attendu : -40% de code, 0% de duplication, +90% de réutilisabilité**

---

## 🔧 Développement

### Ajouter un nouveau composant

1. **Définir le HTML**
   ```html
   <!-- templates/components/my-component.html -->
   <div class="my-component">
     {{ content }}
   </div>
   ```

2. **Ajouter le CSS dans components.css**
   ```css
   .my-component {
     padding: var(--space-4);
     background: var(--color-surface-1);
     border-radius: var(--radius-xl);
   }
   ```

3. **Utiliser dans une page**
   ```html
   {% include "components/my-component.html" with content="Hello" %}
   ```

### Ajouter une nouvelle page

1. **Créer le template**
   ```html
   <!-- templates/pages/ma-page.html -->
   {% extends "base.html" %}
   {% block body %}...{% endblock %}
   ```

2. **Créer le CSS (optionnel)**
   ```css
   /* static/css/pages/ma-page.css */
   .ma-page-specific { ... }
   ```

3. **Créer le JS (optionnel)**
   ```js
   // static/js/pages/ma-page.js
   console.log('Ma page chargée');
   ```

### Tester localement

```bash
# Flask (V1)
cd python-server
python app.py
# → http://localhost:8080

# Rust (V2 — à venir)
cd songsurf-rust
cargo run
# → http://localhost:8080
```

---

## 📊 Métriques

| Métrique | V1 (Python Flask) | V2 (Architecture modulaire) |
|----------|-------------------|------------------------------|
| **Lignes CSS totales** | ~1550 | ~930 |
| **Duplication CSS** | ~70% | 0% |
| **Lignes JS dashboard** | ~300 | ~200 |
| **Composants réutilisables** | 0 | 15+ |
| **Bundle CSS (gzipped)** | ~45 KB | ~28 KB |
| **Maintenabilité** | ⚠️ Difficile | ✅ Facile |

---

## 🎯 Roadmap

### ✅ Phase 1 — Design System (FAIT)
- Variables CSS centralisées
- Composants UI réutilisables
- Layouts responsive
- Client API JavaScript

### 🚧 Phase 2 — Migration templates (EN COURS)
- [ ] Migrer login.html
- [ ] Migrer dashboard.html
- [ ] Migrer guest.html
- [ ] Créer composants réutilisables

### 📅 Phase 3 — Rust Backend (À VENIR)
- [ ] Setup Axum + Tera
- [ ] Migrer les routes Flask → Axum
- [ ] Intégrer les templates V2
- [ ] Tests de compatibilité

---

## 📚 Ressources

- **CSS Variables** : [MDN — Custom Properties](https://developer.mozilla.org/en-US/docs/Web/CSS/--*)
- **BEM Methodology** : [getbem.com](http://getbem.com/)
- **Tera Templates** : [keats.github.io/tera](https://keats.github.io/tera/)
- **Axum Framework** : [docs.rs/axum](https://docs.rs/axum/)

---

## 🤝 Contributing

Pour contribuer à l'architecture frontend :

1. Fork le projet
2. Créer une branche (`git checkout -b feature/nouveau-composant`)
3. Ajouter ton composant dans `components.css`
4. Documenter l'usage dans ce README
5. Commit (`git commit -m 'Add: nouveau composant'`)
6. Push (`git push origin feature/nouveau-composant`)
7. Ouvrir une Pull Request

---

## 📝 License

MIT License — Voir [LICENSE](../LICENSE)

---

**Questions ? Bugs ? Suggestions ?**  
Ouvrir une issue sur GitHub ou contacter l'équipe dev !
