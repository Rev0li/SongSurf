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
      if (u.pathname.startsWith('/channel/') || u.pathname.startsWith('/artist/') || u.pathname.startsWith('/@')) return 'artist';
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
    positionPanel();

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

  // Shelf headings on the artist page: "Albums" / "Singles et EP" (FR),
  // "Albums" / "Singles & EPs" (EN). Singles and EPs are MPREb_ releases too,
  // so the link extraction is identical — only the shelf heading differs.
  const SHELF_MATCHERS = {
    albums:  (t) => t.includes('album'),
    singles: (t) => /single|\beps?\b/.test(t),
  };

  const RELEASE_KIND_META = {
    albums:  { label: 'Albums',       noun: 'album'     },
    singles: { label: 'EP & Singles', noun: 'EP/single' },
  };

  function scrapeReleases(kind) {
    const seen       = new Set();
    const items      = [];
    const artistName = document.title.replace(/\s*[-–]\s*YouTube Music\s*$/i, '').trim() || '';
    const matches    = SHELF_MATCHERS[kind];

    const shelves = document.querySelectorAll('ytmusic-carousel-shelf-renderer');
    for (const shelf of shelves) {
      const heading = shelf.querySelector('yt-formatted-string.title');
      if (!heading || !matches(heading.textContent.trim().toLowerCase())) continue;

      shelf.querySelectorAll('a[href*="browse/MPREb_"]').forEach(link => {
        try {
          const href = link.getAttribute('href');
          const m = href.match(/browse\/(MPREb_[^/?&#]+)/);
          if (m) {
            const url = `https://music.youtube.com/browse/${m[1]}`;
            if (!seen.has(url)) {
              seen.add(url);
              // Scrape album title from the card element
              const card    = link.closest('ytmusic-two-row-item-renderer') || link.parentElement;
              const titleEl = card && (card.querySelector('.title') || card.querySelector('yt-formatted-string'));
              const albumTitle = (titleEl?.title || titleEl?.textContent || '').trim();
              items.push({ url, artist: artistName, album: albumTitle });
            }
          }
        } catch {}
      });
    }

    return items;
  }

  function showArtistPanel(items, kind) {
    closePanel();
    ensurePanelStyles();

    const artistName = (items[0] && items[0].artist) || document.title.replace(/\s*[-–]\s*YouTube Music\s*$/i, '').trim() || 'Artiste';
    const n = items.length;
    const { label, noun } = RELEASE_KIND_META[kind] || RELEASE_KIND_META.albums;

    panelEl = document.createElement('div');
    panelEl.id = 'songsurf-panel';

    panelEl.innerHTML = `
      <div id="ssp-inner">
        <div id="ssp-header">
          <div id="ssp-type">🎤 Artiste · ${label}</div>
          <div id="ssp-title" title="${esc(artistName)}">${esc(artistName)}</div>
          <div id="ssp-count">${n} ${noun}${n > 1 ? 's' : ''} détecté${n > 1 ? 's' : ''}</div>
        </div>
        <div id="ssp-actions">
          <button id="ssp-cancel">Annuler</button>
          <button id="ssp-confirm">Tout ajouter →</button>
        </div>
      </div>
    `;

    document.body.appendChild(panelEl);
    positionPanel();

    document.getElementById('ssp-cancel').addEventListener('click', () => {
      closePanel();
      updateButtonForUrl(location.href);
    });

    document.getElementById('ssp-confirm').addEventListener('click', async () => {
      const btn = document.getElementById('ssp-confirm');
      btn.disabled    = true;
      btn.textContent = '…';

      const result = await chrome.runtime.sendMessage({ type: 'QUEUE_BATCH', items });

      closePanel();
      if (result && result.success) {
        showToast('✅', `${result.added} ${noun}${result.added > 1 ? 's' : ''} ajouté${result.added > 1 ? 's' : ''} à la queue SongSurf`);
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

  // ── Floating buttons (draggable) ──────────────────────────────────────────────

  let fabWrap = null, floatBtn = null, singlesBtn = null, lastType = null, isBusy = false;
  let dragMoved = false;
  const FAB_POS_KEY = 'ssf_fab_pos';
  const FAB_BG = 'rgba(20,20,30,.88)';

  function makeFabButton(id) {
    const btn = document.createElement('button');
    btn.id = id;
    Object.assign(btn.style, {
      display: 'flex', alignItems: 'center', gap: '7px',
      padding: '9px 18px', borderRadius: '24px', border: 'none',
      background: FAB_BG, backdropFilter: 'blur(8px)',
      color: '#fff', fontFamily: 'system-ui, -apple-system, sans-serif',
      fontSize: '13px', fontWeight: '600', cursor: 'pointer',
      boxShadow: '0 2px 16px rgba(0,0,0,.5)',
      transition: 'background .15s, opacity .2s',
      outline: 'none', whiteSpace: 'nowrap',
    });
    btn.addEventListener('mouseenter', () => {
      if (!isBusy) btn.style.background = 'rgba(37,99,235,.9)';
    });
    btn.addEventListener('mouseleave', () => {
      if (!isBusy) btn.style.background = FAB_BG;
    });
    return btn;
  }

  function ensureButtons() {
    if (fabWrap && document.body.contains(fabWrap)) return;
    if (!fabWrap) {
      fabWrap = document.createElement('div');
      fabWrap.id = 'songsurf-fab-wrap';
      Object.assign(fabWrap.style, {
        position: 'fixed', bottom: '24px', right: '20px', zIndex: '2147483647',
        display: 'flex', flexDirection: 'column', gap: '8px',
        alignItems: 'flex-end', touchAction: 'none', userSelect: 'none',
      });

      singlesBtn = makeFabButton('songsurf-fab-singles');
      floatBtn   = makeFabButton('songsurf-fab');
      fabWrap.appendChild(singlesBtn);
      fabWrap.appendChild(floatBtn);

      floatBtn.addEventListener('click', onMainButtonClick);
      singlesBtn.addEventListener('click', onSinglesButtonClick);

      initFabDrag(fabWrap);
      restoreFabPos();
    }
    document.body.appendChild(fabWrap);
  }

  async function onMainButtonClick(e) {
    e.stopPropagation();
    if (isBusy) return;

    // If panel already open, close it
    if (panelEl) { closePanel(); updateButtonForUrl(location.href); return; }

    const type = detectType(location.href);
    if (!type) return;

    // ── Artiste : scraping DOM synchrone, pas d'appel API ──
    if (type === 'artist') {
      openArtistPanel(floatBtn, 'albums');
      return;
    }

    // ── Song / album / playlist : preview API ──
    const url = getCleanUrl(location.href, type);

    isBusy = true;
    setButtonLabel('Analyse…', '⏳');
    floatBtn.style.background = FAB_BG;

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
  }

  function onSinglesButtonClick(e) {
    e.stopPropagation();
    if (isBusy) return;
    if (panelEl) { closePanel(); updateButtonForUrl(location.href); return; }
    openArtistPanel(singlesBtn, 'singles');
  }

  function openArtistPanel(btn, kind) {
    const items = scrapeReleases(kind);
    if (!items.length) {
      const { noun } = RELEASE_KIND_META[kind];
      showToast('⚠️', `Aucun ${noun} détecté — fais défiler la discographie d'abord`, true);
      updateButtonForUrl(location.href);
      return;
    }
    showArtistPanel(items, kind);
    setBtnLabel(btn, 'Fermer ✕', '');
  }

  // ── Drag & drop du bloc de boutons ──
  // Un vrai clic reste un clic : le drag ne démarre qu'au-delà de 6 px de
  // mouvement, et le clic qui suit un drag est avalé (listener en capture).

  function initFabDrag(wrap) {
    let startX = 0, startY = 0, origL = 0, origT = 0, pid = null;

    // Pas de setPointerCapture : Chrome retargetterait le click vers le wrap
    // et les clics normaux sur les boutons ne partiraient plus. Le suivi se
    // fait sur window, ce qui couvre aussi les mouvements rapides hors bouton.
    wrap.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      pid = e.pointerId;
      dragMoved = false;
      startX = e.clientX; startY = e.clientY;
      const r = wrap.getBoundingClientRect();
      origL = r.left; origT = r.top;
    });

    window.addEventListener('pointermove', (e) => {
      if (pid === null || e.pointerId !== pid) return;
      const dx = e.clientX - startX, dy = e.clientY - startY;
      if (!dragMoved && Math.hypot(dx, dy) < 6) return;
      dragMoved = true;
      setFabPos(origL + dx, origT + dy);
    });

    const endDrag = (e) => {
      if (pid === null || e.pointerId !== pid) return;
      pid = null;
      if (dragMoved) {
        saveFabPos();
        // Le click de fin de drag (s'il part) est avalé par le listener
        // capture ci-dessous ; on réarme après coup dans tous les cas.
        setTimeout(() => { dragMoved = false; }, 0);
      }
    };
    window.addEventListener('pointerup', endDrag);
    window.addEventListener('pointercancel', endDrag);

    wrap.addEventListener('click', (e) => {
      if (dragMoved) {
        e.stopPropagation();
        e.preventDefault();
      }
    }, true);
  }

  function setFabPos(left, top) {
    if (!fabWrap) return;
    const r    = fabWrap.getBoundingClientRect();
    const maxL = window.innerWidth  - r.width  - 4;
    const maxT = window.innerHeight - r.height - 4;
    fabWrap.style.left   = `${Math.min(Math.max(4, left), maxL)}px`;
    fabWrap.style.top    = `${Math.min(Math.max(4, top),  maxT)}px`;
    fabWrap.style.right  = 'auto';
    fabWrap.style.bottom = 'auto';
  }

  function reclampFab() {
    if (fabWrap && fabWrap.style.left)
      setFabPos(parseFloat(fabWrap.style.left), parseFloat(fabWrap.style.top));
  }

  function saveFabPos() {
    try {
      const r = fabWrap.getBoundingClientRect();
      chrome.storage.local.set({ [FAB_POS_KEY]: { left: r.left, top: r.top } });
    } catch {}
  }

  function restoreFabPos() {
    try {
      chrome.storage.local.get(FAB_POS_KEY, (v) => {
        const pos = v && v[FAB_POS_KEY];
        if (pos && typeof pos.left === 'number' && typeof pos.top === 'number')
          setFabPos(pos.left, pos.top);
      });
    } catch {}
  }

  window.addEventListener('resize', reclampFab);

  // Le panneau s'ancre au-dessus des boutons (où qu'ils soient), en restant
  // dans le viewport ; s'il n'y a pas la place au-dessus, il s'ouvre dessous.
  function positionPanel() {
    if (!panelEl || !fabWrap) return;
    const r      = fabWrap.getBoundingClientRect();
    const pw     = panelEl.offsetWidth  || 290;
    const ph     = panelEl.offsetHeight || 200;
    const margin = 10;
    const left   = Math.min(Math.max(8, r.right - pw), window.innerWidth - pw - 8);
    let top = r.top - ph - margin;
    if (top < 8) top = Math.min(r.bottom + margin, window.innerHeight - ph - 8);
    Object.assign(panelEl.style, {
      left: `${left}px`, top: `${Math.max(8, top)}px`,
      right: 'auto', bottom: 'auto',
    });
  }

  function setBtnLabel(btn, label, emoji) {
    if (!btn) return;
    btn.innerHTML = emoji
      ? `<span style="font-size:16px">${emoji}</span><span>${label}</span>`
      : `<span>${label}</span>`;
  }

  function setButtonLabel(label, emoji) {
    setBtnLabel(floatBtn, label, emoji);
  }

  function flashButton(color) {
    const bg = color === 'green' ? 'rgba(16,185,129,.85)' : 'rgba(239,68,68,.8)';
    for (const b of [floatBtn, singlesBtn])
      if (b && b.style.display !== 'none') b.style.background = bg;
    setTimeout(() => {
      for (const b of [floatBtn, singlesBtn])
        if (b) b.style.background = FAB_BG;
      updateButtonForUrl(location.href);
    }, 1200);
  }

  function updateButtonForUrl(url) {
    const type = detectType(url);
    isBusy = false;
    if (!type) {
      if (fabWrap) fabWrap.style.display = 'none';
      lastType = null;
      return;
    }
    ensureButtons();
    fabWrap.style.display = 'flex';
    lastType = type;

    if (type === 'artist') {
      singlesBtn.style.display = 'flex';
      setBtnLabel(floatBtn,   '+ SongSurf · Albums',       '💿');
      setBtnLabel(singlesBtn, '+ SongSurf · EP & Singles', '🎶');
      floatBtn.title   = 'Détecter les albums de cet artiste et les ajouter à SongSurf';
      singlesBtn.title = 'Détecter les EP et singles de cet artiste et les ajouter à SongSurf';
    } else {
      singlesBtn.style.display = 'none';
      const m = TYPE_META[type];
      setBtnLabel(floatBtn, `+ SongSurf · ${m.label}`, m.emoji);
      floatBtn.title = `Analyser et ajouter ${m.label.toLowerCase()} à SongSurf`;
    }
    reclampFab();
  }

  // ── SPA watcher ───────────────────────────────────────────────────────────────

  let lastUrl = location.href;

  const observer = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      closePanel();
      updateButtonForUrl(location.href);
    }
    if (fabWrap && !document.body.contains(fabWrap) && lastType)
      document.body.appendChild(fabWrap);
    if (toastEl && !document.body.contains(toastEl))
      document.body.appendChild(toastEl);
  });

  observer.observe(document.documentElement, { childList: true, subtree: true });
  updateButtonForUrl(location.href);

})();
