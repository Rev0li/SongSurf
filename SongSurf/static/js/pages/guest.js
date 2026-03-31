const GUEST_CFG = window.GUEST_CONFIG || {};
const MAX_SONGS = Number(GUEST_CFG.maxSongs || 0);

let expiresAt = new Date(GUEST_CFG.expiresAt || new Date().toISOString());
let currentMeta = null;
let isPlaylist = false;
let pollInterval = null;
let completed = [];
let playlistModeEnabled = false;
let expiryModalShown = false;
let tutoStep = 0;
let isDownloading = false;
let zipCountdownInterval = null;

const dlGroups = {};

function openTuto() {
	tutoStep = 0;
	_tutoRender();
	document.getElementById('tuto-overlay').classList.add('active');
}

function closeTuto() {
	document.getElementById('tuto-overlay').classList.remove('active');
	localStorage.setItem('songsurf_tuto_done', '1');
}

function tutoNext() {
	tutoStep = 1;
	_tutoRender();
}

function tutoPrev() {
	tutoStep = 0;
	_tutoRender();
}

function _tutoRender() {
	[0, 1].forEach((i) => {
		document.getElementById(`tuto-screen-${i}`).classList.toggle('active', i === tutoStep);
		document.getElementById(`tuto-dot-${i}`).classList.toggle('active', i === tutoStep);
	});
}

function onPlaylistModeChange() {
	playlistModeEnabled = document.getElementById('toggle-playlist-mode').checked;
}

const WARN_SECONDS = 5 * 60;

function updateTimer() {
	const now = new Date();
	const diff = Math.max(0, Math.floor((expiresAt - now) / 1000));
	const h = Math.floor(diff / 3600);
	const m = Math.floor((diff % 3600) / 60);
	const s = diff % 60;

	const timer = document.getElementById('timer');
	if (timer) {
		timer.textContent = h > 0
			? `${h}h ${String(m).padStart(2, '0')}min`
			: `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	}

	if (document.getElementById('expiry-modal').classList.contains('active')) {
		document.getElementById('modal-countdown').textContent = h > 0
			? `${h}h ${String(m).padStart(2, '0')}min`
			: `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	}

	if (!expiryModalShown && diff > 0 && diff <= WARN_SECONDS) {
		expiryModalShown = true;
		document.getElementById('expiry-modal').classList.add('active');
	}

	if (diff === 0) {
		document.getElementById('expiry-modal').classList.remove('active');
		showAlert('⏱️ Votre session a expiré. Reconnectez-vous.', 'info');
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
		}
	}
}

async function extendSession() {
	const btn = document.getElementById('btn-extend');
	btn.disabled = true;
	btn.textContent = '⏳ Prolongation...';
	try {
		const res = await fetch('/api/guest/extend-session', { method: 'POST' });
		const data = await res.json();
		if (data.success) {
			expiresAt = new Date(data.expires_at);
			expiryModalShown = false;
			document.getElementById('expiry-modal').classList.remove('active');
			showAlert('✅ Session prolongée d\'une heure !', 'info');
		} else {
			showAlert(data.error || 'Impossible de prolonger la session.');
			document.getElementById('expiry-modal').classList.remove('active');
		}
	} catch (e) {
		showAlert('Erreur réseau lors de la prolongation.');
	} finally {
		btn.disabled = false;
		btn.innerHTML = '✅ Continuer<br><small style="font-weight:400;font-size:11px;">Prolonger d\'1 heure</small>';
	}
}

function leaveSession() {
	document.getElementById('expiry-modal').classList.remove('active');
	const zipZone = document.getElementById('zip-zone');
	if (zipZone.style.display === 'none' || zipZone.style.display === '') {
		showAlert('📦 Aucune musique téléchargée. Téléchargez d\'abord une musique pour obtenir un ZIP.', 'info');
		return;
	}
	zipZone.scrollIntoView({ behavior: 'smooth', block: 'center' });
	setTimeout(() => prepareAndDownloadZip(), 400);
}

function showAlert(msg, type = 'error') {
	const zone = document.getElementById('alert-zone');
	if (!zone) return;
	zone.innerHTML = `<div class="alert alert-${type}">${msg}</div>`;
	setTimeout(() => {
		zone.innerHTML = '';
	}, 5000);
}

function setDownloadingState(active) {
	isDownloading = active;
	const btnExtract = document.getElementById('btn-extract');
	const btnZip = document.getElementById('btn-prepare-zip');
	if (btnExtract) btnExtract.disabled = active;
	if (btnZip) btnZip.disabled = active;
}

async function extractUrl() {
	const url = document.getElementById('url-input').value.trim();
	if (!url) return showAlert('Collez un lien YouTube Music.');

	document.getElementById('btn-extract').disabled = true;
	document.getElementById('btn-extract').textContent = '⏳';
	document.getElementById('metadata-preview').style.display = 'none';

	try {
		const res = await fetch('/api/guest/extract', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ url }),
		});
		const data = await res.json();
		if (!data.success) return showAlert(data.error || 'Erreur extraction.');

		const meta = data.metadata ? { ...data, ...data.metadata } : data;
		currentMeta = meta;

		const thumbEl = document.getElementById('meta-thumb');
		const thumbCandidates = [];
		const pushThumb = (u) => {
			if (!u || typeof u !== 'string') return;
			const clean = u.trim();
			if (!clean) return;
			if (!thumbCandidates.includes(clean)) thumbCandidates.push(clean);
		};

		pushThumb(meta.thumbnail_url || '');
		if (Array.isArray(meta.thumbnail_candidates)) meta.thumbnail_candidates.forEach(pushThumb);

		const fromUrl = (val) => {
			const raw = String(val || '');
			const m = raw.match(/[?&]v=([^&]+)/i);
			return m && m[1] ? m[1] : '';
		};

		const firstSong = Array.isArray(meta.songs) && meta.songs.length ? meta.songs[0] : null;
		const firstId = (firstSong && (firstSong.id || fromUrl(firstSong.url || ''))) || '';
		if (firstId) {
			pushThumb(`https://i.ytimg.com/vi/${firstId}/hqdefault.jpg`);
			pushThumb(`https://i.ytimg.com/vi/${firstId}/mqdefault.jpg`);
		}

		const shouldCacheBust = (u) => {
			const raw = String(u || '');
			if (!raw) return false;
			if (/\/s_p\//i.test(raw)) return false;
			if (/[?&](?:rs|sqp)=/i.test(raw)) return false;
			return true;
		};

		let thumbIdx = 0;
		const showNextThumb = () => {
			if (thumbIdx >= thumbCandidates.length) {
				thumbEl.removeAttribute('src');
				thumbEl.style.display = 'none';
				return;
			}
			const base = thumbCandidates[thumbIdx++];
			if (shouldCacheBust(base)) {
				const sep = base.includes('?') ? '&' : '?';
				thumbEl.src = `${base}${sep}t=${Date.now()}_${thumbIdx}`;
			} else {
				thumbEl.src = base;
			}
		};

		thumbEl.onload = () => {
			thumbEl.style.display = 'block';
		};
		thumbEl.onerror = () => {
			showNextThumb();
		};
		showNextThumb();

		if (meta.songs) {
			isPlaylist = true;
			document.getElementById('meta-fields-single').style.display = 'none';
			document.getElementById('meta-fields-playlist').style.display = 'flex';
			document.getElementById('playlist-title-display').textContent = `💿 ${meta.songs.length} chanson(s) détectée(s)`;
			document.getElementById('playlist-info').style.display = 'none';
			document.getElementById('btn-dl').textContent = '⬇️ Tout télécharger';

			document.getElementById('edit-playlist-artist').value = meta.artist || '';
			document.getElementById('edit-playlist-album').value = meta.title || '';
			document.getElementById('edit-playlist-year').value = meta.year || '';

			if (MAX_SONGS > 0) {
				const already = parseInt(document.getElementById('pill-songs-val').textContent, 10) || 0;
				const free = MAX_SONGS - already;
				if (meta.songs.length > free) {
					document.getElementById('playlist-info').style.display = 'block';
					document.getElementById('playlist-msg').textContent = `⚠️ Quota: seulement ${free} chanson(s) seront ajoutées.`;
				}
			}
		} else {
			isPlaylist = false;
			document.getElementById('meta-fields-single').style.display = 'flex';
			document.getElementById('meta-fields-playlist').style.display = 'none';
			document.getElementById('playlist-info').style.display = 'none';
			document.getElementById('btn-dl').textContent = '⬇️ Télécharger';

			document.getElementById('edit-title').value = meta.title || '';
			document.getElementById('edit-artist').value = meta.artist || '';
			document.getElementById('edit-album').value = meta.album || '';
		}

		document.getElementById('metadata-preview').style.display = 'block';
	} catch (e) {
		showAlert('Erreur réseau.');
	} finally {
		document.getElementById('btn-extract').disabled = isDownloading;
		document.getElementById('btn-extract').textContent = 'Analyser';
	}
}

function resetPreview() {
	document.getElementById('metadata-preview').style.display = 'none';
	document.getElementById('url-input').value = '';
	document.getElementById('edit-title').value = '';
	document.getElementById('edit-artist').value = '';
	document.getElementById('edit-album').value = '';
	document.getElementById('edit-playlist-artist').value = '';
	document.getElementById('edit-playlist-album').value = '';
	document.getElementById('edit-playlist-year').value = '';
	currentMeta = null;
}

async function addToQueue() {
	if (!currentMeta) return;
	document.getElementById('btn-dl').disabled = true;

	try {
		let res;
		let data;
		if (isPlaylist) {
			const playlistArtist = document.getElementById('edit-playlist-artist').value.trim() || currentMeta.artist || '';
			const playlistAlbum = document.getElementById('edit-playlist-album').value.trim() || currentMeta.title || '';
			const playlistYear = document.getElementById('edit-playlist-year').value.trim() || currentMeta.year || '';

			const updatedMeta = {
				...currentMeta,
				artist: playlistArtist,
				title: playlistAlbum,
				year: playlistYear,
			};

			res = await fetch('/api/guest/download-playlist', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ playlist_metadata: updatedMeta, playlist_mode: playlistModeEnabled }),
			});
			data = await res.json();
			if (!data.success) return showAlert(data.error);
			showAlert(`✅ ${data.added} chanson(s) ajoutée(s) à la queue.`, 'info');
			if (data.skipped > 0) showAlert(`⚠️ ${data.skipped} chanson(s) ignorée(s) (quota atteint).`);
		} else {
			const title = document.getElementById('edit-title').value.trim() || currentMeta.title || 'Unknown Title';
			const artist = document.getElementById('edit-artist').value.trim() || currentMeta.artist || 'Unknown Artist';
			const album = document.getElementById('edit-album').value.trim() || currentMeta.album || 'Unknown Album';

			res = await fetch('/api/guest/download', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					url: document.getElementById('url-input').value.trim(),
					title,
					artist,
					album,
					year: currentMeta.year || '',
					playlist_mode: playlistModeEnabled,
				}),
			});
			data = await res.json();
			if (!data.success) return showAlert(data.error);
			showAlert(`✅ "${title}" ajouté à la queue.`, 'info');
		}

		resetPreview();
		setDownloadingState(true);
		startPolling();
	} finally {
		document.getElementById('btn-dl').disabled = false;
	}
}

function startPolling() {
	if (pollInterval) return;
	pollInterval = setInterval(pollStatus, 1500);
	pollStatus();
}

async function pollStatus() {
	try {
		const res = await fetch('/api/guest/status');
		if (!res.ok) return;
		const data = await res.json();

		const songs = data.songs_downloaded || 0;
		const max = MAX_SONGS > 0 ? MAX_SONGS : 0;
		document.getElementById('pill-songs-val').textContent = max > 0 ? `${songs} / ${max}` : `${songs}`;
		document.getElementById('pill-queue-val').textContent = data.queue_size || 0;

		if (max > 0) {
			const pct = Math.min(100, Math.round((songs / max) * 100));
			document.getElementById('quota-fill').style.width = `${pct}%`;
			document.getElementById('quota-fill').classList.toggle('full', pct >= 100);
			document.getElementById('quota-text').textContent = `${songs} / ${max}`;
		}

		const busy = data.in_progress || data.queue_size > 0;
		setDownloadingState(busy);
		const prog = data.in_progress && data.progress;
		document.getElementById('progress-zone').style.display = prog ? 'block' : 'none';
		if (prog) {
			const p = data.progress;
			const meta = data.current_download && data.current_download.metadata;
			document.getElementById('prog-title').textContent = meta ? `${meta.artist} - ${meta.title}` : '...';
			document.getElementById('prog-status').textContent = p.status === 'processing' ? 'Conversion en MP3...' : 'Téléchargement...';
			document.getElementById('prog-bar').style.width = `${p.percent || 0}%`;
			document.getElementById('prog-pct').textContent = `${p.percent || 0}%`;
			document.getElementById('prog-speed').textContent = p.speed || '';
			document.getElementById('prog-eta').textContent = p.eta ? `ETA: ${p.eta}` : '';
		}

		if (data.last_completed && data.last_completed.success) {
			const lc = data.last_completed;
			const key = lc.timestamp;
			if (!completed.includes(key)) {
				completed.push(key);
				addDlItem(lc.metadata);
				document.getElementById('zip-zone').style.display = 'block';
				document.getElementById('zip-state-idle').style.display = 'block';
				document.getElementById('zip-state-preparing').style.display = 'none';
				document.getElementById('zip-state-done').style.display = 'none';
			}
		}
	} catch (e) {
		// ignore polling errors
	}
}

function _esc(s) {
	return String(s || '')
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}

function toggleGroup(key) {
	const g = dlGroups[key];
	if (g) g.groupEl.classList.toggle('open');
}

function addDlItem(meta) {
	document.getElementById('dl-empty').style.display = 'none';

	const groupKey = meta.album || meta.artist || 'Inconnu';
	const groupIcon = meta.album ? '💿' : '🎵';
	const groupLabel = groupKey;
	const subLabel = meta.artist || '';

	if (!dlGroups[groupKey]) {
		const groupEl = document.createElement('div');
		groupEl.className = 'dl-group open';
		groupEl.id = `dlg-${groupKey.replace(/[^a-z0-9]/gi, '_')}`;

		const songsEl = document.createElement('ul');
		songsEl.className = 'dl-group-songs';

		groupEl.innerHTML = `
			<div class="dl-group-header" onclick="toggleGroup(${JSON.stringify(groupKey)})">
				<span class="dl-group-icon">${groupIcon}</span>
				<div class="dl-group-info">
					<span class="dl-group-title">${_esc(groupLabel)}</span>
					<span class="dl-group-meta">${_esc(subLabel)} · <span id="dlg-count-${groupEl.id}">0</span> chanson(s)</span>
				</div>
				<span class="dl-group-chevron">▼</span>
			</div>
		`;

		groupEl.appendChild(songsEl);
		document.getElementById('dl-list').appendChild(groupEl);
		dlGroups[groupKey] = { groupEl, songsEl, count: 0 };
	}

	const g = dlGroups[groupKey];
	g.count += 1;

	const countEl = g.groupEl.querySelector('[id^="dlg-count-"]');
	if (countEl) countEl.textContent = g.count;

	const li = document.createElement('li');
	li.className = 'dl-item';
	li.innerHTML = `
		<span class="icon">♪</span>
		<span class="name">${_esc(meta.title || meta.artist)}</span>
		<span class="ok">✓</span>
	`;
	g.songsEl.appendChild(li);
}

async function prepareAndDownloadZip() {
	document.getElementById('zip-state-idle').style.display = 'none';
	document.getElementById('zip-state-preparing').style.display = 'block';
	document.getElementById('zip-state-done').style.display = 'none';

	let attempts = 0;
	while (attempts < 60) {
		try {
			const res = await fetch('/api/guest/status');
			const data = await res.json();
			if (!data.in_progress && data.queue_size === 0) break;
		} catch (e) {}
		await new Promise((r) => setTimeout(r, 2000));
		attempts += 1;
	}

	let zipData;
	try {
		const res = await fetch('/api/guest/prepare-zip', { method: 'POST' });
		zipData = await res.json();
	} catch (e) {
		_resetZipState();
		showAlert('Erreur réseau lors de la préparation du ZIP.');
		return;
	}

	if (!zipData.success) {
		_resetZipState();
		showAlert(zipData.error || 'Erreur lors de la création du ZIP.');
		return;
	}

	_triggerZipDownload();
	document.getElementById('zip-state-preparing').style.display = 'none';
	document.getElementById('zip-state-done').style.display = 'block';
	document.getElementById('zip-info-text').textContent = `${zipData.file_count} fichier(s) · ${zipData.size_mb} MB`;

	_lockUIAfterZip();

	let remaining = 900;
	_updateZipCountdown(remaining);
	zipCountdownInterval = setInterval(() => {
		remaining -= 1;
		_updateZipCountdown(remaining);
		if (remaining <= 0) {
			clearInterval(zipCountdownInterval);
			window.location.href = '/guest/login';
		}
	}, 1000);
}

function _updateZipCountdown(sec) {
	const m = Math.floor(sec / 60);
	const s = sec % 60;
	const el = document.getElementById('zip-countdown');
	if (el) el.textContent = `${m}:${String(s).padStart(2, '0')}`;
}

function _triggerZipDownload() {
	const a = document.createElement('a');
	a.href = '/api/guest/download-zip';
	a.download = 'SongSurf_musiques.zip';
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
}

function _resetZipState() {
	document.getElementById('zip-state-idle').style.display = 'block';
	document.getElementById('zip-state-preparing').style.display = 'none';
	document.getElementById('zip-state-done').style.display = 'none';
}

function _lockUIAfterZip() {
	document.getElementById('btn-extract').disabled = true;
	const btnDl = document.getElementById('btn-dl');
	if (btnDl) btnDl.disabled = true;
	const urlInput = document.getElementById('url-input');
	urlInput.disabled = true;
	urlInput.placeholder = 'Session en cours de fermeture...';
	if (pollInterval) {
		clearInterval(pollInterval);
		pollInterval = null;
	}
}

function closeSessionNow() {
	if (zipCountdownInterval) clearInterval(zipCountdownInterval);
	window.location.href = '/guest/logout';
}

window.openTuto = openTuto;
window.closeTuto = closeTuto;
window.tutoNext = tutoNext;
window.tutoPrev = tutoPrev;
window.onPlaylistModeChange = onPlaylistModeChange;
window.extractUrl = extractUrl;
window.resetPreview = resetPreview;
window.addToQueue = addToQueue;
window.toggleGroup = toggleGroup;
window.prepareAndDownloadZip = prepareAndDownloadZip;
window.closeSessionNow = closeSessionNow;
window.extendSession = extendSession;
window.leaveSession = leaveSession;

document.addEventListener('DOMContentLoaded', () => {
	if (!localStorage.getItem('songsurf_tuto_done')) openTuto();

	setInterval(updateTimer, 1000);
	updateTimer();

	const input = document.getElementById('url-input');
	if (input) {
		input.addEventListener('keydown', (e) => {
			if (e.key === 'Enter') extractUrl();
		});
	}

	startPolling();
});
