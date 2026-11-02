<script>
	// « Modifier l'album » (SSF-13) : nom (tags + dossier), année, genre, écrits
	// sur tous les titres. Une fenêtre montre l'avant → après avant d'appliquer.
	import { onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { api } from '$lib/api.js';
	import { addToast, confirmAction } from '$lib/stores.js';
	import { closeSheet, closeSheetAndGo } from '$lib/ui/sheets.js';
	import { tree, findAlbum, coverUrl, refreshLibrary, albumUrl, plural } from '$lib/library/data.js';
	import Sheet from '../ui/Sheet.svelte';
	import Cover from '../ui/Cover.svelte';
	import GenrePicker from '../ui/GenrePicker.svelte';

	let { albumPath, onClose } = $props();

	const located = untrack(() => findAlbum(get(tree), albumPath)); // panneau remonté à chaque ouverture
	let loaded = $state(false);
	let saving = $state(false);
	let error = $state('');
	let nTracks = $state(located?.album.songs?.length ?? 0);
	let initial = { name: located?.album.name ?? '', year: '', genre: '' };
	let name = $state(initial.name);
	let year = $state('');
	let genre = $state('');

	// Valeur la plus fréquente parmi les titres (vide si aucune)
	function mostCommon(values) {
		const counts = new Map();
		for (const x of values.filter(Boolean)) counts.set(x, (counts.get(x) ?? 0) + 1);
		return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '';
	}

	onMount(async () => {
		try {
			const data = await api.albumTracks(albumPath);
			const tracks = data.tracks ?? [];
			nTracks = tracks.length;
			initial.year = mostCommon(tracks.map((t) => t.year));
			initial.genre = mostCommon(tracks.map((t) => (t.genres ?? []).join('; ')));
			year = initial.year;
			genre = initial.genre;
		} catch (e) { error = e.message ?? 'Erreur'; }
		finally { loaded = true; }
	});

	async function save() {
		if (saving) return;
		error = '';
		const fields = {};
		const lines = [];
		const n = name.trim(), y = year.trim();
		if (!n) { error = "L'album doit avoir un nom."; return; }
		if (y && !/^\d{4}$/.test(y)) { error = "L'année doit avoir 4 chiffres (ex. 2017)."; return; }
		if (n !== initial.name) { fields.album = n; lines.push(`Nom : ${initial.name} → ${n}`); }
		if (y !== initial.year) { fields.year = y; lines.push(`Année : ${initial.year || 'vide'} → ${y || 'vide'}`); }
		if (genre !== initial.genre) { fields.genre = genre; lines.push(`Genre : ${initial.genre || 'vide'} → ${genre || 'vide'}`); }
		if (lines.length === 0) { closeSheet(); return; }

		const ok = await confirmAction({
			title: `Modifier l'album « ${initial.name} » ?`,
			message: [
				...lines, '',
				`Les ${plural(nTracks, 'titre')} de l'album seront mis à jour.`,
				...(fields.album ? ['Le dossier de l\'album est renommé aussi.'] : []),
			].join('\n'),
			confirmLabel: 'Appliquer',
		});
		if (!ok) return;
		saving = true;
		try {
			const res = await api.saveAlbumTags(albumPath, fields);
			if ((res.errors ?? []).length) addToast(`${res.updated} titres modifiés, ${res.errors.length} en erreur.`, 'error');
			else addToast('Album mis à jour.', 'info');
			await refreshLibrary();
			if (res.path && res.path !== albumPath) closeSheetAndGo(albumUrl(res.path));
			else closeSheet();
		} catch (e) { error = e.message ?? 'Erreur'; }
		finally { saving = false; }
	}
</script>

<Sheet title="Modifier l'album" sub={located ? `${located.album.name}${located.artist ? ` · ${located.artist.name}` : ''}` : albumPath} tall {onClose}>
	{#snippet lead()}<Cover src={coverUrl(albumPath)} label={initial.name} size={44} />{/snippet}
	<p class="note">Ces infos sont écrites dans les {plural(nTracks, 'titre')} de l'album.</p>
	<div class="form">
		<div class="f"><label for="ae-name">Nom de l'album</label><input id="ae-name" class="inp" bind:value={name} /></div>
		<div class="f">
			<label for="ae-year">Année</label>
			<input id="ae-year" class="inp" bind:value={year} inputmode="numeric" maxlength="4" placeholder="ex. 2017" disabled={!loaded} />
		</div>
		<div class="f">
			<span class="flab">Genre</span>
			{#if loaded}<GenrePicker bind:value={genre} id="ae-genre" />{/if}
		</div>
	</div>
	{#if error}<p class="err-title" role="alert">{error}</p>{/if}

	{#snippet foot()}
		<div class="sheet-foot">
			<button type="button" class="btn btn-soft" onclick={onClose}>Annuler</button>
			<button type="button" class="btn btn-primary" onclick={save} disabled={!loaded || saving}>{saving ? 'Enregistrement…' : 'Enregistrer'}</button>
		</div>
	{/snippet}
</Sheet>
