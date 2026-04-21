# 🚀 Installation Rapide — SongSurf V2

Guide d'installation en 5 minutes pour appliquer toutes les modifications.

---

## ⚡ Installation Express

```bash
# 1. Se placer dans le projet
cd /volume1/docker/SongSurf

# 2. Créer la structure frontend
mkdir -p static/css/pages static/js/pages templates/pages

# 3. Copier TOUS les fichiers CSS
curl -L https://raw.githubusercontent.com/.../design-system.css -o static/css/design-system.css
curl -L https://raw.githubusercontent.com/.../components.css -o static/css/components.css
curl -L https://raw.githubusercontent.com/.../layouts.css -o static/css/layouts.css
curl -L https://raw.githubusercontent.com/.../dashboard.css -o static/css/pages/dashboard.css

# 4. Copier TOUS les fichiers JS
curl -L https://raw.githubusercontent.com/.../api.js -o static/js/api.js
curl -L https://raw.githubusercontent.com/.../dashboard-admin.js -o static/js/pages/dashboard-admin.js

# 5. Copier les templates
curl -L https://raw.githubusercontent.com/.../base.html -o templates/base.html
curl -L https://raw.githubusercontent.com/.../login.html -o templates/pages/login.html
curl -L https://raw.githubusercontent.com/.../dashboard-admin.html -o templates/pages/dashboard-admin.html

# 6. Ajouter le montage static dans docker-compose.yml
nano docker-compose.yml
# Ajouter sous volumes: - ./static:/app/static

# 7. Redémarrer
docker-compose down && docker-compose build --no-cache && docker-compose up -d
```

---

## 📋 Installation Manuelle (si GitHub non dispo)

### Étape 1 : Créer la structure

```bash
cd /volume1/docker/SongSurf
mkdir -p static/css/pages
mkdir -p static/js/pages
mkdir -p templates/pages
```

### Étape 2 : Copier les fichiers frontend

**Copier depuis `/home/claude/songsurf-frontend/` vers votre projet :**

```bash
# CSS
cp design-system.css → static/css/
cp components.css → static/css/
cp layouts.css → static/css/
cp pages/dashboard.css → static/css/pages/

# JavaScript
cp api.js → static/js/
cp pages/dashboard-admin.js → static/js/pages/

# Templates
cp base.html → templates/
cp pages/login.html → templates/pages/
cp pages/dashboard-admin.html → templates/pages/
```

### Étape 3 : Modifier docker-compose.yml

Ajouter cette ligne dans la section `volumes` du service `songsurf` :

```yaml
services:
  songsurf:
    volumes:
      - ./static:/app/static          # ← AJOUTER CETTE LIGNE
      - ./python-server/templates:/app/templates
      - ./data/temp:/data/temp
      # ... (reste identique)
```

### Étape 4 : Modifier le backend Python

#### Fichier 1 : `python-server/organizer.py`

**Modification 1 : Ajouter artiste dans le nom d'album**

Ligne ~95 (dans la fonction `organize()`) :

```python
# CHERCHER :
album = self._clean_filename(metadata.get('album', 'Unknown Album'))

# REMPLACER PAR :
raw_artist = metadata.get('artist', 'Unknown Artist')
raw_album = metadata.get('album', 'Unknown Album')

if raw_artist and raw_artist != 'Unknown Artist':
    album_with_artist = f"{raw_artist} - {raw_album}"
else:
    album_with_artist = raw_album

album = self._clean_filename(album_with_artist)
```

**Modification 2 : Crop thumbnails en carré (ratio 1:1)**

Ligne ~215 (dans la fonction `_convert_image_to_jpeg()`) :

```python
# CHERCHER (après la conversion RGB) :
max_size = 1000

# AJOUTER AVANT max_size :
# Crop en carré 1:1
width, height = img.size
if width != height:
    min_dim = min(width, height)
    left = (width - min_dim) // 2
    top = (height - min_dim) // 2
    right = left + min_dim
    bottom = top + min_dim
    img = img.crop((left, top, right, bottom))
    logger.debug(f"✂️ Image croppée: {min_dim}x{min_dim}")

# Puis le code max_size existant...
max_size = 1000
```

#### Fichier 2 : `python-server/templates/guest_dashboard.html`

**Correction bug : Guest bloqué après 1 DL**

Ligne ~450 (dans la fonction `pollStatus()`) :

```javascript
// CHERCHER :
if (!data.in_progress && data.queue_size === 0) {
  clearInterval(pollInterval);
  pollInterval = null;
}

// REMPLACER PAR :
if (!data.in_progress && data.queue_size === 0) {
  clearInterval(pollInterval);
  pollInterval = null;
  
  // Réinitialiser l'interface
  setTimeout(() => {
    document.getElementById('url-input').value = '';
    const preview = document.getElementById('metadata-preview');
    if (preview) preview.style.display = 'none';
    document.getElementById('btn-extract').disabled = false;
    currentMeta = null;
    isPlaylist = false;
    playlistData = null;
  }, 1000);
}
```

### Étape 5 : Mettre à jour Flask app.py

**Ajouter la route pour servir les fichiers statiques** (si nécessaire) :

```python
# À la fin de app.py, avant if __name__ == '__main__':
from flask import send_from_directory

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)
```

### Étape 6 : Redémarrer

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Vérifier les logs
docker-compose logs -f
```

---

## ✅ Vérification Post-Installation

### Test 1 : CSS chargé
```bash
# Ouvrir http://votre-nas:8080
# F12 → Network → Filtrer "css"
# Vérifier que design-system.css, components.css, layouts.css sont chargés (200 OK)
```

### Test 2 : Dashboard admin
```bash
# Se connecter en admin
# Vérifier :
#  - Layout 2 colonnes ✓
#  - Pas de stats dans le header ✓
#  - Sidebar visible à droite ✓
```

### Test 3 : Barre de progression
```bash
# Télécharger un morceau
# Vérifier :
#  - 3 étapes visibles ✓
#  - Étape 1 affiche le % ✓
#  - Animation pulse sur l'étape active ✓
```

### Test 4 : Métadonnées
```bash
# Télécharger "The Weeknd - Blinding Lights"
# Vérifier dans le NAS :
#  - Dossier : The Weeknd/The Weeknd - After Hours/ ✓
```

### Test 5 : Thumbnails
```bash
# Télécharger un morceau avec pochette
# Ouvrir le MP3 dans un lecteur
# Vérifier :
#  - Pochette carrée (1:1) ✓
#  - Pas de déformation ✓
```

### Test 6 : Bug guest
```bash
# Se connecter en guest
# Télécharger 1 morceau
# Attendre la fin
# Essayer de télécharger un 2ème morceau ✓
#  - Le bouton "Analyser" doit être actif
#  - Pas de blocage
```

---

## 🐛 Dépannage

### Problème : CSS non chargé

**Cause** : Volume `static` non monté

**Solution** :
```bash
# Vérifier docker-compose.yml
grep "static" docker-compose.yml
# Doit afficher : - ./static:/app/static

# Si absent, ajouter la ligne et redémarrer
docker-compose down && docker-compose up -d
```

---

### Problème : Barre de progression reste à 0%

**Cause** : JavaScript non chargé ou API non accessible

**Solution** :
```bash
# Vérifier les logs navigateur (F12 → Console)
# Erreurs 404 sur api.js ou dashboard-admin.js ?

# Vérifier que les fichiers existent
ls -la static/js/
ls -la static/js/pages/

# Si absents, re-copier les fichiers JS
```

---

### Problème : Thumbnails toujours pas carrés

**Cause** : Modification de `_convert_image_to_jpeg()` non appliquée

**Solution** :
```bash
# Vérifier le code
docker exec -it songsurf cat /app/organizer.py | grep -A 10 "def _convert_image_to_jpeg"

# Si le code de crop n'apparaît pas :
# 1. Éditer le fichier sur le NAS
nano python-server/organizer.py

# 2. Ajouter le code de crop (voir Étape 4 ci-dessus)

# 3. Rebuild obligatoire
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

### Problème : Guest toujours bloqué

**Cause** : Modification JavaScript non appliquée OU cache navigateur

**Solution** :
```bash
# 1. Vider le cache navigateur
Ctrl + Shift + R (ou Cmd + Shift + R sur Mac)

# 2. Vérifier la modification dans le fichier
nano python-server/templates/guest_dashboard.html
# Chercher "setTimeout(() => {"
# Si absent → appliquer la correction (Étape 4 ci-dessus)

# 3. Redémarrer (pas besoin de rebuild pour les templates)
docker-compose restart songsurf
```

---

### Problème : Pop-up ne s'affiche pas

**Cause** : dashboard-admin.js non chargé OU mauvaise version du template

**Solution** :
```bash
# 1. Vérifier le fichier JS
ls -la static/js/pages/dashboard-admin.js
# Doit exister et contenir "download-complete-modal"

# 2. Vérifier le template
grep "download-complete-modal" templates/pages/dashboard-admin.html
# Doit retourner plusieurs lignes

# 3. Si absent, re-copier le template et le JS
```

---

## 📊 Checklist Complète

- [ ] Fichiers CSS copiés (4 fichiers)
- [ ] Fichiers JS copiés (2 fichiers)
- [ ] Templates copiés (3 fichiers)
- [ ] docker-compose.yml mis à jour (volume static)
- [ ] organizer.py modifié (2 fonctions)
- [ ] guest_dashboard.html modifié (1 fonction JS)
- [ ] Container redémarré avec --no-cache
- [ ] Tests de validation passés (6 tests)

---

## 🎯 Temps d'Installation Estimé

- **Installation express** : 5 minutes
- **Installation manuelle** : 15 minutes
- **Debugging** (si problèmes) : 10-30 minutes

---

## 📞 Support

**Problème non résolu ?**

1. Vérifier les logs : `docker-compose logs -f`
2. Vérifier la console navigateur (F12 → Console)
3. Re-télécharger tous les fichiers
4. Supprimer le cache Docker : `docker system prune -a`
5. Rebuild from scratch

**Documentation complète** :
- `README.md` : Architecture frontend
- `MIGRATION.md` : Migration détaillée
- `METADATA_CHEATSHEET.md` : Modifications backend
- `CHANGELOG.md` : Récapitulatif complet

---

**Bonne installation ! 🚀**
