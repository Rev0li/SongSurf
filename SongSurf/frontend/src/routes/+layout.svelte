<script>
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api.js';
	import { user, downloadStatus, recentDownloads, addToast } from '$lib/stores.js';
	import { primaryArtist, asText } from '$lib/utils.js';
	import Toast from '$lib/components/Toast.svelte';
	import WatcherInactivity from '$lib/components/WatcherInactivity.svelte';

	let lastCompletedTimestamp = '';
	let pollInterval;

	async function pollStatus() {
		try {
			const st = await api.getStatus();
			downloadStatus.set(st);

			if (
				st.last_completed?.timestamp &&
				st.last_completed.timestamp !== lastCompletedTimestamp
			) {
				lastCompletedTimestamp = st.last_completed.timestamp;
				const meta = st.last_completed.metadata ?? {};
				recentDownloads.update((list) => [
					{
						artist: primaryArtist(meta.artist ?? 'Unknown Artist'),
						title: asText(meta.title, 'Unknown Title'),
						filePath: st.last_completed.file_path ?? '',
						timestamp: st.last_completed.timestamp,
					},
					...list,
				]);
			}
		} catch {
			// ignore transient errors
		}
	}

	onMount(async () => {
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

	onDestroy(() => clearInterval(pollInterval));
</script>

<Toast />
<WatcherInactivity />

<slot />
