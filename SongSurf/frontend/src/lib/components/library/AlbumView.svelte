<script>
	// Page d'un album : pochette, infos, « À remplir » s'il manque des infos,
	// « Modifier l'album », liste des titres (toucher = modifier, « ⋯ » = actions).
	import { api } from '$lib/api.js';
	import { openSheet } from '$lib/ui/sheets.js';
	import {
		tree, treeLoaded, todo, findAlbum, artistUrl, coverUrl, LIBRARY_URL,
		sortByTrck, trackNum, trackMissing, songTitle, plural, pastedImage,
	} from '$lib/library/data.js';
	import { albumMenu, trackMenu, changeAlbumCover } from '$lib/library/actions.js';
	import Icon from '../ui/Icon.svelte';
	import Cover from '../ui/Cover.svelte';
	import TrackRow from './TrackRow.svelte';
	import { beforeNavigate } from '$app/navigation';
	import { zoomFrom } from '$lib/ui/albumZoom.js';

	let { path, onBack } = $props();

	let located = $derived(findAlbum($tree, path));

	// Vol de pochette (lib/ui/albumZoom.js) : à l'arrivée, la pochette touchée se
	// pose sur data-zoom-hero ; en repartant vers l'artiste ou « Ma musique »,
	// elle revient se poser à sa place dans le Cover Flow / la grille.
	let heroEl = $state();
	beforeNavigate(({ to, willUnload }) => {
		if (willUnload || !heroEl || to?.url.pathname !== '/library' || to.url.searchParams.has('album')) return;
		zoomFrom(heroEl, path, null, 'back');
	});
	let tracks = $state(null);
	let loadedFor = '';

	// Recharge la tracklist (tags réels) quand l'album change ou que l'arbre bouge
	$effect(() => {
		const p = path, songCount = located?.album.songs?.length ?? 0;
		if (p !== loadedFor) tracks = null;
		load(p, songCount);
	});

	let pending = 0;
	async function load(p) {
		const ticket = ++pending;
		try {
			const data = await api.albumTracks(p);
			if (ticket === pending) { tracks = sortByTrck(data.tracks ?? []); loadedFor = p; }
		} catch { if (ticket === pending) { tracks = tracks ?? []; loadedFor = p; } }
	}
	const reload = () => load(path);

	function mostCommon(values) {
		const counts = new Map();
		for (const x of values.filter(Boolean)) counts.set(x, (counts.get(x) ?? 0) + 1);
		return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '';
	}

	let year = $derived(tracks ? mostCommon(tracks.map((t) => t.year)) : '');
	let genre = $derived(tracks ? mostCommon(tracks.map((t) => (t.genres ?? []).join('; '))) : '');
	let inTodo = $derived(($todo ?? []).some((a) => a.path === path));
	let albumArtist = $derived(located?.artist?.name ?? '');
	let rows = $derived(tracks ?? (located?.album.songs ?? []).map((s) => ({ ...s, title: '', track_number: '' })));

	const titleOf = (t) => t.title || songTitle(t.name);
	function subOf(t) {
		const others = (t.artists ?? []).filter((a) => a !== albumArtist);
		return others.length ? (t.artists ?? []).join(', ') : '';
	}

	function onPaste(e) {
		const file = pastedImage(e);
		if (file) changeAlbumCover(path, file);
	}
</script>

<svelte:window onpaste={onPaste} />
<svelte:head><title>{located?.album.name ?? 'Album'} — SongSurf</title></svelte:head>

<section class="page">
	<button type="button" class="link-btn back" onclick={() => onBack(located?.artist ? artistUrl(located.artist.path) : LIBRARY_URL)}>
		<Icon name="back" />{located?.artist?.name ?? 'Ma musique'}
	</button>

	{#if !located}
		{#if $treeLoaded}
			<div class="empty"><h2>Album introuvable</h2><p>Il a peut-être été renommé, déplacé ou supprimé.</p></div>
		{:else}
			<div class="spinner" aria-label="Chargement"></div>
		{/if}
	{:else}
		<div class="hero">
			<div class="cover" bind:this={heroEl} data-zoom-hero={path}><Cover src={coverUrl(path)} label={located.album.name} radius={16} /></div>
			<h1>{located.album.name}</h1>
			{#if located.artist}<a class="link-btn" href={artistUrl(located.artist.path)}>{located.artist.name}</a>{/if}
			<p class="why">{year || 'Année inconnue'} · {plural(located.album.songs?.length ?? 0, 'titre')}{genre ? ` · ${genre}` : ''}</p>
			<div class="actions">
				{#if inTodo}
					<button type="button" class="btn btn-primary btn-sm with-ico" onclick={() => openSheet('fill', { albums: [path], onChanged: reload })}>
						<Icon name="edit" size={16} />À remplir
					</button>
				{/if}
				<button type="button" class="btn btn-soft btn-sm with-ico" onclick={() => openSheet('editAlbum', { albumPath: path })}>
					<Icon name="edit" size={16} />Modifier l'album
				</button>
				<button type="button" class="icon-btn" onclick={() => albumMenu(path)} aria-label="Plus d'actions sur l'album"><Icon name="more" /></button>
			</div>
		</div>

		<ul class="rows">
			{#each rows as t (t.path)}
				<TrackRow
					title={titleOf(t)} sub={subOf(t)} num={isNaN(trackNum(t)) ? '–' : trackNum(t)}
					missing={tracks ? trackMissing(t) : []}
					onOpen={() => openSheet('editTrack', { path: t.path, onSaved: reload })}
					onMenu={() => trackMenu({ path: t.path, title: titleOf(t), sub: located.album.name, albumPath: path, onChanged: reload })}
				/>
			{/each}
		</ul>
		<p class="tip">Touche un titre pour modifier ses infos.</p>
	{/if}
</section>

<style>
	.back { display: inline-flex; align-items: center; gap: 2px; align-self: flex-start; padding: 4px 0; }
	.hero { display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; }
	.hero h1 { margin: 0; font-size: 26px; overflow-wrap: anywhere; }
	.cover { width: min(220px, 60vw); box-shadow: var(--shadow-soft); border-radius: 16px; }
	.actions { display: flex; gap: var(--s2); align-items: center; flex-wrap: wrap; justify-content: center; margin-top: 4px; }
	.with-ico { display: inline-flex; align-items: center; gap: 6px; }
	a.link-btn { text-decoration: none; }
	.tip { margin: 0; font-size: 13px; color: var(--text-3); text-align: center; }
</style>
