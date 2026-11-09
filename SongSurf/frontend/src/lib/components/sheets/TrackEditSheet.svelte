<script>
	// « Modifier les infos » d'un titre (SSF-13). Membre : 5 champs simples + l'album
	// (changé via « Déplacer vers… », pour que dossier et tags restent d'accord).
	// Admin : codes ID3 visibles, « Mode expert » (tous les champs, TXXX, fichier).
	import { onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { api } from '$lib/api.js';
	import { user, addToast } from '$lib/stores.js';
	import { openSheet, closeSheet } from '$lib/ui/sheets.js';
	import { tree, findAlbum, parentPath, coverUrl, refreshTodo, songTitle } from '$lib/library/data.js';
	import { ID3_LABELS, MULTI_HINT } from '$lib/metadata/id3.js';
	import '$lib/styles/metadata.css'; // outils experts existants (préfixe .meta-layout)
	import Sheet from '../ui/Sheet.svelte';
	import Cover from '../ui/Cover.svelte';
	import GenrePicker from '../ui/GenrePicker.svelte';
	import Icon from '../ui/Icon.svelte';
	import SongDetails from '../metadata/SongDetails.svelte';

	let { path, onSaved = () => {}, onClose } = $props();

	const isAdmin = get(user)?.role === 'admin';
	const albumPath = untrack(() => parentPath(path)); // panneau remonté à chaque ouverture
	const located = findAlbum(get(tree), albumPath);
	const EXPERT_KEYS = ['album_artist', 'disc_number', 'composer', 'publisher', 'bpm', 'key', 'language', 'isrc', 'copyright', 'encoded_by', 'comment'];

	let meta = $state(null);
	let loadError = $state('');
	let saving = $state(false);
	let saveError = $state('');
	let initial = {};
	let v = $state({ title: '', artist: '', year: '', n: '', total: '', genre: '' });
	let expert = $state({});

	onMount(load);

	async function load() {
		try {
			const data = await api.songMeta(path);
			if (!data.success) throw new Error(data.error ?? 'Lecture impossible');
			meta = data;
			const id3 = data.id3 ?? {};
			const [n, total] = String(id3.track_number ?? '').split('/');
			v = {
				title: id3.title ?? '', artist: id3.artist ?? '', year: String(id3.year ?? '').slice(0, 4),
				n: (n ?? '').trim(), total: (total ?? '').trim() || String(located?.album.songs?.length ?? ''), genre: id3.genre ?? '',
			};
			expert = Object.fromEntries(EXPERT_KEYS.map((k) => [k, id3[k] ?? '']));
			initial = { ...v, ...expert };
		} catch (e) { loadError = e.message ?? 'Erreur'; }
	}

	let missingYear = $derived(meta && !v.year.trim());
	let missingN = $derived(meta && !v.n.trim());

	async function save() {
		if (saving) return;
		saveError = '';
		const year = v.year.trim(), n = v.n.trim(), total = v.total.trim();
		if (year && !/^\d{4}$/.test(year)) { saveError = "L'année doit avoir 4 chiffres (ex. 2017)."; return; }
		if (n && !/^\d+$/.test(n)) { saveError = 'Le numéro de piste doit être un nombre.'; return; }
		const tags = {};
		if (v.title.trim() !== (initial.title ?? '').trim()) tags.title = v.title.trim();
		if (v.artist.trim() !== (initial.artist ?? '').trim()) tags.artist = v.artist.trim();
		if (year !== (initial.year ?? '')) tags.year = year;
		if (n !== (initial.n ?? '') || (n && total !== (initial.total ?? ''))) tags.track_number = n ? (total ? `${n}/${total}` : n) : '';
		if (v.genre !== (initial.genre ?? '')) tags.genre = v.genre;
		if (isAdmin) for (const k of EXPERT_KEYS) if ((expert[k] ?? '') !== (initial[k] ?? '')) tags[k] = expert[k];
		if (Object.keys(tags).length === 0) { closeSheet(); return; }
		saving = true;
		try {
			await api.saveSongMeta(path, tags);
			addToast('Infos enregistrées.', 'info');
			refreshTodo();
			onSaved();
			closeSheet();
		} catch (e) { saveError = e.message ?? 'Erreur'; }
		finally { saving = false; }
	}


	const lab = (label, code) => (isAdmin && code ? `${label} <code>${code}</code>` : label);
</script>

<Sheet title="Modifier les infos" sub={meta ? (v.title || songTitle(path.split('/').pop())) : 'Chargement…'} tall {onClose}>
	{#snippet lead()}<Cover src={coverUrl(albumPath)} label={located?.album.name ?? ''} size={44} />{/snippet}

	{#if loadError}
		<p class="err-title" role="alert">{loadError}</p>
	{:else if !meta}
		<div class="spinner" aria-label="Chargement"></div>
	{:else}
		<div class="form">
			<div class="f"><label for="te-title">{@html lab('Titre', 'TIT2')}</label><input id="te-title" class="inp" bind:value={v.title} /></div>
			<div class="f">
				<label for="te-artist">{@html lab('Artiste(s)', 'TPE1')}</label>
				<input id="te-artist" class="inp" bind:value={v.artist} />
				<span class="hint">{MULTI_HINT}</span>
			</div>
			<div class="f">
				<span class="flab">{@html lab('Album', 'TALB')}</span>
				<div class="album-line">
					<span class="album-name">{located?.album.name ?? meta.id3?.album ?? '—'}</span>
					<button type="button" class="btn btn-soft btn-sm with-ico" onclick={() => openSheet('move', { what: 'track', path, onDone: onSaved })}>
						<Icon name="move" size={16} />Déplacer vers…
					</button>
				</div>
			</div>
			<div class="two">
				<div class="f" class:missing={missingYear}>
					<label for="te-year">{@html lab('Année', 'TDRC')}</label>
					<input id="te-year" class="inp" bind:value={v.year} inputmode="numeric" maxlength="4" placeholder="ex. 2017" />
					{#if missingYear}<span class="hint">À compléter</span>{/if}
				</div>
				<div class="f" class:missing={missingN}>
					<label for="te-n">{@html lab('N° de piste', 'TRCK')}</label>
					<div class="pair">
						<input id="te-n" class="inp" bind:value={v.n} inputmode="numeric" placeholder="?" />
						<span>sur</span>
						<input id="te-total" class="inp" bind:value={v.total} inputmode="numeric" aria-label="Nombre de titres de l'album" />
					</div>
					{#if missingN}<span class="hint">À compléter</span>{/if}
				</div>
			</div>
			<div class="f">
				<span class="flab">{@html lab('Genre', 'TCON')}</span>
				<GenrePicker bind:value={v.genre} id="te-genre" />
			</div>
		</div>

		{#if isAdmin}
			<details class="expert">
				<summary><Icon name="spark" size={16} />Mode expert<span class="tag-expert">Admin</span></summary>
				<div class="form">
					{#each EXPERT_KEYS as k (k)}
						<div class="f">
							<label for="te-x-{k}">{ID3_LABELS[k] ?? k}</label>
							<input id="te-x-{k}" class="inp" bind:value={expert[k]} />
						</div>
					{/each}
				</div>
				<div class="meta-layout details">
					<SongDetails {meta} albumCoverUrl={coverUrl(albumPath)} />
				</div>
			</details>
		{/if}
		{#if saveError}<p class="err-title" role="alert">{saveError}</p>{/if}
	{/if}

	{#snippet foot()}
		<div class="sheet-foot">
			<button type="button" class="btn btn-soft" onclick={onClose}>Annuler</button>
			<button type="button" class="btn btn-primary" onclick={save} disabled={!meta || saving}>{saving ? 'Enregistrement…' : 'Enregistrer'}</button>
		</div>
	{/snippet}
</Sheet>

<style>
	.album-line { display: flex; align-items: center; justify-content: space-between; gap: var(--s2); }
	.album-name { font-weight: 600; overflow-wrap: anywhere; }
	.with-ico { display: inline-flex; align-items: center; gap: 6px; flex: none; }
	.pair { display: grid; grid-template-columns: 1fr auto 1fr; gap: 8px; align-items: center; color: var(--text-2); font-size: 14px; }
	.pair .inp { text-align: center; }
	.expert { border: 1px solid var(--sep); border-radius: 14px; padding: 4px 12px; }
	.expert summary { cursor: pointer; padding: 10px 0; font-weight: 600; display: flex; align-items: center; gap: 8px; }
	.expert[open] summary { border-bottom: 1px solid var(--sep); margin-bottom: 10px; }
	.expert .form { padding-bottom: 12px; }
	.details { height: auto; }
</style>
