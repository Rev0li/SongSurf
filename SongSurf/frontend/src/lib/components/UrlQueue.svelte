<script>
	import { onDestroy } from 'svelte';
	import { workerBusy } from '$lib/stores.js';
	import { api } from '$lib/api.js';

	// queue items: { id, label, status, error, isPlaylist, ...download params }
	// status: 'pending' | 'submitting' | 'waiting' | 'done' | 'error'
	let queue = [];
	let processing = false; // true from start-of-submit until server worker finishes
	let idCounter = 0;

	// ── Public API ────────────────────────────────────────────────────────────
	export function enqueue(item) {
		queue = [...queue, { ...item, id: ++idCounter, status: 'pending', error: '' }];
		processNext();
	}

	// ── Worker-free transition detector ──────────────────────────────────────
	// Subscribe manually to detect busy→free transition without $: loop risk
	let _prevBusy = false;
	const _unsubBusy = workerBusy.subscribe(busy => {
		if (_prevBusy && !busy) onWorkerFree();
		_prevBusy = busy;
	});
	onDestroy(_unsubBusy);

	function onWorkerFree() {
		// The item that was 'waiting' is now complete
		const waiting = queue.find(q => q.status === 'waiting');
		if (waiting) { waiting.status = 'done'; queue = queue; }
		processing = false;
		processNext();
	}

	// ── Sequential processing ─────────────────────────────────────────────────
	function processNext() {
		// Guards: one item at a time, don't send while server is busy
		if (processing || $workerBusy) return;
		const next = queue.find(q => q.status === 'pending');
		if (!next) return;

		processing = true;      // MUST be first — prevents any re-entrant call
		next.status = 'submitting';
		queue = queue;

		_submit(next);           // fire-and-forget async
	}

	async function _submit(item) {
		try {
			let res;
			if (item.isPlaylist) {
				res = await api.downloadPlaylist({
					playlist_mode: item.playlistMode ?? false,
					mp4_mode:      item.mp4Mode ?? false,
					playlist_metadata: item.playlistMetadata,
				});
			} else {
				res = await api.download({
					url:           item.url,
					playlist_mode: item.playlistMode ?? false,
					mp4_mode:      item.mp4Mode ?? false,
					title:         item.title,
					artist:        item.artist,
					album:         item.album,
					year:          item.year ?? '',
				});
			}

			if (!res.success) throw new Error(res.error || 'Erreur téléchargement');

			// Submitted — now wait for workerBusy → false (handled by onWorkerFree)
			item.status = 'waiting';
			queue = queue;
			// processing stays true until onWorkerFree releases it

		} catch (err) {
			item.status = 'error';
			item.error = err.message;
			processing = false;
			queue = queue;
			// Try next item after a short pause
			setTimeout(processNext, 400);
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
</style>
