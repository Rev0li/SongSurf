// SongSurf Clip — popup script

const pill       = document.getElementById('status-pill');
const pillText   = document.getElementById('status-text');
const noConfig   = document.getElementById('no-config');
const main       = document.getElementById('main');
const offlineHint = document.getElementById('offline-hint');

function applyStatus(status) {
  pill.className = `status-pill ${status}`;
  const labels = { online: 'En ligne', offline: 'Hors ligne', unknown: 'Inconnu' };
  pillText.textContent = labels[status] || '…';
  offlineHint.style.display = status === 'offline' ? 'block' : 'none';
}

// Listen for live updates pushed by background
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'STATUS_UPDATE') applyStatus(msg.status);
});

// Initial state
chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
  if (!res) return;
  const configured = !!res.songSurfUrl;
  noConfig.style.display = configured ? 'none'  : 'block';
  main.style.display     = configured ? 'block' : 'none';
  if (configured) applyStatus(res.status);
});

// Buttons
document.getElementById('btn-open-songsurf')?.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'OPEN_SONGSURF' });
  window.close();
});

document.getElementById('btn-options')?.addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
  window.close();
});

document.getElementById('btn-open-options')?.addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
  window.close();
});

// Sync cookies
const syncBtn    = document.getElementById('btn-sync-cookies');
const syncStatus = document.getElementById('sync-status');

function showSyncStatus(msg, isError = false) {
  syncStatus.style.display = 'block';
  syncStatus.style.color   = isError ? '#f87171' : '#34d399';
  syncStatus.textContent   = msg;
  setTimeout(() => { syncStatus.style.display = 'none'; }, 4000);
}

// Compte SongSurf de la dernière synchro (les cookies sont rangés par utilisateur).
const syncAccount = document.getElementById('sync-account');

async function showSyncAccount() {
  const { last_cookie_sync: last } = await chrome.storage.local.get('last_cookie_sync');
  if (!syncAccount || !last?.pseudo) return;
  const when = new Date(last.at).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
  syncAccount.textContent   = `🍪 Cookies synchronisés pour ${last.pseudo} · ${when}`;
  syncAccount.style.display = 'block';
}
showSyncAccount();

syncBtn?.addEventListener('click', async () => {
  syncBtn.disabled    = true;
  syncBtn.textContent = '⏳ Synchronisation…';

  chrome.runtime.sendMessage({ type: 'SYNC_COOKIES' }, (res) => {
    syncBtn.disabled    = false;
    syncBtn.textContent = '🍪 Sync cookies YouTube';
    if (res && res.success) {
      showSyncStatus(`✓ ${res.count} cookies envoyés${res.pseudo ? ` pour ${res.pseudo}` : ''}`);
      showSyncAccount();
    } else {
      showSyncStatus(res?.error || 'Erreur inconnue', true);
    }
  });
});
