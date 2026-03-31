(function () {
	const cfg = window.GUEST_CONFIG || {};
	const maxSongs = Number(cfg.maxSongs || 0);
	let expiresAt = new Date(cfg.expiresAt || new Date().toISOString());
	let expiryModalShown = false;
	let lastSessionPoll = 0;

	function byId(id) {
		return document.getElementById(id);
	}

	function openTuto() {
		const overlay = byId('tuto-overlay');
		if (!overlay) return;
		setTutoStep(0);
		overlay.classList.add('active');
	}

	function closeTuto() {
		const overlay = byId('tuto-overlay');
		if (!overlay) return;
		overlay.classList.remove('active');
		localStorage.setItem('songsurf_tuto_done', '1');
	}

	function setTutoStep(step) {
		const s0 = byId('tuto-screen-0');
		const s1 = byId('tuto-screen-1');
		const d0 = byId('tuto-dot-0');
		const d1 = byId('tuto-dot-1');
		const isFirst = step === 0;
		if (s0) s0.classList.toggle('active', isFirst);
		if (s1) s1.classList.toggle('active', !isFirst);
		if (d0) d0.classList.toggle('active', isFirst);
		if (d1) d1.classList.toggle('active', !isFirst);
	}

	function formatTimer(diff) {
		const h = Math.floor(diff / 3600);
		const m = Math.floor((diff % 3600) / 60);
		const s = diff % 60;
		if (h > 0) return h + 'h ' + String(m).padStart(2, '0') + 'min';
		return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
	}

	function updateTimer() {
		const now = new Date();
		const diff = Math.max(0, Math.floor((expiresAt - now) / 1000));

		const timer = byId('timer');
		if (timer) timer.textContent = formatTimer(diff);

		const modal = byId('expiry-modal');
		const modalCount = byId('modal-countdown');
		if (modal && modal.classList.contains('active') && modalCount) {
			modalCount.textContent = formatTimer(diff);
		}

		if (!expiryModalShown && diff > 0 && diff <= 5 * 60) {
			expiryModalShown = true;
			if (modal) modal.classList.add('active');
		}

		if (diff === 0) {
			window.location.href = '/guest/login';
		}
	}

	function updateSessionPills(st) {
		const songs = Number(st.songs_downloaded || 0);
		const queue = Number(st.queue_size || 0);

		const songsEl = byId('pill-songs-val');
		if (songsEl) songsEl.textContent = maxSongs > 0 ? (songs + ' / ' + maxSongs) : String(songs);

		const queueEl = byId('pill-queue-val');
		if (queueEl) queueEl.textContent = String(queue);

		if (maxSongs > 0) {
			const pct = Math.min(100, Math.round((songs / maxSongs) * 100));
			const fill = byId('quota-fill');
			const text = byId('quota-text');
			if (fill) {
				fill.style.width = pct + '%';
				fill.classList.toggle('full', pct >= 100);
			}
			if (text) text.textContent = songs + ' / ' + maxSongs;
		}
	}

	async function pollSessionStatus() {
		const now = Date.now();
		if (now - lastSessionPoll < 2500) return;
		lastSessionPoll = now;
		try {
			const res = await fetch('/api/guest/status', { credentials: 'same-origin' });
			if (!res.ok) return;
			const st = await res.json();
			if (st && st.expires_at) {
				expiresAt = new Date(st.expires_at);
			}
			updateSessionPills(st || {});
		} catch (_) {
			// Ignore polling hiccups.
		}
	}

	async function extendSession() {
		const btn = byId('btn-extend');
		if (btn) {
			btn.disabled = true;
			btn.textContent = '⏳ Prolongation...';
		}
		try {
			const res = await fetch('/api/guest/extend-session', { method: 'POST', credentials: 'same-origin' });
			const data = await res.json();
			if (data && data.success && data.expires_at) {
				expiresAt = new Date(data.expires_at);
				expiryModalShown = false;
				const modal = byId('expiry-modal');
				if (modal) modal.classList.remove('active');
			}
		} catch (_) {
			// ignore network error
		} finally {
			if (btn) {
				btn.disabled = false;
				btn.textContent = '✅ Continuer';
			}
		}
	}

	function leaveSession() {
		const modal = byId('expiry-modal');
		if (modal) modal.classList.remove('active');
		if (typeof window.downloadRecentFiles === 'function') {
			window.downloadRecentFiles();
			return;
		}
		window.location.href = '/guest/logout';
	}

	window.openTuto = openTuto;
	window.closeTuto = closeTuto;
	window.tutoNext = function () { setTutoStep(1); };
	window.tutoPrev = function () { setTutoStep(0); };
	window.extendSession = extendSession;
	window.leaveSession = leaveSession;

	document.addEventListener('DOMContentLoaded', function () {
		if (!localStorage.getItem('songsurf_tuto_done')) {
			openTuto();
		}
		setInterval(updateTimer, 1000);
		setInterval(pollSessionStatus, 3000);
		updateTimer();
		pollSessionStatus();
	});
})();
