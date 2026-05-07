// SongSurf Clip — options script

const urlInput  = document.getElementById('url-input');
const btnSave   = document.getElementById('btn-save');
const btnTest   = document.getElementById('btn-test');
const statusMsg = document.getElementById('status-msg');
const pingDot   = document.getElementById('ping-dot');
const pingLabel = document.getElementById('ping-label');

// ── Load saved config ─────────────────────────────────────────────────────────

chrome.storage.sync.get('songsurf_url', ({ songsurf_url }) => {
  if (songsurf_url) urlInput.value = songsurf_url;
  refreshStatus();
});

// ── Save ──────────────────────────────────────────────────────────────────────

btnSave.addEventListener('click', () => {
  const raw = urlInput.value.trim().replace(/\/$/, '');
  if (!raw) {
    showMsg('❌ URL requise.', 'error');
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
  const url = urlInput.value.trim().replace(/\/$/, '');
  if (!url) { showMsg('❌ Saisis l\'URL d\'abord.', 'error'); return; }

  btnTest.disabled = true;
  btnTest.textContent = '…';
  showMsg('', '');

  try {
    const r = await fetch(`${url}/ping`, {
      credentials: 'include',
      signal: AbortSignal.timeout(5000),
    });
    if (r.ok) {
      showMsg('✅ SongSurf répond correctement.', 'success');
      applyStatus('online');
    } else {
      showMsg(`⚠️ Réponse inattendue : ${r.status}`, 'error');
      applyStatus('offline');
    }
  } catch {
    showMsg('❌ Impossible de joindre SongSurf. Vérifie l\'URL et ta connexion Tailscale.', 'error');
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
