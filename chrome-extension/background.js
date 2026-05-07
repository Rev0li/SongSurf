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

async function queueUrl(url) {
  await loadConfig();
  if (!songSurfUrl) {
    return { success: false, error: 'URL SongSurf non configurée. Ouvre les options.' };
  }
  if (serverStatus === 'offline') {
    return { success: false, error: 'SongSurf est hors ligne.' };
  }
  try {
    const r = await fetch(`${songSurfUrl}/api/queue-direct`, {
      method:      'POST',
      credentials: 'include',
      headers:     { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body:        JSON.stringify({ url }),
      signal:      AbortSignal.timeout(8000),
    });
    const data = await r.json();
    if (r.ok && data.success) {
      setStatus('online');
      return { success: true, label: data.label, type: data.type };
    }
    if (r.status === 401 || r.status === 503) {
      return { success: false, error: 'Non authentifié — connecte-toi à SongSurf d\'abord.' };
    }
    return { success: false, error: data.error || `Erreur ${r.status}` };
  } catch (e) {
    setStatus('offline');
    return { success: false, error: 'SongSurf injoignable.' };
  }
}

// ── Message handler (from content.js and popup) ───────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'QUEUE_URL') {
    queueUrl(msg.url).then(sendResponse);
    return true; // async response
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
