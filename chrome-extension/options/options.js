// SongSurf Clip — options script

// Keep in sync with DEFAULT_SONGSURF_URL in background.js
const DEFAULT_SONGSURF_URL = 'https://songsurf.rev0li.duckdns.org';

const urlInput  = document.getElementById('url-input');
const btnSave   = document.getElementById('btn-save');
const btnTest   = document.getElementById('btn-test');
const statusMsg = document.getElementById('status-msg');
const pingDot   = document.getElementById('ping-dot');
const pingLabel = document.getElementById('ping-label');

urlInput.placeholder = DEFAULT_SONGSURF_URL;

// ── Load saved config ─────────────────────────────────────────────────────────

chrome.storage.sync.get('songsurf_url', ({ songsurf_url }) => {
  if (songsurf_url) urlInput.value = songsurf_url;
  refreshStatus();
});

// ── Save ──────────────────────────────────────────────────────────────────────

btnSave.addEventListener('click', () => {
  const raw = urlInput.value.trim().replace(/\/$/, '');
  if (!raw) {
    chrome.storage.sync.remove('songsurf_url', () => {
      showMsg('✅ URL par défaut rétablie.', 'success');
      setTimeout(refreshStatus, 300);
    });
    return;
  }
  try { new URL(raw); } catch {
    showMsg('❌ URL invalide.', 'error');
    return;
  }
  chrome.storage.sync.set({ songsurf_url: raw }, () => {
    showMsg('✅ Enregistré.', 'success');
    setTimeout(refreshStatus, 300);
  });
});

// ── Test connection ───────────────────────────────────────────────────────────

btnTest.addEventListener('click', async () => {
  const url = urlInput.value.trim().replace(/\/$/, '') || DEFAULT_SONGSURF_URL;

  btnTest.disabled = true;
  btnTest.textContent = '…';
  showMsg('', '');

  try {
    const r = await fetch(`${url}/ping`, {
      credentials: 'include',
      signal: AbortSignal.timeout(5000),
    });
    // Porte du portail : 401, ou redirection vers la connexion (autre origine)
    if (r.status === 401 || (r.redirected && new URL(r.url).origin !== new URL(url).origin)) {
      showMsg('🔐 SongSurf répond, mais tu n\'es pas connecté : ouvre SongSurf pour te connecter au portail.', 'error');
      applyStatus('unauth');
    } else if (r.ok) {
      showMsg('✅ SongSurf répond correctement.', 'success');
      applyStatus('online');
    } else {
      showMsg(`⚠️ Réponse inattendue : ${r.status}`, 'error');
      applyStatus('offline');
    }
  } catch {
    showMsg('❌ Impossible de joindre SongSurf. Vérifie l\'URL et ta connexion.', 'error');
    applyStatus('offline');
  } finally {
    btnTest.disabled = false;
    btnTest.textContent = 'Tester la connexion';
  }
});

// ── Status ────────────────────────────────────────────────────────────────────

function refreshStatus() {
  chrome.runtime.sendMessage({ type: 'PING' }, (res) => {
    if (res) applyStatus(res.status);
  });
}

function applyStatus(status) {
  pingDot.className = `ping-dot ${status}`;
  const labels = {
    online:  'SongSurf est en ligne ✓',
    offline: 'SongSurf est hors ligne',
    unauth:  'Non connecté au portail',
    unknown: 'Statut inconnu',
  };
  pingLabel.textContent = labels[status] || 'Statut inconnu';
}

function showMsg(text, type) {
  statusMsg.textContent = text;
  statusMsg.className   = type;
}

// Live status updates from background
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'STATUS_UPDATE') applyStatus(msg.status);
});
