(function () {
	var modal = null;
	var timerEl = null;
	var isVisible = false;
	var countdown = 0;
	var countdownHandle = null;
	var pollHandle = null;
	var lastUserKeepaliveAt = 0;
	var logoutUrl = '/logout';
	var loginUrl = '/administrator';

	function createModal() {
		if (modal) return;

		var style = document.createElement('style');
		style.textContent = [
			'.watcher-idle-overlay{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:9999;}',
			'.watcher-idle-box{width:min(92vw,460px);background:#12131a;color:#fff;border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.45);}',
			'.watcher-idle-title{font-size:20px;font-weight:700;margin-bottom:8px;}',
			'.watcher-idle-text{opacity:.88;line-height:1.45;margin-bottom:12px;}',
			'.watcher-idle-timer{font-size:28px;font-weight:800;letter-spacing:.5px;margin:8px 0 16px;color:#ffb547;}',
			'.watcher-idle-actions{display:flex;gap:10px;justify-content:flex-end;}',
			'.watcher-idle-btn{border:0;border-radius:10px;padding:10px 14px;font-weight:600;cursor:pointer;}',
			'.watcher-idle-btn.primary{background:#16a34a;color:#fff;}'
		].join('');
		document.head.appendChild(style);

		modal = document.createElement('div');
		modal.className = 'watcher-idle-overlay';
		modal.innerHTML = '' +
			'<div class="watcher-idle-box" role="dialog" aria-live="assertive">' +
				'<div class="watcher-idle-title">Etes-vous toujours la ?</div>' +
				'<div class="watcher-idle-text">Le serveur va s\'arreter automatiquement faute d\'activite.</div>' +
				'<div class="watcher-idle-timer" id="watcher-idle-timer">15:00</div>' +
				'<div class="watcher-idle-actions">' +
					'<button class="watcher-idle-btn primary" id="watcher-idle-keepalive">Je suis la</button>' +
				'</div>' +
			'</div>';
		document.body.appendChild(modal);
		timerEl = document.getElementById('watcher-idle-timer');

		document.getElementById('watcher-idle-keepalive').addEventListener('click', function () {
			acknowledgePresence();
		});
	}

	function forceLogoutRedirect() {
		fetch(logoutUrl, {
			method: 'GET',
			credentials: 'same-origin',
		})
			.then(function () {
				window.location.href = loginUrl;
			})
			.catch(function () {
				window.location.href = loginUrl;
			});
	}

	function fmt(seconds) {
		var s = Math.max(0, Number(seconds || 0));
		var m = Math.floor(s / 60);
		var r = s % 60;
		return String(m) + ':' + String(r).padStart(2, '0');
	}

	function show(seconds) {
		createModal();
		countdown = Math.max(0, Number(seconds || 0));
		if (timerEl) timerEl.textContent = fmt(countdown);
		modal.style.display = 'flex';
		isVisible = true;

		if (countdownHandle) clearInterval(countdownHandle);
		countdownHandle = setInterval(function () {
			countdown -= 1;
			if (timerEl) timerEl.textContent = fmt(countdown);
			if (countdown <= 0) {
				clearInterval(countdownHandle);
				countdownHandle = null;
				forceLogoutRedirect();
			}
		}, 1000);
	}

	function hide() {
		if (!modal) return;
		modal.style.display = 'none';
		isVisible = false;
		if (countdownHandle) {
			clearInterval(countdownHandle);
			countdownHandle = null;
		}
	}

	function acknowledgePresence() {
		fetch('/watcher/keepalive', {
			method: 'POST',
			credentials: 'same-origin',
			headers: { 'Content-Type': 'application/json' },
			body: '{}'
		})
			.then(function (r) { return r.ok ? r.json() : null; })
			.then(function () {
				hide();
			})
			.catch(function () {
				hide();
			});
	}

	function keepaliveOnUserAction() {
		var now = Date.now();
		if (now - lastUserKeepaliveAt < 60000) {
			return;
		}
		lastUserKeepaliveAt = now;
		fetch('/watcher/keepalive', {
			method: 'POST',
			credentials: 'same-origin',
			headers: { 'Content-Type': 'application/json' },
			body: '{}'
		}).catch(function () {
			// Ignore when not behind watcher.
		});
	}

	function poll() {
		fetch('/watcher/inactivity-status', { credentials: 'same-origin' })
			.then(function (r) {
				if (!r.ok) return null;
				return r.json();
			})
			.then(function (data) {
				if (!data) return;
				if (data.logout_url) logoutUrl = data.logout_url;
				if (data.login_url) loginUrl = data.login_url;
				if (data.warned) {
					show(data.grace_remaining_seconds || data.force_stop_in_seconds || 0);
				} else if (isVisible) {
					hide();
				}
			})
			.catch(function () {
				// Ignore when not behind watcher.
			});
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', function () {
			poll();
			pollHandle = setInterval(poll, 30000);
			document.addEventListener('click', keepaliveOnUserAction, { passive: true });
			document.addEventListener('keydown', keepaliveOnUserAction, { passive: true });
			document.addEventListener('touchstart', keepaliveOnUserAction, { passive: true });
		});
	} else {
		poll();
		pollHandle = setInterval(poll, 30000);
		document.addEventListener('click', keepaliveOnUserAction, { passive: true });
		document.addEventListener('keydown', keepaliveOnUserAction, { passive: true });
		document.addEventListener('touchstart', keepaliveOnUserAction, { passive: true });
	}
})();
