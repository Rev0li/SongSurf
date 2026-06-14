<script>
	import '$lib/styles/design-system.css';
	import '$lib/styles/components.css';
	import '$lib/styles/layouts.css';
	import '$lib/styles/dashboard.css';

	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api.js';
	import { user, downloadStatus, lastCompleted, extensionQueue, theme, helpOpen, addToast } from '$lib/stores.js';
	import { primaryArtist, asText } from '$lib/utils.js';
	import Toast from '$lib/components/Toast.svelte';
	import WatcherInactivity from '$lib/components/WatcherInactivity.svelte';
	import HelpModal from '$lib/components/HelpModal.svelte';

	let lastCompletedTimestamp = '';
	let lastErrorTimestamp = '';
	let errorBaselineSet = false;
	let pollInterval;
	let unsubTheme;

	async function pollStatus() {
		try {
			const st = await api.getStatus();
			downloadStatus.set(st);

			if ((st.extension_pending_count ?? 0) > 0) {
				try {
					const res = await api.consumeExtensionQueue();
					if (res.items?.length > 0) {
						extensionQueue.update((q) => [...q, ...res.items]);
					}
				} catch {
					// ignore transient errors
				}
			}

			if (
				st.last_completed?.timestamp &&
				st.last_completed.timestamp !== lastCompletedTimestamp
			) {
				lastCompletedTimestamp = st.last_completed.timestamp;
				const meta = st.last_completed.metadata ?? {};
				lastCompleted.set({
					artist: primaryArtist(meta.artist ?? 'Unknown Artist'),
					title: asText(meta.title, 'Unknown Title'),
					timestamp: st.last_completed.timestamp,
				});
			}

			// Échec de téléchargement (ex. cookies/âge) → toast actionnable.
			// Au 1er poll on ne fait qu'établir la ligne de base (pas de toast
			// pour une erreur résiduelle d'une session précédente).
			if (!errorBaselineSet) {
				lastErrorTimestamp = st.last_error?.timestamp ?? '';
				errorBaselineSet = true;
			} else if (
				st.last_error?.timestamp &&
				st.last_error.timestamp !== lastErrorTimestamp
			) {
				lastErrorTimestamp = st.last_error.timestamp;
				const meta = st.last_error.metadata ?? {};
				const who = asText(meta.title, '') || asText(meta.album, '');
				const prefix = who ? `« ${who} » : ` : '';
				addToast(`${prefix}${asText(st.last_error.error, 'Téléchargement échoué.')}`, 'error', 8000);
			}
		} catch {
			// ignore transient errors
		}
	}

	onMount(async () => {
		// Theme: read from localStorage, apply to <html> and keep in sync
		const saved = localStorage.getItem('theme') ?? 'light';
		theme.set(saved);
		unsubTheme = theme.subscribe((t) => {
			localStorage.setItem('theme', t);
			document.documentElement.classList.toggle('dark', t === 'dark');
		});

		// Load user identity
		try {
			const me = await api.me();
			user.set(me);
		} catch {
			// DEV_MODE or unauthenticated — user stays null
		}

		// Auto-ouverture du tutoriel au tout premier passage
		if (!localStorage.getItem('ssf.help.seen')) {
			helpOpen.set(true);
			localStorage.setItem('ssf.help.seen', '1');
		}

		pollStatus();
		pollInterval = setInterval(pollStatus, 1500);
	});

	onDestroy(() => {
		clearInterval(pollInterval);
		unsubTheme?.();
	});
</script>

<svelte:head>
	<link rel="preload" href="/fonts/jgs_font-webfont.woff2" as="font" type="font/woff2" crossorigin="anonymous" />
</svelte:head>

<Toast />
<WatcherInactivity />
<HelpModal />

<slot />
