// SongSurf Clip — background script (MV2 Firefox + MV3 Chrome)
// Handles: API calls to SongSurf, periodic ping, icon badge

const action = chrome.action || chrome.browserAction;

const PING_ALARM   = 'songsurf-ping';
const PING_MINUTES = 0.5; // every 30 seconds

// ── State ─────────────────────────────────────────────────────────────────────

let songSurfUrl  = '';
let serverStatus = 'unknown'; // 'online' | 'offline' | 'unknown'

async function loadConfig() {
  const { songsurf_url } = await chrome.storage.sync.get('songsurf_url');
  songSurfUrl = (songsurf_url || '').replace(/\/$/, '');
}

// ── Ping ──────────────────────────────────────────────────────────────────────

async function ping() {
  await loadConfig();
  if (!songSurfUrl) {
    setStatus('unknown');
    return;
  }
  try {
    const r = await fetch(`${songSurfUrl}/ping`, {
      credentials: 'include',
      signal: AbortSignal.timeout(4000),
    });
    setStatus(r.ok ? 'online' : 'offline');
  } catch {
    setStatus('offline');
  }
}

function setStatus(status) {
  serverStatus = status;
  updateBadge();
  // Notify any open popups
  chrome.runtime.sendMessage({ type: 'STATUS_UPDATE', status }).catch(() => {});
}

function updateBadge() {
  if (serverStatus === 'offline') {
    action.setBadgeText({ text: '!' });
    action.setBadgeBackgroundColor({ color: '#e53e3e' });
  } else if (serverStatus === 'online') {
    action.setBadgeText({ text: '' });
  } else {
    action.setBadgeText({ text: '?' });
    action.setBadgeBackgroundColor({ color: '#718096' });
  }
}

// ── Queue URL ─────────────────────────────────────────────────────────────────

async function apiPost(endpoint, body, timeoutMs = 8000) {
  await loadConfig();
  if (!songSurfUrl) return { _noConfig: true };
  const r = await fetch(`${songSurfUrl}${endpoint}`, {
    method:      'POST',
    credentials: 'include',
    headers:     { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body:        JSON.stringify(body),
    signal:      AbortSignal.timeout(timeoutMs),
  });
  const data = await r.json().catch(() => ({}));
  return { _status: r.status, ...data };
}

async function previewUrl(url) {
  await loadConfig();
  if (!songSurfUrl)
    return { success: false, error: 'URL SongSurf non configurée. Ouvre les options.' };
  try {
    const data = await apiPost('/api/preview', { url }, 30000); // yt-dlp can take ~10s
    if (data._noConfig) return { success: false, error: 'URL SongSurf non configurée.' };
    if (data._status === 401 || data._status === 503)
      return { success: false, error: 'Non authentifié — connecte-toi à SongSurf d\'abord.' };
    if (data.success) { setStatus('online'); return data; }
    return { success: false, error: data.error || `Erreur ${data._status}` };
  } catch {
    setStatus('offline');
    return { success: false, error: 'SongSurf injoignable.' };
  }
}

// Les titres restreints (âge/connexion) échouent côté yt-dlp dès que les cookies
// sont périmés : on resynchronise avant chaque mise en file, en attendant la fin.
// Jamais fatal — sans cookies frais, les titres non restreints passent quand même.
let lastCookieSyncAt = 0;
const COOKIE_SYNC_TTL_MS = 60 * 1000;

async function syncCookiesBeforeQueue() {
  if (Date.now() - lastCookieSyncAt < COOKIE_SYNC_TTL_MS) return;
  await getCookiesAndSend();
}

async function queueUrl(url, meta = {}) {
  await loadConfig();
  if (!songSurfUrl)
    return { success: false, error: 'URL SongSurf non configurée. Ouvre les options.' };
  if (serverStatus === 'offline')
    return { success: false, error: 'SongSurf est hors ligne.' };
  try {
    await syncCookiesBeforeQueue();
    const body = { url, ...meta };
    const data = await apiPost('/api/queue-direct', body, 10000);
    if (data._noConfig) return { success: false, error: 'URL SongSurf non configurée.' };
    if (data._status === 401 || data._status === 503)
      return { success: false, error: 'Non authentifié — connecte-toi à SongSurf d\'abord.' };
    if (data.success) { setStatus('online'); return { success: true, label: data.label, type: data.type }; }
    return { success: false, error: data.error || `Erreur ${data._status}` };
  } catch {
    setStatus('offline');
    return { success: false, error: 'SongSurf injoignable.' };
  }
}

async function getCookiesAndSend() {
  await loadConfig();
  if (!songSurfUrl)
    return { success: false, error: 'URL SongSurf non configurée. Ouvre les options.' };
  try {
    // Récupère tous les cookies YouTube (compte + session)
    const [ytCookies, ytmCookies] = await Promise.all([
      chrome.cookies.getAll({ domain: '.youtube.com' }),
      chrome.cookies.getAll({ domain: 'music.youtube.com' }),
    ]);

    // Déduplique par domain+name
    const seen = new Set();
    const all  = [];
    for (const c of [...ytCookies, ...ytmCookies]) {
      const key = `${c.domain}|${c.name}`;
      if (!seen.has(key)) { seen.add(key); all.push(c); }
    }

    if (!all.length)
      return { success: false, error: 'Aucun cookie YouTube trouvé — es-tu connecté ?' };

    // Format Netscape (attendu par yt-dlp)
    const lines = ['# Netscape HTTP Cookie File', '# Generated by SongSurf Clip', ''];
    for (const c of all) {
      const domain     = c.domain.startsWith('.') ? c.domain : `.${c.domain}`;
      const subdomains = c.domain.startsWith('.') ? 'TRUE' : 'FALSE';
      const secure     = c.secure ? 'TRUE' : 'FALSE';
      const expiry     = c.expirationDate ? Math.floor(c.expirationDate) : 0;
      lines.push(`${domain}\t${subdomains}\t${c.path}\t${secure}\t${expiry}\t${c.name}\t${c.value}`);
    }

    const r = await fetch(`${songSurfUrl}/api/cookies/update`, {
      method:      'POST',
      credentials: 'include',
      headers:     { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body:        JSON.stringify({ cookies: lines.join('\n') }),
      signal:      AbortSignal.timeout(10000),
    });
    const data = await r.json().catch(() => ({}));
    if (r.ok && data.success) {
      setStatus('online');
      lastCookieSyncAt = Date.now();
      return { success: true, count: all.length };
    }
    if (r.status === 401 || r.status === 503) return { success: false, error: 'Non authentifié — connecte-toi à SongSurf d\'abord.' };
    return { success: false, error: data.error || `Erreur ${r.status}` };
  } catch {
    return { success: false, error: 'SongSurf injoignable.' };
  }
}

async function queueBatch(items) {
  await loadConfig();
  if (!songSurfUrl)
    return { success: false, error: 'URL SongSurf non configurée. Ouvre les options.' };
  await syncCookiesBeforeQueue();
  let added = 0, failed = 0;
  for (const item of items) {
    // Accept both plain URL strings and {url, artist, album} objects
    const body = typeof item === 'string'
      ? { url: item }
      : { url: item.url, artist: item.artist || '', album: item.album || '' };
    try {
      const data = await apiPost('/api/queue-direct', body, 10000);
      if (data._status === 401 || data._status === 503)
        return { success: added > 0, added, failed: failed + (items.length - added - failed), error: 'Non authentifié — connecte-toi à SongSurf d\'abord.' };
      if (data.success) added++;
      else failed++;
    } catch {
      failed++;
    }
  }
  if (added > 0) setStatus('online');
  return { success: added > 0, added, failed };
}

// ── Message handler (from content.js and popup) ───────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'PREVIEW_URL') {
    previewUrl(msg.url).then(sendResponse);
    return true;
  }
  if (msg.type === 'QUEUE_URL') {
    queueUrl(msg.url, msg.meta || {}).then(sendResponse);
    return true;
  }
  if (msg.type === 'QUEUE_BATCH') {
    queueBatch(msg.items || msg.urls || []).then(sendResponse);
    return true;
  }
  if (msg.type === 'SYNC_COOKIES') {
    getCookiesAndSend().then(sendResponse);
    return true;
  }
  if (msg.type === 'GET_STATUS') {
    loadConfig().then(() => ping()).then(() => {
      sendResponse({ status: serverStatus, songSurfUrl });
    });
    return true;
  }
  if (msg.type === 'PING') {
    ping().then(() => sendResponse({ status: serverStatus }));
    return true;
  }
  if (msg.type === 'OPEN_SONGSURF') {
    loadConfig().then(() => {
      if (songSurfUrl) chrome.tabs.create({ url: songSurfUrl });
    });
    return false;
  }
});

// ── Alarms ────────────────────────────────────────────────────────────────────

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === PING_ALARM) ping();
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(PING_ALARM, { periodInMinutes: PING_MINUTES });
  ping();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(PING_ALARM, { periodInMinutes: PING_MINUTES });
  ping();
});
