<script>
	// Éditeur des tags ID3 d'un titre.
	// Mode simple : champs principaux + Sauvegarder.
	// Mode expert : « Champs supplémentaires » et « Appliquer à l'album ».
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { secondaryOpen } from '$lib/metadata/library.js';
	import {
		EDITABLE_KEYS, ID3_PRIMARY, ID3_SECONDARY, ID3_LABELS,
		MULTI_FIELDS, MULTI_HINT, JELLYFIN_KEYS,
	} from '$lib/metadata/id3.js';

	export let path;
	export let meta;             // réponse /api/library/song-meta (id3 présent)
	export let albumSongs = [];  // titres visés par « Appliquer à l'album »
	export let onMetaReloaded = () => {};

	let editValues      = {};
	let dirty           = false;
	let saving          = false;
	let saveError       = '';
	let lastEditedField = null;  // dernier champ modifié (cible d'« Appliquer à l'album »)
	let applyingToAlbum = false;

	// Initialisé une fois (puis après chaque sauvegarde) : un upload de pochette
	// recharge `meta` sans écraser les modifications en cours.
	initEdit(meta);

	function initEdit(m) {
		const v = {};
		for (const k of EDITABLE_KEYS) v[k] = m.id3?.[k] ?? '';
		editValues = v;
		dirty = false;
	}

	function setField(k, v) {
		editValues = { ...editValues, [k]: v };
		dirty = true;
		lastEditedField = k;
	}

	async function saveTags() {
		if (!dirty || saving) return;
		saving = true; saveError = '';
		try {
			await api.saveSongMeta(path, editValues);
			addToast('Tags sauvegardés.', 'info');
			dirty = false;
			const data = await api.songMeta(path);
			if (data.success) { onMetaReloaded(data); initEdit(data); }
		} catch (e) { saveError = e.message ?? 'Erreur'; }
		finally { saving = false; }
	}

	async function applyToAlbum() {
		if (!lastEditedField || applyingToAlbum) return;
		const songs = albumSongs;
		if (songs.length === 0) return;
		applyingToAlbum = true;
		const fieldValue = editValues[lastEditedField] ?? '';
		let done = 0, errors = 0;
		for (const song of songs) {
			try {
				await api.saveSongMeta(song.path, { [lastEditedField]: fieldValue });
				if (song.path === path) dirty = false;
				done++;
			} catch { errors++; }
		}
		applyingToAlbum = false;
		const label = ID3_LABELS[lastEditedField] ?? lastEditedField;
		if (errors === 0) addToast(`« ${label} » appliqué à ${done} titre${done > 1 ? 's' : ''}.`, 'info');
		else addToast(`${done} OK, ${errors} erreur${errors > 1 ? 's' : ''}.`, 'error');
	}

	$: jellyfinMissing = JELLYFIN_KEYS.filter((k) => {
		const v = editValues[k] ?? meta.id3[k];
		return !v || v === '' || String(v).toLowerCase().includes('unknown');
	});
</script>

<section class="meta-section">
	<h3 class="section-title">
		🏷️ Tags ID3
		{#if jellyfinMissing.length > 0}
			<span class="jellyfin-warn">⚠️ Jellyfin manque : {jellyfinMissing.map(k=>ID3_LABELS[k]?.split(' ')[0]??k).join(', ')}</span>
		{/if}
	</h3>

	<div class="section-subtitle">Principaux (Jellyfin / Ampifin)</div>
	<div class="multi-hint">💡 Artiste(s), genre, compositeur : sépare plusieurs valeurs par « ; » — ex. <code>ArtisteA; ArtisteB</code></div>
	<div class="meta-grid">
		{#each ID3_PRIMARY as key}
			<div class="meta-row {jellyfinMissing.includes(key) ? 'row-warn' : ''}">
				<label class="meta-key" for="f-{key}">{ID3_LABELS[key]}</label>
				<input
					id="f-{key}"
					class="meta-input {jellyfinMissing.includes(key) ? 'input-warn' : ''}"
					value={editValues[key] ?? ''}
					placeholder={MULTI_FIELDS.has(key) ? 'A; B' : '—'}
					title={MULTI_FIELDS.has(key) ? MULTI_HINT : ''}
					on:input={(e) => setField(key, e.currentTarget.value)}
				/>
			</div>
		{/each}
	</div>

	<button class="details-toggle" on:click={() => secondaryOpen.update((o) => !o)}>
		{$secondaryOpen ? '▾' : '▸'} Champs supplémentaires
	</button>
	{#if $secondaryOpen}
		<div class="section-subtitle">Autres champs</div>
		<div class="meta-grid details-grid">
			{#each ID3_SECONDARY as key}
				<div class="meta-row">
					<label class="meta-key" for="f-{key}">{ID3_LABELS[key]}</label>
					<input
						id="f-{key}"
						class="meta-input {key === 'isrc' || key === 'encoded_by' ? 'mono' : ''}"
						value={editValues[key] ?? ''}
						placeholder={MULTI_FIELDS.has(key) ? 'A; B' : '—'}
						title={MULTI_FIELDS.has(key) ? MULTI_HINT : ''}
						on:input={(e) => setField(key, e.currentTarget.value)}
					/>
				</div>
			{/each}
		</div>
	{/if}

	<div class="save-bar">
		{#if saveError}<span class="save-error">{saveError}</span>{/if}
		{#if lastEditedField && albumSongs.length > 1}
			<button
				class="btn btn-ghost btn-sm"
				on:click={applyToAlbum}
				disabled={applyingToAlbum}
				title="Appliquer « {ID3_LABELS[lastEditedField] ?? lastEditedField} » à tous les titres de l'album"
			>
				{applyingToAlbum ? '⏳…' : '📋 Appliquer à l\'album'}
			</button>
		{/if}
		<button
			class="btn btn-primary btn-sm"
			on:click={saveTags}
			disabled={!dirty || saving}
		>
			{saving ? '⏳ Sauvegarde…' : dirty ? '💾 Sauvegarder' : '✓ Sauvegardé'}
		</button>
	</div>
</section>

<style>
	.jellyfin-warn { font-size: 11px; font-weight: 500; color: var(--orange); text-transform: none; letter-spacing: 0; }

	.multi-hint {
		padding: var(--s2) var(--s4);
		font-size: 11px; color: var(--text-3);
		border-bottom: 1px solid rgba(84,84,88,.2);
	}
	.multi-hint code { font-size: 10px; background: rgba(0,0,0,.25); padding: 1px 4px; border-radius: 3px; }

	.details-grid { background: rgba(0,0,0,.08); }

	.details-toggle {
		display: flex; align-items: center; gap: 6px;
		width: 100%; padding: var(--s2) var(--s4);
		background: none; border: none;
		border-top: 1px solid rgba(84,84,88,.2);
		color: var(--blue); font-size: 12px; font-weight: 500;
		cursor: pointer; text-align: left;
		transition: background .1s;
	}
	.details-toggle:hover { background: rgba(10,132,255,.06); }
</style>
