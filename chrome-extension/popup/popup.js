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
