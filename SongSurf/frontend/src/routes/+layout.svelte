<script>
	import '$lib/styles/design-system.css';
	import '$lib/styles/components.css';
	import '$lib/styles/layouts.css';
	import '$lib/styles/dashboard.css';

	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api.js';
	import { user, downloadStatus, lastCompleted, extensionQueue, theme } from '$lib/stores.js';
	import { primaryArtist, asText } from '$lib/utils.js';
	import Toast from '$lib/components/Toast.svelte';
	import WatcherInactivity from '$lib/components/WatcherInactivity.svelte';

	let lastCompletedTimestamp = '';
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

<slot />
