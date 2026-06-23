<script>
	import { onDestroy, onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { workerBusy, extensionQueue, urlQueue } from '$lib/stores.js';
	import { api } from '$lib/api.js';

	// queue items: { id, label, status, error, isPlaylist, ...download params }
	// status: 'pending' | 'submitting' | 'waiting' | 'done' | 'error'
	let queue = get(urlQueue); // restore across navigation
	let processing = false;
	let idCounter = queue.reduce((max, item) => Math.max(max, item.id ?? 0), 0);

	// Sync local queue to persistent store on every change
	$: urlQueue.set(queue);

	// ── Public API ────────────────────────────────────────────────────────────
	export function enqueue(item) {
		queue = [...queue, { ...item, id: ++idCounter, status: 'pending', error: '' }];
		processNext();
	}

	// ── Extension queue intake ─────────────────────────────────────────────────
	const _unsubExt = extensionQueue.subscribe((items) => {
		if (items.length === 0) return;
		for (const item of items) {
			const isPlaylist = item.url_mode === 'album' || item.url_mode === 'playlist';
			const label = isPlaylist
				? `${item.artist || '?'} — ${item.album || item.url_mode}`
				: `${item.artist || '?'} — ${item.title || item.url}`;
			enqueue({
				label,
				url:          item.url,
				url_mode:     item.url_mode,
				title:        item.title,
				artist:       item.artist,
				album:        item.album,
				year:         item.year ?? '',
				isPlaylist,
				needsExtract: isPlaylist,
				fromExtension: true,
			});
		}
		extensionQueue.set([]);
	});
	onDestroy(_unsubExt);

	// ── Worker-free transition detector ──────────────────────────────────────
	// Subscribe manually to detect busy→free transition without $: loop risk
	let _prevBusy = false;
	const _unsubBusy = workerBusy.subscribe(busy => {
		if (_prevBusy && !busy) onWorkerFree();
		_prevBusy = busy;
	});
	onDestroy(_unsubBusy);

	// ── Reconcile state after navigation ─────────────────────────────────────
	// The queue persists but local flags (processing, _prevBusy) reset on mount.
	onMount(() => {
		// 'submitting' = fetch was in-flight when we left; reset to retry
		for (const item of queue) {
			if (item.status === 'submitting') item.status = 'pending';
		}
		// 'waiting' = remis au serveur ; si le worker est libre, le batch est fini.
		if (!get(workerBusy)) {
			for (const item of queue) {
				if (item.status === 'waiting') item.status = 'done';
			}
		}
		queue = queue;
		processNext();
	});

	function onWorkerFree() {
		// Le worker serveur a fini de drainer : tout ce qui était remis (waiting)
		// est terminé. On ne marque que si plus rien n'est en cours de soumission.
		if (queue.some(q => q.status === 'pending' || q.status === 'submitting')) return;
		let changed = false;
		for (const item of queue) {
			if (item.status === 'waiting') { item.status = 'done'; changed = true; }
		}
		if (changed) queue = queue;
	}

	// ── Submit everything to the server, which drains album by album on its own ──
	// On empile tout d'un coup : le serveur possède la file et la draine
	// séquentiellement (un album = un job), sans saturer ni dépendre de la page
	// ouverte. onWorkerFree passera les items 'waiting' à 'done' à la fin du batch.
	async function processNext() {
		if (processing) return;     // évite deux boucles de drain concurrentes
		processing = true;
		try {
			while (true) {
				const next = queue.find(q => q.status === 'pending');
				if (!next) break;
				next.status = 'submitting';
				queue = queue;
				await _submit(next);   // empile côté serveur (waiting) ou error
			}
		} finally {
			processing = false;
		}
	}

	async function _submit(item) {
		try {
			let res;
			if (item.needsExtract) {
				const extracted = await api.extract(item.url);
				if (!extracted.success) throw new Error(extracted.error || 'Extraction échouée');
				res = await api.downloadPlaylist({
					playlist_metadata: {
						...extracted,
						artist: item.artist || extracted.artist,
						title:  item.album  || extracted.title,
					},
				});
			} else if (item.isPlaylist) {
				res = await api.downloadPlaylist({
					playlist_metadata: item.playlistMetadata,
				});
			} else {
				res = await api.download({
					url:    item.url,
					title:  item.title,
					artist: item.artist,
					album:  item.album,
					year:   item.year ?? '',
					track_number: item.track_number ?? '',
					album_artist: item.album_artist ?? '',
					artists: item.artists ?? [],
				});
			}

			if (!res.success) throw new Error(res.error || 'Erreur téléchargement');

			// Remis au serveur. Le worker draine seul ; onWorkerFree passera
			// l'item à 'done' quand le batch sera terminé.
			item.status = 'waiting';
			queue = queue;

		} catch (err) {
			item.status = 'error';
			item.error = err.message;
			queue = queue;
		}
	}

	// ── UI helpers ────────────────────────────────────────────────────────────
	function remove(id) {
		queue = queue.filter(q => !(q.id === id && q.status === 'pending'));
	}

	function clearFinished() {
		queue = queue.filter(q => q.status !== 'done' && q.status !== 'error');
	}

	$: pending    = queue.filter(q => q.status === 'pending').length;
	$: hasQueue   = queue.length > 0;
	$: hasFinished = queue.some(q => q.status === 'done' || q.status === 'error');

	const STATUS_ICON = {
		pending:    '⏳',
		submitting: '📤',
		waiting:    '⬇️',
		done:       '✅',
		error:      '❌',
	};
	const STATUS_LABEL = {
		pending:    'En attente',
		submitting: 'Envoi…',
		waiting:    'Téléchargement…',
		done:       'Terminé',
		error:      'Erreur',
	};
</script>

<div class="card queue-card">
	<div class="queue-header">
		<h2 class="card-title" style="margin:0">📋 File d'attente</h2>
		{#if pending > 0}
			<span class="queue-badge">{pending} en attente</span>
		{/if}
		{#if hasFinished}
			<button class="btn btn-ghost btn-sm" style="margin-left:auto" on:click={clearFinished}>
				Vider
			</button>
		{/if}
	</div>

	{#if !hasQueue}
		<p class="empty-state-text" style="margin:0">
			Analyse un lien, puis clique sur « Ajouter à la file ».
		</p>
	{:else}
		<ul class="queue-list">
			{#each queue as item (item.id)}
				<li
					class="queue-item"
					class:is-done={item.status === 'done'}
					class:is-error={item.status === 'error'}
					class:is-active={item.status === 'submitting' || item.status === 'waiting'}
				>
					<span class="queue-icon">{STATUS_ICON[item.status]}</span>
					<span class="queue-label" title={item.label}>
						{item.label}
						{#if item.fromExtension}
							<span class="queue-source">ext</span>
						{/if}
						{#if item.status === 'error'}
							<span class="queue-error">{item.error}</span>
						{/if}
					</span>
					<span class="queue-status-text">{STATUS_LABEL[item.status]}</span>
					{#if item.status === 'pending'}
						<button class="queue-remove" on:click={() => remove(item.id)}>✕</button>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.queue-card { margin-bottom: var(--s4); }

	.queue-header {
		display: flex;
		align-items: center;
		gap: var(--s3);
		margin-bottom: var(--s3);
	}
	.queue-badge {
		font-size: 11px;
		background: var(--blue);
		color: #fff;
		padding: 2px 8px;
		border-radius: var(--r-full);
		font-weight: 600;
	}

	.queue-list {
		list-style: none;
		margin: 0; padding: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.queue-item {
		display: flex;
		align-items: center;
		gap: var(--s2);
		padding: 7px var(--s2);
		border-radius: var(--r-sm);
		background: var(--bg-3);
		font-size: 13px;
		min-width: 0;
		transition: opacity .2s;
	}
	.queue-item.is-done   { opacity: .5; }
	.queue-item.is-error  { background: rgba(255, 59, 48, .12); }
	.queue-item.is-active { background: rgba(10, 132, 255, .1); }

	.queue-icon  { flex-shrink: 0; font-size: 14px; width: 20px; text-align: center; }
	.queue-label {
		flex: 1; min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--text);
	}
	.queue-error {
		display: block;
		color: #ff453a;
		font-size: 11px;
		white-space: normal;
		margin-top: 2px;
	}
	.queue-status-text {
		flex-shrink: 0;
		font-size: 11px;
		color: var(--text-3);
		white-space: nowrap;
	}
	.queue-remove {
		flex-shrink: 0;
		background: none; border: none;
		color: var(--text-3); cursor: pointer;
		font-size: 11px; padding: 2px 5px;
		border-radius: 4px; line-height: 1;
	}
	.queue-remove:hover { color: var(--text); background: var(--bg-4); }

	.queue-source {
		display: inline-block;
		font-size: 9px;
		font-weight: 700;
		letter-spacing: .04em;
		text-transform: uppercase;
		background: rgba(191, 90, 242, .18);
		color: var(--purple);
		border-radius: 3px;
		padding: 1px 4px;
		margin-left: 5px;
		vertical-align: middle;
	}
</style>
