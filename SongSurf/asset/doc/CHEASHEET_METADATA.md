# 📝 Cheatsheet — Modification des Métadonnées Backend

## 🎯 Objectif
Ajouter automatiquement le nom de l'artiste dans le nom de l'album lors de l'organisation des fichiers.

---

## 📍 Fichiers concernés

### 1️⃣ `organizer.py` — Fonction `organize()`
**Ligne ~80-150**

```python
def organize(self, file_path, metadata, playlist_mode=False):
    """
    Organise un fichier MP3.
    """
    try:
        file_path = Path(file_path)
        
        raw_artist = metadata.get('artist', 'Unknown Artist')
        album      = metadata.get('album',  'Unknown Album')
        raw_title  = metadata.get('title',  'Unknown Title')
        year       = metadata.get('year',   '')
        
        # ✅ MODIFICATION ICI : Ajouter l'artiste dans le nom de l'album
        # AVANT :
        # album = self._clean_filename(album)
        
        # APRÈS :
        if raw_artist and raw_artist != 'Unknown Artist':
            album_with_artist = f"{raw_artist} - {album}"
        else:
            album_with_artist = album
        
        album_clean = self._clean_filename(album_with_artist)
```

**Résultat :**
- **Avant** : `music/The Weeknd/After Hours/Blinding Lights.mp3`
- **Après** : `music/The Weeknd/The Weeknd - After Hours/Blinding Lights.mp3`

---

### 2️⃣ Modification complète — `organizer.py`

```python
def organize(self, file_path, metadata, playlist_mode=False):
    """
    Organise un fichier MP3.

    Mode normal (playlist_mode=False) :
        Structure  Artist/Artist - Album/Title.mp3
        Featuring auto-détecté.

    Mode playlist (playlist_mode=True) :
        Structure  Album/Title.mp3  (dossier = nom de l'album)
        Pas de tri par artiste, chaque chanson garde ses propres tags ID3.
    """
    try:
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Fichier non trouvé: {file_path}")

        logger.info(f"📁 Organisation: {file_path.name}")

        raw_artist = metadata.get('artist', 'Unknown Artist')
        album      = metadata.get('album',  'Unknown Album')
        raw_title  = metadata.get('title',  'Unknown Title')
        year       = metadata.get('year',   '')

        thumbnail_path = None

        if playlist_mode:
            # ── MODE PLAYLIST : Album/Title.mp3 ──────────────────────
            artist = self._clean_filename(raw_artist)
            
            # ✅ AJOUT : Préfixer l'album avec l'artiste
            if raw_artist and raw_artist != 'Unknown Artist':
                album_with_artist = f"{raw_artist} - {album}"
            else:
                album_with_artist = album
            
            album  = self._clean_filename(album_with_artist)
            title  = self._clean_filename(raw_title)

            logger.info(f"   🎵 Mode Playlist — dossier: {album} / titre: {title}")

            dest_dir = self.music_dir / album
            dest_dir.mkdir(parents=True, exist_ok=True)
            final_path = dest_dir / f"{title}.mp3"

            if final_path.exists():
                counter = 1
                while final_path.exists():
                    final_path = dest_dir / f"{title} ({counter}).mp3"
                    counter += 1

            shutil.copy2(file_path, final_path)
            thumbnail_path = self._find_thumbnail(file_path)

            self._update_tags(final_path, {
                'artist': artist,
                'album':  album,
                'title':  title,
                'year':   year,
            }, thumbnail_path)

        else:
            # ── MODE NORMAL : Artist/Artist - Album/Title.mp3 ────────
            feat_info = self.detect_featuring(raw_title, raw_artist)
            artist = feat_info['main_artist']
            title  = feat_info['clean_title']

            if feat_info['has_feat']:
                feat_str = ', '.join(feat_info['feat_artists'])
                title = f"{title} (feat. {feat_str})"
                logger.info(f"   🎭 Featuring détecté: {feat_str} → artiste principal: {artist}")

            artist_clean = self._clean_filename(artist)
            
            # ✅ AJOUT : Préfixer l'album avec l'artiste
            if artist and artist != 'Unknown Artist':
                album_with_artist = f"{artist} - {album}"
            else:
                album_with_artist = album
            
            album_clean = self._clean_filename(album_with_artist)
            title_clean = self._clean_filename(title)

            logger.info(f"   🎤 {artist_clean} / 💿 {album_clean} / 🎵 {title_clean} ({year})")

            album_dir = self.music_dir / artist_clean / album_clean
            album_dir.mkdir(parents=True, exist_ok=True)
            final_path = album_dir / f"{title_clean}.mp3"

            if final_path.exists():
                logger.debug(f"   ⚠️ Doublon détecté, ajout d'un suffixe")
                counter = 1
                while final_path.exists():
                    final_path = album_dir / f"{title_clean} ({counter}).mp3"
                    counter += 1

            shutil.copy2(file_path, final_path)
            thumbnail_path = self._find_thumbnail(file_path)

            self._update_tags(final_path, {
                'artist': artist,
                'album':  album_with_artist,  # ✅ Tag ID3 contient aussi l'artiste
                'title':  title,
                'year':   year,
            }, thumbnail_path)

        # ── Nettoyage commun ──────────────────────────────────────────
        file_path.unlink()
        if thumbnail_path and thumbnail_path.exists():
            thumbnail_path.unlink()

        logger.info(f"   ✅ Organisé → {final_path.relative_to(self.music_dir)}")

        return {
            'success':    True,
            'final_path': str(final_path.relative_to(self.music_dir)),
            'timestamp':  datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Erreur organisation: {e}")
        return {
            'success':   False,
            'error':     str(e),
            'timestamp': datetime.now().isoformat()
        }
```

---

## 🖼️ Correction : Ratio 1:1 pour les thumbnails (crop carré)

### Fichier : `organizer.py` — Fonction `_convert_image_to_jpeg()`

**Ligne ~200-240**

```python
def _convert_image_to_jpeg(self, image_path):
    """
    Convertit une image en JPEG avec ratio 1:1 (carré).
    Crop automatique au centre si l'image n'est pas carrée.
    """
    try:
        img = Image.open(image_path)
        
        # Convertir en RGB si nécessaire
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # ✅ AJOUT : Crop en carré 1:1
        width, height = img.size
        
        if width != height:
            # Prendre la dimension la plus petite
            min_dim = min(width, height)
            
            # Calculer les coordonnées de crop pour centrer
            left = (width - min_dim) // 2
            top = (height - min_dim) // 2
            right = left + min_dim
            bottom = top + min_dim
            
            # Crop au centre
            img = img.crop((left, top, right, bottom))
            logger.debug(f"   ✂️  Image croppée en carré: {min_dim}x{min_dim}")

        # Redimensionner si trop grand (max 800x800)
        max_size = 800
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            logger.debug(f"   📐 Image redimensionnée: {img.width}x{img.height}")

        # Sauvegarder en JPEG
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=90, optimize=True)
        
        logger.debug(f"   🖼️  Image convertie: {len(buffer.getvalue())} bytes, 1:1 ratio")
        
        return buffer.getvalue(), 'image/jpeg'

    except Exception as e:
        logger.warning(f"⚠️ Erreur conversion image: {e}")
        try:
            # Fallback : retourner l'image originale sans modification
            with open(image_path, 'rb') as f:
                img_data = f.read()
            mime_type = mimetypes.guess_type(str(image_path))[0] or 'image/jpeg'
            return img_data, mime_type
        except Exception:
            return None, None
```

---

## 🐛 Correction Bug Guest (bloqué après 1 téléchargement)

### Problème identifié
Le guest ne peut pas télécharger un 2ème morceau car le bouton reste désactivé.

### Fichier : `guest_dashboard.html` (JavaScript)

**Ligne ~350-400 (fonction `pollStatus`)**

```javascript
async function pollStatus() {
  try {
    const res  = await fetch('/api/guest/status');
    if (!res.ok) return;
    const data = await res.json();

    // ... (code existant pour quotas, progression, etc.)

    // ✅ CORRECTION : Réactiver le bouton extract après téléchargement
    const busy = data.in_progress || data.queue_size > 0;
    
    // Réactiver le bouton "Analyser" si pas de téléchargement en cours
    const btnExtract = document.getElementById('btn-extract');
    if (btnExtract) {
      btnExtract.disabled = busy;
      if (!busy) {
        btnExtract.title = '';
      }
    }

    // Progression + grisage des boutons
    const prog = data.in_progress && data.progress;
    document.getElementById('progress-zone').style.display = prog ? 'block' : 'none';
    
    // ... (reste du code)

    // Arrêter le polling si idle
    if (!data.in_progress && data.queue_size === 0) {
      clearInterval(pollInterval);
      pollInterval = null;
      
      // ✅ AJOUT : Réinitialiser complètement l'interface
      const metadataPreview = document.getElementById('metadata-preview');
      if (metadataPreview) {
        metadataPreview.style.display = 'none';
      }
      
      // Vider les champs
      document.getElementById('url-input').value = '';
      currentMeta = null;
      isPlaylist = false;
      playlistData = null;
    }
    
  } catch(e) {
    console.error('Erreur polling:', e);
  }
}
```

**OU solution alternative plus propre :**

Ajouter une fonction de reset après chaque téléchargement complété :

```javascript
// Ajouter dans la section "Dernière chanson complétée"
if (data.last_completed?.success) {
  const lc  = data.last_completed;
  const key = lc.timestamp;
  if (!completed.includes(key)) {
    completed.push(key);
    addDlItem(lc.metadata);
    
    // Afficher la zone ZIP
    document.getElementById('zip-zone').style.display       = 'block';
    document.getElementById('zip-state-idle').style.display = 'block';
    document.getElementById('zip-state-preparing').style.display = 'none';
    document.getElementById('zip-state-done').style.display = 'none';
    
    // ✅ AJOUT : Réinitialiser l'interface pour un nouveau téléchargement
    setTimeout(() => {
      document.getElementById('url-input').value = '';
      document.getElementById('metadata-preview').style.display = 'none';
      currentMeta = null;
      isPlaylist = false;
      playlistData = null;
      
      // Réactiver tous les boutons
      document.getElementById('btn-extract').disabled = false;
      const btnDl = document.getElementById('btn-dl');
      if (btnDl) btnDl.disabled = false;
    }, 1000); // Délai de 1s pour que l'utilisateur voie la confirmation
  }
}
```

---

## 📝 Résumé des modifications

### ✅ Métadonnées : Artiste dans l'album
- **Fichier** : `organizer.py`
- **Fonction** : `organize()`
- **Changement** : `album = f"{artist} - {album}"`
- **Résultat** : `The Weeknd - After Hours` au lieu de `After Hours`

### ✅ Thumbnails : Ratio 1:1
- **Fichier** : `organizer.py`
- **Fonction** : `_convert_image_to_jpeg()`
- **Changement** : Crop automatique au centre si pas carré
- **Résultat** : Toutes les pochettes sont carrées

### ✅ Bug Guest : Déblocage après 1 DL
- **Fichier** : `guest_dashboard.html` (JavaScript)
- **Fonction** : `pollStatus()`
- **Changement** : Reset interface + réactivation boutons après DL
- **Résultat** : Le guest peut télécharger plusieurs morceaux

---

## 🚀 Application des changements

```bash
# 1. Modifier organizer.py (backend)
nano python-server/organizer.py

# 2. Modifier guest_dashboard.html (frontend)
nano python-server/templates/guest_dashboard.html

# 3. Redémarrer le conteneur
docker-compose restart songsurf

# 4. Tester
# - Télécharger un morceau
# - Vérifier le nom de dossier : Artist - Album ✓
# - Vérifier la pochette : carrée ✓
# - (Guest) Essayer de télécharger 2 morceaux ✓
```

---

## 🔍 Debugging

### Vérifier les logs
```bash
docker logs -f songsurf
```

### Tester les métadonnées
```bash
# Entrer dans le conteneur
docker exec -it songsurf bash

# Lancer Python
python3

# Tester
from organizer import MusicOrganizer
org = MusicOrganizer('/data/music')

metadata = {
    'artist': 'The Weeknd',
    'album': 'After Hours',
    'title': 'Blinding Lights',
    'year': '2020'
}

# Vérifier le nom de dossier généré
artist_clean = org._clean_filename('The Weeknd')
album_with_artist = f"{metadata['artist']} - {metadata['album']}"
album_clean = org._clean_filename(album_with_artist)

print(f"Dossier final : {artist_clean}/{album_clean}/")
# Output : The Weeknd/The Weeknd - After Hours/
```

---

**Tout est prêt ! 🎉**