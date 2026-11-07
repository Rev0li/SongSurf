<script>
	import '$lib/styles/design-system.css';
	import '$lib/styles/components.css';
	import '$lib/styles/layouts.css';
	import '$lib/styles/app.css';

	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api.js';
	import { user, downloadStatus, theme, addToast } from '$lib/stores.js';
	import { ingestStatus } from '$lib/downloads.js';
	import { refreshLibrary } from '$lib/library/data.js';
	import Toast from '$lib/components/Toast.svelte';
	import ConfirmModal from '$lib/components/ConfirmModal.svelte';
	import TopBar from '$lib/components/shell/TopBar.svelte';
	import TabBar from '$lib/components/shell/TabBar.svelte';
	import MiniBar from '$lib/components/shell/MiniBar.svelte';
	import SheetHost from '$lib/components/sheets/SheetHost.svelte';
	/**
	 * @typedef {Object} Props
	 * @property {import('svelte').Snippet} [children]
	 */

	/** @type {Props} */
	let { children } = $props();

	let pollInterval;
	let unsubTheme;
	let libraryRefresh = null;

	async function pollStatus() {
		try {
			const st = await api.getStatus();
			downloadStatus.set(st);

			// Titre terminé → « Ma musique » se met à jour (regroupé : un album = une
			// rafale de titres). Échec (cookies, âge…) → message + « Réessayer » dans « En cours ».
			const { completed, failed } = ingestStatus(st);
			if (completed && !libraryRefresh) {
				libraryRefresh = setTimeout(() => { libraryRefresh = null; refreshLibrary(); }, 2500);
			}
			if (failed) addToast(`« ${failed.title} » : ${failed.error}`, 'error', 8000);
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
		clearTimeout(libraryRefresh);
		unsubTheme?.();
	});
</script>

<svelte:head>
	<link rel="preload" href="/fonts/jgs_font-webfont.woff2" as="font" type="font/woff2" crossorigin="anonymous" />
</svelte:head>

<Toast />
<ConfirmModal />

<TopBar />
<main class="shell-main">
	{@render children?.()}
</main>
<MiniBar />
<TabBar />
<SheetHost />
