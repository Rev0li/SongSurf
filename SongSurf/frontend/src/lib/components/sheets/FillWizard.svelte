<script>
	// « À remplir » (SSF-13) : album par album, seules les infos manquantes sont
	// demandées. Année et genre sont écrits sur tout l'album, les numéros de piste
	// titre par titre (numéros libres proposés). Passer garde l'album dans la liste.
	import { onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { closeSheet } from '$lib/ui/sheets.js';
	import {
		todo, tree, findAlbum, parentPath, refreshLibrary, coverUrl, trackNum, songTitle, plural,
	} from '$lib/library/data.js';
	import { GENRES } from '$lib/library/genres.js';
	import Sheet from '../ui/Sheet.svelte';
	import Cover from '../ui/Cover.svelte';
	import GenrePicker from '../ui/GenrePicker.svelte';
	import Icon from '../ui/Icon.svelte';

	let { albums = null, onChanged = () => {}, onClose } = $props();

	// Liste figée à l'ouverture : les albums complétés n'en disparaissent pas en cours de route
	const steps = untrack(() => albums ?? (get(todo) ?? []).map((a) => a.path));
	let i = $state(0);
	let done = $state(0);
	let skipped = $state(0);
	let saving = $state(false);
	let error = $state('');
	let bodyEl = $state(null);

	// Étape courante
	let tracks = $state(null);
	let year = $state('');
	let genre = $state('');
	let numbers = $state({}); // path → n
	const genreByArtist = new Map(); // genre choisi dans cette session, par artiste
	const statusCache = new Map();   // artiste → album-status (genres des autres albums)

	let path = $derived(steps[i]);
	let located = $derived(path ? findAlbum(get(tree), path) : null);
	let artistPath = $derived(path ? parentPath(path) : '');
	let need = $derived(tracks ? {
		year: tracks.some((t) => !t.year),
		numbers: tracks.filter((t) => isNaN(trackNum(t))),
		genre: tracks.some((t) => !(t.genres ?? []).length),
	} : null);
	let knownYear = $derived(tracks?.find((t) => t.year)?.year ?? '');
	let noYearCount = $derived(tracks ? tracks.filter((t) => !t.year).length : 0);
	let taken = $derived(tracks ? tracks.map(trackNum).filter((n) => !isNaN(n)).sort((a, b) => a - b) : []);
	let suggestion = $state('');

	onMount(() => { if (steps.length) enter(); });

	async function enter() {
		tracks = null; error = ''; year = ''; genre = ''; numbers = {}; suggestion = '';
		bodyEl?.scrollTo?.({ top: 0 });
		const p = steps[i];
		try {
			const data = await api.albumTracks(p);
			const list = data.tracks ?? [];
			// Numéros libres proposés aux titres sans numéro, dans l'ordre reçu
			const used = new Set(list.map(trackNum).filter((n) => !isNaN(n)));
			let k = 1;
			const nums = {};
			for (const t of list.filter((t) => isNaN(trackNum(t)))) {
				while (used.has(k)) k++;
				used.add(k);
				nums[t.path] = String(k);
			}
			numbers = nums;
			year = list.find((t) => t.year)?.year ?? '';
			tracks = list;
			if (list.some((t) => !(t.genres ?? []).length)) suggestion = await genreSuggestion(parentPath(p), p);
			// Album déjà complet (corrigé ailleurs entre-temps) → on passe au suivant
			if (!hasNeeds(list)) { done++; next(); }
		} catch (e) { error = e.message ?? 'Erreur'; tracks = []; }
	}

	function hasNeeds(list) {
		return list.some((t) => !t.year || isNaN(trackNum(t)) || !(t.genres ?? []).length);
	}

	// Genre des autres albums de l'artiste : celui choisi dans cette session, sinon
	// celui déjà écrit (style générique d'abord : « Hip-Hop/Rap; French Rap »).
	async function genreSuggestion(artist, albumPath) {
		if (genreByArtist.has(artist)) return genreByArtist.get(artist);
		try {
			if (!statusCache.has(artist)) statusCache.set(artist, (await api.albumStatus(artist)).albums ?? []);
			const other = statusCache.get(artist).find((a) => a.path !== albumPath && (a.genres ?? []).length);
			if (!other) return '';
			return [...other.genres].sort((a, b) => (b in GENRES) - (a in GENRES)).join('; ');
		} catch { return ''; }
	}

	function next() {
		i++;
		if (i < steps.length) enter();
		else onChanged();
	}

	function skip() { skipped++; next(); }

	async function saveStep() {
		if (saving || !tracks) return;
		error = '';
		const y = year.trim();
		if (need.year && y && !/^\d{4}$/.test(y)) { error = "L'année doit avoir 4 chiffres (ex. 2017)."; return; }
		for (const t of need.numbers) {
			const n = (numbers[t.path] ?? '').trim();
			if (n && !/^\d+$/.test(n)) { error = `Numéro de piste invalide pour « ${t.title || songTitle(t.name)} ».`; return; }
		}
		saving = true;
		try {
			const fields = {};
			if (need.year && y) fields.year = y;
			if (need.genre && genre) fields.genre = genre;
			if (Object.keys(fields).length) await api.saveAlbumTags(path, fields);
			const total = tracks.length;
			for (const t of need.numbers) {
				const n = (numbers[t.path] ?? '').trim();
				if (n) await api.saveSongMeta(t.path, { track_number: `${n}/${total}` });
			}
			if (genre) genreByArtist.set(artistPath, genre);
			const complete = (!need.year || y) && (!need.genre || genre) && need.numbers.every((t) => (numbers[t.path] ?? '').trim());
			if (complete) done++; else skipped++;
			next();
		} catch (e) { error = e.message ?? 'Erreur'; }
		finally { saving = false; }
	}

	function finish() {
		refreshLibrary();
		closeSheet();
	}

	function close() {
		if (done > 0) refreshLibrary();
		onClose();
	}
</script>

<Sheet title="À remplir" sub={i < steps.length ? 'Seules les infos manquantes sont demandées' : 'Terminé'} tall onClose={close} bind:bodyEl>
	<div class="prog" aria-hidden="true"><i style="width:{steps.length ? (Math.min(i, steps.length) / steps.length) * 100 : 100}%"></i></div>

	{#if steps.length === 0}
		<div class="empty"><Icon name="check" size={28} /><h2>Rien à remplir</h2><p>Toutes tes infos sont complètes.</p></div>
	{:else if i >= steps.length}
		<div class="empty">
			<Icon name="check" size={28} />
			<h2>C'est rempli !</h2>
			<p>
				{plural(done, 'album complété', 'albums complétés')}.
				{#if skipped}{plural(skipped, 'album passé', 'albums passés')} : tu les retrouves dans « À remplir ».{/if}
			</p>
		</div>
	{:else}
		<div class="head">
			<Cover src={coverUrl(path)} label={located?.album.name ?? path} size={72} radius={12} />
			<div class="head-txt">
				<span class="kind">Album {i + 1} sur {steps.length}</span>
				<strong>{located?.album.name ?? path.split('/').pop()}</strong>
				<span class="why">{located?.artist?.name ?? ''}{tracks ? ` · ${plural(tracks.length, 'titre')}` : ''}</span>
			</div>
		</div>

		{#if !tracks}
			<div class="spinner" aria-label="Chargement"></div>
		{:else if need}
			{#if need.year}
				<section class="wsec">
					<h3>Année de sortie</h3>
					<p class="why">
						{noYearCount === tracks.length ? "Aucun titre de cet album n'a d'année." : `${plural(noYearCount, 'titre')} sans année, les autres ont ${knownYear}.`}
						Elle sera écrite sur tout l'album.
					</p>
					<input class="inp" id="w-year" bind:value={year} inputmode="numeric" maxlength="4" placeholder="ex. 2017" aria-label="Année de sortie" />
				</section>
			{/if}
			{#if need.numbers.length}
				<section class="wsec">
					<h3>Numéro de piste</h3>
					<p class="why">
						Indique la place {need.numbers.length > 1 ? 'de ces titres' : 'de ce titre'} dans l'album.
						{#if taken.length}Déjà pris : {taken.join(', ')}.{/if} On propose les numéros libres.
					</p>
					{#each need.numbers as t (t.path)}
						<div class="ntrack">
							<label for="w-n-{t.path}">{t.title || songTitle(t.name)}</label>
							<input class="inp" id="w-n-{t.path}" bind:value={numbers[t.path]} inputmode="numeric" />
						</div>
					{/each}
				</section>
			{/if}
			{#if need.genre}
				<section class="wsec">
					<h3>Genre</h3>
					<p class="why">Il sera écrit sur les {plural(tracks.length, 'titre')} de l'album.</p>
					{#key path}<GenrePicker bind:value={genre} {suggestion} startOpen id="w-genre" />{/key}
				</section>
			{/if}
		{/if}
		{#if error}<p class="err-title" role="alert">{error}</p>{/if}
	{/if}

	{#snippet foot()}
		{#if steps.length === 0 || i >= steps.length}
			<div class="sheet-foot one"><button type="button" class="btn btn-primary" onclick={finish}>Terminé</button></div>
		{:else}
			<div class="sheet-foot">
				<button type="button" class="btn btn-soft" onclick={skip} disabled={saving}>Passer</button>
				<button type="button" class="btn btn-primary" onclick={saveStep} disabled={saving || !tracks}>
					{saving ? 'Enregistrement…' : i + 1 < steps.length ? 'Enregistrer, suivant' : 'Enregistrer'}
				</button>
			</div>
		{/if}
	{/snippet}
</Sheet>

<style>
	.prog { height: 4px; background: var(--bg-4); border-radius: 4px; overflow: hidden; flex: none; }
	.prog i { display: block; height: 100%; background: var(--accent); transition: width .3s; }
	.head { display: flex; gap: var(--s3); align-items: center; }
	.head-txt { min-width: 0; display: flex; flex-direction: column; }
	.head-txt strong { font-size: 17px; overflow-wrap: anywhere; }
	.kind { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px; color: var(--accent-ink); }
	.wsec { display: flex; flex-direction: column; gap: 8px; padding: 12px; border: 1px solid var(--sep); border-radius: 14px; }
	.wsec h3 { margin: 0; font-size: 15px; }
	.ntrack { display: grid; grid-template-columns: 1fr 72px; gap: 10px; align-items: center; font-size: 14px; }
	.ntrack .inp { text-align: center; }
</style>
