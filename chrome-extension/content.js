// SongSurf Clip — content script (runs on music.youtube.com)
// Injects the "Add to SongSurf" button and toast notifications.

(function () {
  'use strict';

  // ── URL detection ────────────────────────────────────────────────────────────

  function detectType(url) {
    try {
      const u = new URL(url);
      if (u.pathname === '/watch' && u.searchParams.has('v')) return 'song';
      if (u.pathname === '/playlist') {
        const list = u.searchParams.get('list') || '';
        return list.startsWith('OLAK5uy_') ? 'album' : 'playlist';
      }
    } catch {}
    return null;
  }

  function getCleanUrl(url, type) {
    const u = new URL(url);
    if (type === 'song') {
      // Keep only the video id, drop context list
      return `https://music.youtube.com/watch?v=${u.searchParams.get('v')}`;
    }
    if (type === 'album' || type === 'playlist') {
      return `https://music.youtube.com/playlist?list=${u.searchParams.get('list')}`;
    }
    return url;
  }

  const LABELS = {
    song:     { text: '+ SongSurf',         icon: '🎵' },
    album:    { text: '+ SongSurf',          icon: '💿' },
    playlist: { text: '+ SongSurf',          icon: '📋' },
  };

  // ── Toast ────────────────────────────────────────────────────────────────────

  let toastEl = null;
  let toastTimer = null;

  function ensureToast() {
    if (toastEl) return;
    toastEl = document.createElement('div');
    toastEl.id = 'songsurf-toast';
    toastEl.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 99999;
      background: #1a202c;
      color: #fff;
      padding: 10px 18px;
      border-radius: 10px;
      font-family: -apple-system, sans-serif;
      font-size: 14px;
      font-weight: 500;
      display: flex;
      align-items: center;
      gap: 10px;
      box-shadow: 0 4px 20px rgba(0,0,0,.45);
      opacity: 0;
      transform: translateY(12px);
      transition: opacity .22s, transform .22s;
      pointer-events: none;
      max-width: 320px;
    `;
    document.body.appendChild(toastEl);
  }

  function showToast(icon, message, isError = false) {
    ensureToast();
    toastEl.style.background = isError ? '#742a2a' : '#1a202c';
    toastEl.innerHTML = `<span style="font-size:18px">${icon}</span><span>${message}</span>`;
    toastEl.style.opacity = '1';
    toastEl.style.transform = 'translateY(0)';

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.style.opacity = '0';
      toastEl.style.transform = 'translateY(12px)';
    }, 3000);
  }

  // ── Button ───────────────────────────────────────────────────────────────────

  let currentBtn  = null;
  let currentType = null;
  let isAdding    = false;

  function createButton(type) {
    const { text, icon } = LABELS[type];
    const btn = document.createElement('button');
    btn.id = 'songsurf-clip-btn';
    btn.title = `Ajouter à SongSurf (${type})`;
    btn.style.cssText = `
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 14px;
      border-radius: 20px;
      border: 1.5px solid rgba(255,255,255,.25);
      background: rgba(255,255,255,.08);
      color: #fff;
      font-family: -apple-system, sans-serif;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: background .18s, border-color .18s, transform .1s;
      white-space: nowrap;
      letter-spacing: .02em;
    `;
    btn.innerHTML = `<span style="font-size:16px">${icon}</span><span>${text}</span>`;

    btn.addEventListener('mouseenter', () => {
      btn.style.background = 'rgba(255,255,255,.16)';
      btn.style.borderColor = 'rgba(255,255,255,.5)';
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.background = 'rgba(255,255,255,.08)';
      btn.style.borderColor = 'rgba(255,255,255,.25)';
    });
    btn.addEventListener('mousedown', () => {
      btn.style.transform = 'scale(.96)';
    });
    btn.addEventListener('mouseup', () => {
      btn.style.transform = 'scale(1)';
    });

    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (isAdding) return;
      isAdding = true;

      const url = getCleanUrl(location.href, type);
      btn.style.opacity = '.5';
      btn.style.pointerEvents = 'none';

      const result = await chrome.runtime.sendMessage({ type: 'QUEUE_URL', url });

      btn.style.opacity = '1';
      btn.style.pointerEvents = '';
      isAdding = false;

      if (result.success) {
        const typeLabels = { song: 'Chanson', album: 'Album', playlist: 'Playlist' };
        showToast('✅', `${typeLabels[result.type] || 'URL'} ajouté(e) à SongSurf`);
      } else {
        showToast('❌', result.error || 'Erreur inconnue', true);
      }
    });

    return btn;
  }

  // ── Injection ─────────────────────────────────────────────────────────────────
  // YouTube Music is an SPA — we watch for URL changes and DOM mutations.

  function inject() {
    const type = detectType(location.href);

    // Remove button if URL type changed or no longer relevant
    if (!type) {
      if (currentBtn) { currentBtn.remove(); currentBtn = null; currentType = null; }
      return;
    }

    // Already injected for this type — nothing to do
    if (currentBtn && currentBtn.isConnected && currentType === type) return;

    // Remove stale button
    if (currentBtn) { currentBtn.remove(); currentBtn = null; }

    // Find the actions bar where YT Music renders its share/menu buttons
    const anchor = findAnchor();
    if (!anchor) return;

    currentType = type;
    currentBtn  = createButton(type);
    anchor.appendChild(currentBtn);
  }

  function findAnchor() {
    // Try several selectors that YouTube Music uses (they change occasionally)
    const selectors = [
      'ytmusic-player-bar .middle-controls-buttons',
      'ytmusic-player-bar #middle-controls .buttons',
      'ytmusic-detail-header-renderer .buttons',
      'ytmusic-immersive-header-renderer .buttons',
      'ytmusic-responsive-header-renderer .buttons',
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  // ── SPA navigation observer ───────────────────────────────────────────────────

  let lastUrl = location.href;

  const observer = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      // Remove old button immediately on navigation
      if (currentBtn) { currentBtn.remove(); currentBtn = null; currentType = null; }
    }
    inject();
  });

  observer.observe(document.body, { childList: true, subtree: true });

  // Initial injection attempt
  inject();
})();
