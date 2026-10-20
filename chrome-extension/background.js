// SongSurf Clip — background script (MV2 Firefox + MV3 Chrome)
// Handles: API calls to SongSurf, periodic ping, icon badge

const action = chrome.action || chrome.browserAction;

const PING_ALARM   = 'songsurf-ping';
const PING_MINUTES = 0.5; // every 30 seconds

// Used when no URL is set in the options page (override for dev / self-hosting)
const DEFAULT_SONGSURF_URL = 'https://songsurf.rev0li.duckdns.org';

// ── State ─────────────────────────────────────────────────────────────────────

let songSurfUrl  = '';
let serverStatus = 'unknown'; // 'online' | 'offline' | 'unauth' | 'unknown'

async function loadConfig() {
  const { songsurf_url } = await chrome.storage.sync.get('songsurf_url');
  songSurfUrl = (songsurf_url || DEFAULT_SONGSURF_URL).replace(/\/$/, '');
}

// ── Réponses de la porte du portail ───────────────────────────────────────────
// Devant SongSurf, Caddy vérifie la session du portail : sans session il répond
// 401 ou redirige vers la page de connexion du portail (autre origine). Quand
// SongSurf dort, le Watcher redirige vers sa page de chargement.

const ERR_LOGIN     = 'Non connecté — clique ici pour ouvrir SongSurf et te connecter.';
const ERR_OFFLINE   = 'SongSurf injoignable — clique ici pour ouvrir SongSurf (connexion ?).';
const ERR_WAKING    = 'SongSurf démarre — réessaie dans quelques secondes.';
const ERR_FORBIDDEN = 'Ton compte n\'a pas accès à SongSurf.';

function responseIssue(r) {
  if (r.status === 401) return 'login';
  if (r.redirected) {
    const u = new URL(r.url);
    if (u.origin !== new URL(songSurfUrl).origin) return 'login';
    if (u.pathname.startsWith('/watcher/loading')) return 'waking';
  }
  // 403 de la porte (session sans accès SongSurf) : pas du JSON SongSurf
  if (r.status === 403 && !(r.headers.get('Content-Type') || '').includes('json')) return 'forbidden';
  return null;
}

function issueError(issue) {
  if (issue === 'login') {
    setStatus('unauth');
    return { success: false, error: ERR_LOGIN, needsLogin: true };
  }
  if (issue === 'waking')    return { success: false, error: ERR_WAKING };
  if (issue === 'forbidden') return { success: false, error: ERR_FORBIDDEN };
  return null;
}

function offlineError() {
  setStatus('offline');
  return { success: false, error: ERR_OFFLINE, needsLogin: true };
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
    if (responseIssue(r) === 'login') setStatus('unauth');
    else setStatus(r.ok ? 'online' : 'offline');
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
  } else if (serverStatus === 'unauth') {
    action.setBadgeText({ text: '!' });
    action.setBadgeBackgroundColor({ color: '#dd6b20' });
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
  return { _status: r.status, _issue: responseIssue(r), ...data };
}

async function previewUrl(url) {
  await loadConfig();
  if (!songSurfUrl)
    return { success: false, error: 'URL SongSurf non configurée. Ouvre les options.' };
  try {
    const data = await apiPost('/api/preview', { url }, 30000); // yt-dlp can take ~10s
    if (data._noConfig) return { success: false, error: 'URL SongSurf non configurée.' };
    const issue = issueError(data._issue);
    if (issue) return issue;
    if (data.success) { setStatus('online'); return data; }
    return { success: false, error: data.error || `Erreur ${data._status}` };
  } catch {
    return offlineError();
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
  if (serverStatus === 'unauth') return issueError('login');
  if (serverStatus === 'offline') return offlineError();
  try {
    await syncCookiesBeforeQueue();
    const body = { url, ...meta };
    const data = await apiPost('/api/queue-direct', body, 10000);
    if (data._noConfig) return { success: false, error: 'URL SongSurf non configurée.' };
    const issue = issueError(data._issue);
    if (issue) return issue;
    if (data.success) { setStatus('online'); return { success: true, label: data.label, type: data.type }; }
    return { success: false, error: data.error || `Erreur ${data._status}` };
  } catch {
    return offlineError();
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
      // Les cookies sont rangés par compte SongSurf : on retient lequel pour le popup.
      await chrome.storage.local.set({ last_cookie_sync: { pseudo: data.pseudo || '', at: lastCookieSyncAt } });
      return { success: true, count: all.length, pseudo: data.pseudo || '' };
    }
    const issue = issueError(responseIssue(r));
    if (issue) return issue;
    return { success: false, error: data.error || `Erreur ${r.status}` };
  } catch {
    return offlineError();
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
      const issue = issueError(data._issue);
      if (issue)
        return { ...issue, success: added > 0, added, failed: failed + (items.length - added - failed) };
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
