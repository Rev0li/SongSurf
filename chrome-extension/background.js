// SongSurf Clip — background service worker
// Handles: API calls to SongSurf, periodic ping, icon badge

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
    chrome.action.setBadgeText({ text: '!' });
    chrome.action.setBadgeBackgroundColor({ color: '#e53e3e' });
  } else if (serverStatus === 'online') {
    chrome.action.setBadgeText({ text: '' });
  } else {
    chrome.action.setBadgeText({ text: '?' });
    chrome.action.setBadgeBackgroundColor({ color: '#718096' });
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

async function queueUrl(url, meta = {}) {
  await loadConfig();
  if (!songSurfUrl)
    return { success: false, error: 'URL SongSurf non configurée. Ouvre les options.' };
  if (serverStatus === 'offline')
    return { success: false, error: 'SongSurf est hors ligne.' };
  try {
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
