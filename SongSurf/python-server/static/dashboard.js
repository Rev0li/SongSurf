const API_BASE = 'http://localhost:8080';

let libraryData = null;

const navigationState = {
  view: 'artists',
  currentArtist: null,
  currentAlbum: null
};

document.addEventListener('DOMContentLoaded', () => {
  console.log('🎵 Dashboard SongSurf initialisé');
  loadData();
  loadLibrary();
});

async function loadData() {
  try {
    const statsResponse = await fetch(`${API_BASE}/stats`);
    const stats = await statsResponse.json();
    updateStats(stats);

    const statusResponse = await fetch(`${API_BASE}/status`);
    const status = await statusResponse.json();
    updateStatus(status);
  } catch (error) {
    console.error('❌ Erreur lors du chargement des données:', error);
  }
}

function updateStats(stats) {
  const artistsEl = document.getElementById('total-artists');
  const albumsEl = document.getElementById('total-albums');
  const songsEl = document.getElementById('total-songs');
  
  if (artistsEl) artistsEl.textContent = stats.artists || 0;
  if (albumsEl) albumsEl.textContent = stats.albums || 0;
  if (songsEl) songsEl.textContent = stats.songs || 0;
}

function updateStatus(status) {
  console.log('📊 Status:', status);
}

async function loadLibrary() {
  try {
    const response = await fetch(`${API_BASE}/api/library`);
    libraryData = await response.json();
    renderLibraryTree();
  } catch (error) {
    console.error('❌ Erreur lors du chargement de la bibliothèque:', error);
  }
}

function renderLibraryTree() {
  if (!libraryData || !libraryData.songs) return;
  
  if (navigationState.view === 'artists') {
    renderArtistsView();
  } else if (navigationState.view === 'albums') {
    renderAlbumsView(navigationState.currentArtist);
  }
}

function renderArtistsView() {
  const container = document.getElementById('library-tree');

  const artistsMap = new Map();
  libraryData.songs.forEach((song) => {
    if (!artistsMap.has(song.artist)) {
      artistsMap.set(song.artist, {
        albums: new Map(),
        totalSongs: 0,
      });
    }

    const artistData = artistsMap.get(song.artist);

    if (!artistData.albums.has(song.album)) {
      const albumArt = song.album_art || song.albumArt || song.cover || song.artwork || null;
      artistData.albums.set(song.album, {
        songs: [],
        albumArt: albumArt,
      });
    }

    artistData.albums.get(song.album).songs.push(song);
    artistData.totalSongs++;
  });

  let html = `
    <div class="breadcrumb-nav">
      <div class="breadcrumb-item active">
        <span>🎵</span>
        <span>Tous les artistes</span>
      </div>
    </div>
  `;

  html += '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 24px;">';

  Array.from(artistsMap.entries())
    .sort()
    .forEach(([artist, artistData]) => {
      const albumCount = artistData.albums.size;
      const artistPhotoUrl = `/api/artist-photo/${encodeURIComponent(artist)}`;
      html += `
        <div class="artist-card" onclick="showArtistAlbums('${artist.replace(/'/g, "\\'")}')">
          <div class="artist-card-content">
            <div class="artist-avatar" style="position: relative;">
              <img src="${artistPhotoUrl}" 
                   alt="${artist}" 
                   style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;"
                   onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
              <div style="display: none; width: 100%; height: 100%; align-items: center; justify-content: center; font-size: 48px;">🎤</div>
              <button class="upload-photo-btn" onclick="event.stopPropagation(); openPhotoUpload('${artist.replace(/'/g, "\\'")}')">📷</button>
            </div>
            <h3 class="artist-name">${artist}</h3>
            <div class="artist-stats">
              <div class="artist-stat">
                <div class="artist-stat-value">${albumCount}</div>
                <div class="artist-stat-label">Album${albumCount > 1 ? "s" : ""}</div>
              </div>
              <div class="artist-stat">
                <div class="artist-stat-value">${artistData.totalSongs}</div>
                <div class="artist-stat-label">Titre${artistData.totalSongs > 1 ? "s" : ""}</div>
              </div>
            </div>
          </div>
        </div>
      `;
    });

  html += "</div>";
  container.innerHTML = html;

  navigationState.view = "artists";
  navigationState.currentArtist = null;
  navigationState.currentAlbum = null;
}

function showArtistAlbums(artistName) {
  navigationState.view = 'albums';
  navigationState.currentArtist = artistName;
  renderAlbumsView(artistName);
}

function renderAlbumsView(artistName) {
  const container = document.getElementById("library-tree");

  const artistsMap = new Map();
  libraryData.songs.forEach((song) => {
    if (!artistsMap.has(song.artist)) {
      artistsMap.set(song.artist, {
        albums: new Map(),
        totalSongs: 0,
      });
    }

    const artistData = artistsMap.get(song.artist);

    if (!artistData.albums.has(song.album)) {
      const albumArt = song.album_art || song.albumArt || song.cover || song.artwork || null;
      artistData.albums.set(song.album, {
        songs: [],
        albumArt: albumArt,
      });
    }

    artistData.albums.get(song.album).songs.push(song);
    artistData.totalSongs++;
  });

  const artistData = artistsMap.get(artistName);

  let html = `
    <div class="breadcrumb-nav">
      <div class="breadcrumb-item" onclick="renderArtistsView()">
        <span>🎵</span>
        <span>Artistes</span>
      </div>
      <span class="breadcrumb-separator">›</span>
      <div class="breadcrumb-item active">
        <span>🎤</span>
        <span>${artistName}</span>
      </div>
    </div>
  `;

  html += '<div class="albums-grid">';

  Array.from(artistData.albums.entries())
    .sort()
    .forEach(([album, albumData]) => {
      const songs = albumData.songs;
      const albumArt = albumData.albumArt;
      const albumId = `album-${artistName}-${album}`.replace(/[^a-zA-Z0-9]/g, "-");

      html += `
        <div class="album-flip-card" id="${albumId}" onclick="flipCard('${albumId}')">
          <div class="album-flip-card-inner">
            <div class="album-flip-card-front">
              <div class="album-cover-container">
                <div class="album-cover-wrapper">
                  ${
                    albumArt
                      ? `<img src="${albumArt}" alt="${album}" onerror="this.parentElement.innerHTML='<div style=\\'width:100%;height:100%;background:linear-gradient(135deg,rgba(255,59,109,0.3) 0%,rgba(124,58,237,0.2) 100%);display:flex;align-items:center;justify-content:center;font-size:80px;\\'><span style=\\'opacity:0.5;\\'>💿</span></div>'">`
                      : `<div style="width: 100%; height: 100%; background: linear-gradient(135deg, rgba(255, 59, 109, 0.3) 0%, rgba(124, 58, 237, 0.2) 100%); display: flex; align-items: center; justify-content: center; font-size: 80px;"><span style="opacity: 0.5;">💿</span></div>`
                  }
                </div>
                <div class="album-badge">${songs.length} Track${songs.length > 1 ? "s" : ""}</div>
              </div>
              <div class="album-info-front">
                <h3 class="album-title-front" title="${album}">${album}</h3>
                <p class="album-artist-front">${artistName}</p>
                <div class="flip-hint">
                  <span>Cliquer pour voir les titres</span>
                </div>
              </div>
            </div>
            
            <div class="album-flip-card-back">
              <div class="album-back-header">
                <h3 class="album-title-back">${album}</h3>
                <p class="album-subtitle-back">${artistName} • ${songs.length} titre${songs.length > 1 ? "s" : ""}</p>
              </div>
              <div class="songs-list-back">
      `;

      songs.forEach((song, index) => {
        html += `
          <div class="song-item-back">
            <span class="song-number-back">${index + 1}</span>
            <span class="song-icon-back">🎵</span>
            <span class="song-title-back" title="${song.title}">${song.title}</span>
          </div>
        `;
      });

      html += `
              </div>
              <button class="back-button" onclick="event.stopPropagation(); flipCard('${albumId}')">
                <span>↩️</span>
                <span>Retour</span>
              </button>
            </div>
          </div>
        </div>
      `;
    });

  html += "</div>";
  container.innerHTML = html;
}

function flipCard(cardId) {
  const card = document.getElementById(cardId);
  if (card) {
    card.classList.toggle("flipped");
  }
}


function filterLibrary(query) {
  if (!libraryData || !libraryData.songs) return;
  
  const searchTerm = query.toLowerCase().trim();
  
  if (!searchTerm) {
    renderLibraryTree();
    return;
  }

  const filteredSongs = libraryData.songs.filter(song => 
    song.title.toLowerCase().includes(searchTerm) ||
    song.artist.toLowerCase().includes(searchTerm) ||
    song.album.toLowerCase().includes(searchTerm)
  );

  const tempData = { songs: filteredSongs };
  const originalData = libraryData;
  libraryData = tempData;
  renderLibraryTree();
  libraryData = originalData;
}

function refreshDashboard() {
  console.log('🔄 Rafraîchissement manuel...');
  loadData();
  loadLibrary();
}

function openPhotoUpload(artistName) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/jpeg,image/png,image/webp';
  
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('photo', file);
    formData.append('artist_name', artistName);
    
    try {
      const response = await fetch(`${API_BASE}/api/upload-artist-photo`, {
        method: 'POST',
        body: formData
      });
      
      const result = await response.json();
      
      if (result.success) {
        console.log(`✅ Photo uploadée pour ${artistName}`);
        loadLibrary();
      } else {
        console.error(`❌ Erreur: ${result.error}`);
        alert(`Erreur: ${result.error}`);
      }
    } catch (error) {
      console.error('❌ Erreur upload:', error);
      alert('Erreur lors de l\'upload');
    }
  };
  
  input.click();
}
