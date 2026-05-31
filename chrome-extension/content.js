// SongSurf Clip — content script (music.youtube.com)

(function () {
  'use strict';

  // ── URL detection ─────────────────────────────────────────────────────────────

  function detectType(url) {
    try {
      const u = new URL(url);
      if (u.pathname === '/watch' && u.searchParams.has('v')) return 'song';
      if (u.pathname === '/playlist') {
        const list = u.searchParams.get('list') || '';
        return list.startsWith('OLAK5uy_') ? 'album' : 'playlist';
      }
      if (u.pathname.startsWith('/channel/') || u.pathname.startsWith('/artist/')) return 'artist';
    } catch {}
    return null;
  }

  function getCleanUrl(url, type) {
    try {
      const u = new URL(url);
      if (type === 'song')
        return `https://music.youtube.com/watch?v=${u.searchParams.get('v')}`;
      if (type === 'album' || type === 'playlist')
        return `https://music.youtube.com/playlist?list=${u.searchParams.get('list')}`;
    } catch {}
    return url;
  }

  const TYPE_META = {
    song:     { emoji: '🎵', label: 'Chanson'  },
    album:    { emoji: '💿', label: 'Album'    },
    playlist: { emoji: '📋', label: 'Playlist' },
    artist:   { emoji: '🎤', label: 'Artiste'  },
  };

  // ── Toast ─────────────────────────────────────────────────────────────────────

  let toastEl = null, toastTimer = null;

  function ensureToast() {
    if (toastEl && document.body.contains(toastEl)) return;
    toastEl = document.createElement('div');
    Object.assign(toastEl.style, {
      position: 'fixed', bottom: '90px', right: '20px', zIndex: '2147483645',
      background: '#1a202c', color: '#fff', padding: '10px 16px',
      borderRadius: '10px', fontFamily: 'system-ui, sans-serif',
      fontSize: '13px', fontWeight: '500', display: 'flex',
      alignItems: 'center', gap: '8px',
      boxShadow: '0 4px 20px rgba(0,0,0,.5)', opacity: '0',
      transform: 'translateY(10px)', transition: 'opacity .2s, transform .2s',
      pointerEvents: 'none', maxWidth: '280px', lineHeight: '1.4',
    });
    document.body.appendChild(toastEl);
  }

  function showToast(emoji, msg, isError = false) {
    ensureToast();
    toastEl.style.background = isError ? '#742a2a' : '#1a202c';
    toastEl.innerHTML = `<span style="font-size:17px;flex-shrink:0">${emoji}</span><span>${msg}</span>`;
    toastEl.style.opacity = '1';
    toastEl.style.transform = 'translateY(0)';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.style.opacity = '0';
      toastEl.style.transform = 'translateY(10px)';
    }, 3500);
  }

  // ── Shared panel styles ───────────────────────────────────────────────────────

  function ensurePanelStyles() {
    if (document.getElementById('songsurf-panel-styles')) return;
    const style = document.createElement('style');
    style.id = 'songsurf-panel-styles';
    style.textContent = `
      #songsurf-panel {
        position: fixed;
        bottom: 76px;
        right: 20px;
        z-index: 2147483646;
        width: 290px;
        background: #1a202c;
        border-radius: 14px;
        box-shadow: 0 8px 32px rgba(0,0,0,.6);
        border: 1px solid rgba(255,255,255,.1);
        font-family: system-ui, -apple-system, sans-serif;
        color: #f3f4f6;
        animation: ssp-in .18s ease;
      }
      @keyframes ssp-in {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
      }
      #ssp-inner { padding: 14px; display: flex; flex-direction: column; gap: 10px; }
      #ssp-header { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
      #ssp-type { font-size: 11px; color: #60a5fa; font-weight: 600;
                  letter-spacing: .04em; text-transform: uppercase; }
      #ssp-title {
        font-size: 13px; font-weight: 600; color: #fff;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      #ssp-count { font-size: 11px; color: #9ca3af; }
      .ssp-field { display: flex; flex-direction: column; gap: 4px; }
      .ssp-field label {
        font-size: 10px; font-weight: 700; color: #9ca3af;
        letter-spacing: .06em; text-transform: uppercase;
      }
      .ssp-field input {
        background: #111827; border: 1.5px solid rgba(255,255,255,.12);
        border-radius: 7px; color: #f3f4f6; font-size: 13px;
        padding: 7px 10px; outline: none; font-family: inherit;
        transition: border-color .15s;
      }
      .ssp-field input:focus { border-color: #2563eb; }
      #ssp-actions { display: flex; gap: 8px; padding-top: 2px; }
      #ssp-cancel {
        flex: 1; padding: 8px; border-radius: 8px;
        background: rgba(255,255,255,.06); color: #d1d5db;
        border: 1px solid rgba(255,255,255,.1); font-size: 13px;
        font-weight: 600; cursor: pointer; font-family: inherit;
        transition: background .15s;
      }
      #ssp-cancel:hover { background: rgba(255,255,255,.12); }
      #ssp-confirm {
        flex: 2; padding: 8px; border-radius: 8px;
        background: #2563eb; color: #fff; border: none;
        font-size: 13px; font-weight: 700; cursor: pointer;
        font-family: inherit; transition: background .15s;
      }
      #ssp-confirm:hover { background: #1d4ed8; }
      #ssp-confirm:disabled { background: #374151; color: #6b7280; cursor: not-allowed; }
    `;
    document.head.appendChild(style);
  }

  // ── Panel (song / album / playlist — with editable metadata) ─────────────────

  let panelEl = null;

  function closePanel() {
    if (panelEl) { panelEl.remove(); panelEl = null; }
  }

  function showPanel(meta, url, urlType) {
    closePanel();
    ensurePanelStyles();

    panelEl = document.createElement('div');
    panelEl.id = 'songsurf-panel';

    const isSong = urlType === 'song';

    panelEl.innerHTML = `
      <div id="ssp-inner">
        <div id="ssp-header">
          <div id="ssp-type">${TYPE_META[urlType]?.emoji || ''} ${TYPE_META[urlType]?.label || urlType}</div>
          <div id="ssp-title" title="${esc(meta.title)}">${esc(meta.title)}</div>
          ${!isSong ? `<div id="ssp-count">${meta.song_count || '?'} titres</div>` : ''}
        </div>

        <div class="ssp-field">
          <label>Artiste</label>
          <input id="ssp-artist" type="text" value="${esc(meta.artist)}" placeholder="Artiste">
        </div>
        <div class="ssp-field">
          <label>${isSong ? 'Album' : 'Nom du dossier'}</label>
          <input id="ssp-album" type="text" value="${esc(isSong ? meta.album : meta.title)}" placeholder="Album">
        </div>
        <div class="ssp-field">
          <label>Année</label>
          <input id="ssp-year" type="text" value="${esc(meta.year)}" placeholder="Année" maxlength="4" style="width:90px">
        </div>

        <div id="ssp-actions">
          <button id="ssp-cancel">Annuler</button>
          <button id="ssp-confirm">Ajouter →</button>
        </div>
      </div>
    `;

    document.body.appendChild(panelEl);

    document.getElementById('ssp-cancel').addEventListener('click', () => {
      closePanel();
      updateButtonForUrl(location.href);
    });

    document.getElementById('ssp-confirm').addEventListener('click', async () => {
      const btn    = document.getElementById('ssp-confirm');
      const artist = document.getElementById('ssp-artist').value.trim();
      const album  = document.getElementById('ssp-album').value.trim();
      const year   = document.getElementById('ssp-year').value.trim();

      btn.disabled    = true;
      btn.textContent = '…';

      const result = await chrome.runtime.sendMessage({ type: 'QUEUE_URL', url, meta: { artist, album, year, title: meta.title } });

      closePanel();
      if (result && result.success) {
        const typeLabel = TYPE_META[result.type]?.label || 'Élément';
        showToast('✅', `${typeLabel} ajouté(e) à la queue SongSurf`);
        flashButton('green');
      } else {
        showToast('❌', (result && result.error) || 'Erreur', true);
        updateButtonForUrl(location.href);
      }
    });
  }

  // ── Panel artiste (discographie — batch sans métadonnées) ─────────────────────

  function scrapeAlbumUrls() {
    const seen = new Set();
    const urls = [];

    // Target only the "Albums" shelf — not Singles, Videos, EPs, etc.
    const shelves = document.querySelectorAll('ytmusic-carousel-shelf-renderer');
    for (const shelf of shelves) {
      const heading = shelf.querySelector('yt-formatted-string.title');
      if (!heading || !heading.textContent.trim().toLowerCase().includes('album')) continue;

      shelf.querySelectorAll('a[href*="browse/MPREb_"]').forEach(link => {
        try {
          const href = link.getAttribute('href');
          const m = href.match(/browse\/(MPREb_[^/?&#]+)/);
          if (m) {
            const url = `https://music.youtube.com/browse/${m[1]}`;
            if (!seen.has(url)) { seen.add(url); urls.push(url); }
          }
        } catch {}
      });
    }

    return urls;
  }

  function showArtistPanel(albums) {
    closePanel();
    ensurePanelStyles();

    const artistName = document.title.replace(/\s*[-–]\s*YouTube Music\s*$/i, '').trim() || 'Artiste';
    const n = albums.length;

    panelEl = document.createElement('div');
    panelEl.id = 'songsurf-panel';

    panelEl.innerHTML = `
      <div id="ssp-inner">
        <div id="ssp-header">
          <div id="ssp-type">🎤 Artiste · Discographie</div>
          <div id="ssp-title" title="${esc(artistName)}">${esc(artistName)}</div>
          <div id="ssp-count">${n} album${n > 1 ? 's' : ''} détecté${n > 1 ? 's' : ''}</div>
        </div>
        <div id="ssp-actions">
          <button id="ssp-cancel">Annuler</button>
          <button id="ssp-confirm">Tout ajouter →</button>
        </div>
      </div>
    `;

    document.body.appendChild(panelEl);

    document.getElementById('ssp-cancel').addEventListener('click', () => {
      closePanel();
      updateButtonForUrl(location.href);
    });

    document.getElementById('ssp-confirm').addEventListener('click', async () => {
      const btn = document.getElementById('ssp-confirm');
      btn.disabled    = true;
      btn.textContent = '…';

      const result = await chrome.runtime.sendMessage({ type: 'QUEUE_BATCH', urls: albums });

      closePanel();
      if (result && result.success) {
        showToast('✅', `${result.added} album${result.added > 1 ? 's' : ''} ajouté${result.added > 1 ? 's' : ''} à la queue SongSurf`);
        flashButton('green');
      } else {
        showToast('❌', (result && result.error) || 'Erreur', true);
        updateButtonForUrl(location.href);
      }
    });
  }

  function esc(str) {
    return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
                      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Floating button ───────────────────────────────────────────────────────────

  let floatBtn = null, lastType = null, isBusy = false;

  function ensureButton() {
    if (floatBtn && document.body.contains(floatBtn)) return;
    floatBtn = document.createElement('button');
    floatBtn.id = 'songsurf-fab';
    Object.assign(floatBtn.style, {
      position: 'fixed', bottom: '24px', right: '20px', zIndex: '2147483647',
      display: 'flex', alignItems: 'center', gap: '7px',
      padding: '9px 18px', borderRadius: '24px', border: 'none',
      background: 'rgba(20,20,30,.88)', backdropFilter: 'blur(8px)',
      color: '#fff', fontFamily: 'system-ui, -apple-system, sans-serif',
      fontSize: '13px', fontWeight: '600', cursor: 'pointer',
      boxShadow: '0 2px 16px rgba(0,0,0,.5)',
      transition: 'transform .15s, background .15s, opacity .2s',
      outline: 'none', whiteSpace: 'nowrap',
    });

    floatBtn.addEventListener('mouseenter', () => {
      if (!isBusy) floatBtn.style.background = 'rgba(37,99,235,.9)';
    });
    floatBtn.addEventListener('mouseleave', () => {
      if (!isBusy) floatBtn.style.background = 'rgba(20,20,30,.88)';
    });
    floatBtn.addEventListener('mousedown', () => { floatBtn.style.transform = 'scale(.95)'; });
    floatBtn.addEventListener('mouseup',   () => { floatBtn.style.transform = 'scale(1)'; });

    floatBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (isBusy) return;

      // If panel already open, close it
      if (panelEl) { closePanel(); updateButtonForUrl(location.href); return; }

      const type = detectType(location.href);
      if (!type) return;

      // ── Artiste : scraping DOM synchrone, pas d'appel API ──
      if (type === 'artist') {
        const albums = scrapeAlbumUrls();
        if (!albums.length) {
          showToast('⚠️', 'Aucun album détecté — fais défiler la discographie d\'abord', true);
          updateButtonForUrl(location.href);
          return;
        }
        showArtistPanel(albums);
        setButtonLabel('Fermer ✕', '');
        return;
      }

      // ── Song / album / playlist : preview API ──
      const url = getCleanUrl(location.href, type);

      isBusy = true;
      setButtonLabel('Analyse…', '⏳');
      floatBtn.style.background = 'rgba(20,20,30,.88)';

      const result = await chrome.runtime.sendMessage({ type: 'PREVIEW_URL', url });

      isBusy = false;

      if (!result || !result.success) {
        const msg = result?.error || 'Erreur réseau';
        if (msg.includes('uthenti') || msg.includes('connecte')) {
          showToast('🔐', msg, true);
        } else {
          showToast('❌', msg, true);
        }
        updateButtonForUrl(location.href);
        return;
      }

      showPanel(result, url, type);
      setButtonLabel('Fermer ✕', '');
    });

    document.body.appendChild(floatBtn);
  }

  function setButtonLabel(label, emoji) {
    if (!floatBtn) return;
    floatBtn.innerHTML = emoji
      ? `<span style="font-size:16px">${emoji}</span><span>${label}</span>`
      : `<span>${label}</span>`;
  }

  function flashButton(color) {
    if (!floatBtn) return;
    const bg = color === 'green' ? 'rgba(16,185,129,.85)' : 'rgba(239,68,68,.8)';
    floatBtn.style.background = bg;
    setTimeout(() => {
      floatBtn.style.background = 'rgba(20,20,30,.88)';
      updateButtonForUrl(location.href);
    }, 1200);
  }

  function updateButtonForUrl(url) {
    const type = detectType(url);
    isBusy = false;
    if (!type) {
      if (floatBtn) floatBtn.style.display = 'none';
      lastType = null;
      return;
    }
    ensureButton();
    floatBtn.style.display = 'flex';
    lastType = type;
    const m = TYPE_META[type];
    setButtonLabel(`+ SongSurf · ${m.label}`, m.emoji);
    floatBtn.title = type === 'artist'
      ? 'Détecter les albums de cet artiste et ajouter à SongSurf'
      : `Analyser et ajouter ${m.label.toLowerCase()} à SongSurf`;
  }

  // ── SPA watcher ───────────────────────────────────────────────────────────────

  let lastUrl = location.href;

  const observer = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      closePanel();
      updateButtonForUrl(location.href);
    }
    if (floatBtn && !document.body.contains(floatBtn) && lastType)
      document.body.appendChild(floatBtn);
    if (toastEl && !document.body.contains(toastEl))
      document.body.appendChild(toastEl);
  });

  observer.observe(document.documentElement, { childList: true, subtree: true });
  updateButtonForUrl(location.href);

})();
