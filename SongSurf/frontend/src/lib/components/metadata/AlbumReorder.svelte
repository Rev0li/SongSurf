<script>
	// Renumérotation manuelle d'un album (mode expert) : glisser-déposer ou ▲▼,
	// puis écriture de TRCK 1/N…N/N sur tout l'album.
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { songDisplayName } from '$lib/metadata/id3.js';

	export let albumPath;
	export let tracks = [];          // [{path, name, title, track_number}], numérotées d'abord
	export let onSaved = () => {};
	export let onCancel = () => {};

	let saving  = false;
	let dragIdx = -1;

	function moveTrack(i, delta) {
		const j = i + delta;
		if (j < 0 || j >= tracks.length) return;
		const arr = [...tracks];
		[arr[i], arr[j]] = [arr[j], arr[i]];
		tracks = arr;
	}

	function dragStart(e, i) {
		dragIdx = i;
		e.dataTransfer.effectAllowed = 'move';
	}

	function dragOver(e, i) {
		e.preventDefault();
		if (dragIdx === -1 || i === dragIdx) return;
		const arr = [...tracks];
		const [moved] = arr.splice(dragIdx, 1);
		arr.splice(i, 0, moved);
		tracks = arr;
		dragIdx = i;
	}

	function dragEnd() { dragIdx = -1; }

	async function save() {
		if (saving || tracks.length === 0) return;
		saving = true;
		try {
			const res = await api.renumberAlbum(albumPath, tracks.map((t) => t.path));
			addToast(`Album numéroté 1 à ${res.total}.`, 'info');
			onSaved();
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { saving = false; }
	}
</script>

<div class="reorder-hint">
	Glisse les titres dans l'ordre de l'album (ou utilise ▲▼).
	Les titres <span class="reorder-badge-missing">sans n°</span> ont été placés à la fin.
	« Enregistrer » écrit <code>1/{tracks.length}…{tracks.length}/{tracks.length}</code> sur tous les titres.
</div>
<div class="tracklist">
	{#each tracks as track, i (track.path)}
		<div
			class="track-row reorder-row {dragIdx === i ? 'reorder-dragging' : ''}"
			draggable="true"
			role="listitem"
			on:dragstart={(e) => dragStart(e, i)}
			on:dragover={(e) => dragOver(e, i)}
			on:dragend={dragEnd}
			on:drop|preventDefault={dragEnd}
		>
			<span class="reorder-grip">⠿</span>
			<span class="track-num">{i + 1}</span>
			<span class="track-name">{songDisplayName(track.name)}</span>
			{#if track.track_number}
				<span class="reorder-badge">{track.track_number}</span>
			{:else}
				<span class="reorder-badge reorder-badge-missing">sans n°</span>
			{/if}
			<span class="reorder-arrows">
				<button class="reorder-arrow" disabled={i === 0} on:click={() => moveTrack(i, -1)}>▲</button>
				<button class="reorder-arrow" disabled={i === tracks.length - 1} on:click={() => moveTrack(i, 1)}>▼</button>
			</span>
		</div>
	{/each}
</div>
<div class="save-bar">
	<button class="btn btn-ghost btn-sm" on:click={onCancel} disabled={saving}>
		Annuler
	</button>
	<button class="btn btn-primary btn-sm" on:click={save} disabled={saving}>
		{saving ? '⏳ Écriture…' : `💾 Enregistrer la numérotation (1..${tracks.length})`}
	</button>
</div>

<style>
	.reorder-hint {
		padding: var(--s2) var(--s4);
		font-size: 11px; color: var(--text-3); line-height: 1.5;
		border-bottom: 1px solid rgba(84,84,88,.2);
	}
	.reorder-hint code { font-size: 10px; background: rgba(0,0,0,.25); padding: 1px 4px; border-radius: 3px; }

	/* .track-row.reorder-row : doit l'emporter sur .meta-layout .track-row (metadata.css) */
	.track-row.reorder-row { cursor: grab; user-select: none; }
	.track-row.reorder-row:active { cursor: grabbing; }
	.track-row.reorder-row.reorder-dragging { background: rgba(10,132,255,.12); }
	.reorder-grip { flex-shrink: 0; color: var(--text-3); font-size: 13px; }
	.reorder-arrows { flex-shrink: 0; display: flex; gap: 2px; }
	.reorder-arrow {
		background: none; border: none;
		color: var(--text-3); font-size: 10px;
		cursor: pointer; padding: 2px 4px;
		border-radius: 3px;
		transition: color .1s, background .1s;
	}
	.reorder-arrow:hover { color: var(--text); background: rgba(255,255,255,.08); }
	.reorder-arrow:disabled { opacity: .3; pointer-events: none; }
</style>
