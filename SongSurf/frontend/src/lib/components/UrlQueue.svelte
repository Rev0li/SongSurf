<script>
	import { workerBusy } from '$lib/stores.js';
	import { api } from '$lib/api.js';
	import { asText, primaryArtist, inferPlaylistArtist } from '$lib/utils.js';

	// queue items: { id, url, status, label, error }
	// status: 'pending' | 'extracting' | 'submitted' | 'done' | 'error'
	let queue = [];
	let inputUrl = '';
	let processing = false;
	let idCounter = 0;

	// ── Add URLs ──────────────────────────────────────────────────────────────
	function add() {
		const lines = inputUrl.split('\n').map(l => l.trim()).filter(Boolean);
		if (!lines.length) return;
		queue = [
			...queue,
			...lines.map(url => ({ id: ++idCounter, url, status: 'pending', label: url, error: '' })),
		];
		inputUrl = '';
		maybeProcess();
	}

	function remove(id) {
		queue = queue.filter(q => !(q.id === id && q.status === 'pending'));
	}

	function clearDone() {
		queue = queue.filter(q => q.status !== 'done' && q.status !== 'error');
	}

	function onKeydown(e) {
		if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); add(); }
	}

	// ── Processing ────────────────────────────────────────────────────────────
	// When worker finishes or processing flag clears, check queue
	$: if (!$workerBusy && !processing) maybeProcess();

	function maybeProcess() {
		// Any submitted item whose server download just completed → mark done
		let changed = false;
		for (const item of queue) {
			if (item.status === 'submitted') { item.status = 'done'; changed = true; }
		}
		if (changed) queue = queue;

		// Start next pending if free
		const next = queue.find(q => q.status === 'pending');
		if (next && !processing && !$workerBusy) processItem(next);
	}

	async function processItem(item) {
		processing = true;
		item.status = 'extracting';
		queue = queue;

		try {
			const data = await api.extract(item.url);
			if (!data.success) throw new Error(data.error || 'Extraction impossible');

			item.label = data.is_playlist
				? asText(data.title, item.url)
				: `${primaryArtist(data.artist)} — ${asText(data.title, '…')}`;
			item.status = 'downloading';
			queue = queue;

			let res;
			if (data.is_playlist) {
				res = await api.downloadPlaylist({
					playlist_mode: false,
					mp4_mode: false,
					playlist_metadata: {
						title:  asText(data.title, 'Unknown Album'),
						artist: inferPlaylistArtist(data),
						year:   asText(data.year),
						songs:  data.songs ?? [],
					},
				});
			} else {
				res = await api.download({
					url:           item.url,
					playlist_mode: false,
					mp4_mode:      false,
					title:         asText(data.title,  'Unknown Title'),
					artist:        primaryArtist(data.artist),
					album:         asText(data.album,  'Unknown Album'),
					year:          asText(data.year),
				});
			}
			if (!res.success) throw new Error(res.error || 'Erreur téléchargement');

			// 'submitted' → becomes 'done' when workerBusy goes false (maybeProcess)
			item.status = 'submitted';
		} catch (err) {
			item.status = 'error';
			item.error = err.message;
		} finally {
			processing = false;
			queue = queue;
		}
	}

	// ── Derived ───────────────────────────────────────────────────────────────
	$: pending   = queue.filter(q => q.status === 'pending').length;
	$: hasQueue  = queue.length > 0;
	$: hasClear  = queue.some(q => q.status === 'done' || q.status === 'error');

	const ICON = {
		pending:    '⏳',
		extracting: '🔍',
		downloading:'⬇️',
		submitted:  '⬇️',
		done:       '✅',
		error:      '❌',
	};
	const LABEL = {
		pending:    'En attente',
		extracting: 'Analyse…',
		downloading:'Téléchargement…',
		submitted:  'En cours…',
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
		{#if hasClear}
			<button class="btn btn-ghost btn-sm" on:click={clearDone}>Vider</button>
		{/if}
	</div>

	<div class="queue-input-row">
		<textarea
			class="form-input queue-textarea"
			bind:value={inputUrl}
			placeholder="Coller un ou plusieurs liens YouTube Music (un par ligne)…"
			rows="1"
			on:keydown={onKeydown}
		></textarea>
		<button class="btn btn-primary btn-sm" on:click={add} disabled={!inputUrl.trim()}>
			Ajouter
		</button>
	</div>

	{#if hasQueue}
		<ul class="queue-list">
			{#each queue as item (item.id)}
				<li class="queue-item" class:is-done={item.status === 'done'} class:is-error={item.status === 'error'}>
					<span class="queue-icon">{ICON[item.status]}</span>
					<span class="queue-label" title={item.url}>
						{item.label !== item.url ? item.label : ''}
						{#if item.label === item.url}<span class="queue-url">{item.url}</span>{/if}
						{#if item.status === 'error'}<span class="queue-error">{item.error}</span>{/if}
					</span>
					<span class="queue-status-text">{LABEL[item.status]}</span>
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
	.queue-header .btn { margin-left: auto; }

	.queue-input-row {
		display: flex;
		gap: var(--s2);
		align-items: flex-start;
		margin-bottom: var(--s3);
	}
	.queue-textarea {
		flex: 1;
		resize: none;
		font-size: 13px;
		line-height: 1.5;
		min-height: 36px;
		max-height: 120px;
		overflow-y: auto;
		field-sizing: content; /* auto-grow in modern browsers */
	}

	.queue-list {
		list-style: none;
		margin: 0; padding: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.queue-item {
		display: flex;
		align-items: center;
		gap: var(--s2);
		padding: 6px var(--s2);
		border-radius: var(--r-sm);
		background: var(--bg-3);
		font-size: 13px;
		min-width: 0;
	}
	.queue-item.is-done   { opacity: .55; }
	.queue-item.is-error  { background: rgba(255, 59, 48, .1); }

	.queue-icon  { flex-shrink: 0; font-size: 14px; }
	.queue-label {
		flex: 1;
		min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--text);
	}
	.queue-url   { color: var(--text-3); font-size: 12px; }
	.queue-error { display: block; color: #ff3b30; font-size: 11px; white-space: normal; margin-top: 2px; }

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
		font-size: 11px; padding: 2px 4px;
		border-radius: 4px;
		line-height: 1;
	}
	.queue-remove:hover { color: var(--text); background: var(--bg-4); }
</style>
