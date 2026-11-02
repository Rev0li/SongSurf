<script>
	// Outils experts (admin, SSF-13) : leur fonctionnement ne change pas, seul
	// l'accès passe par les menus « ⋯ ». Ils gardent les styles de metadata.css.
	import { onMount, untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { api } from '$lib/api.js';
	import { closeSheet } from '$lib/ui/sheets.js';
	import { tree, findArtist, findAlbum, refreshLibrary, sortByTrck } from '$lib/library/data.js';
	import '$lib/styles/metadata.css'; // outils experts existants (préfixe .meta-layout)
	import Sheet from '../ui/Sheet.svelte';
	import ArtistAudit from '../metadata/ArtistAudit.svelte';
	import AlbumReorder from '../metadata/AlbumReorder.svelte';
	import ArtistGenre from '../metadata/ArtistGenre.svelte';

	let { tool, artistPath = '', albumPath = '', onDone = () => {}, onClose } = $props();

	const TITLES = { audit: 'Vérifier avec iTunes', renumber: 'Numéroter les pistes', genre: "Genre de l'artiste" };
	const artist = untrack(() => (artistPath ? findArtist(get(tree), artistPath) : null));
	const album = untrack(() => (albumPath ? findAlbum(get(tree), albumPath)?.album : null));

	let tracks = $state(null);
	let albumStatus = $state({});

	onMount(async () => {
		if (tool === 'renumber') {
			try { tracks = sortByTrck((await api.albumTracks(albumPath)).tracks ?? []); } catch { tracks = []; }
		} else if (tool === 'genre') {
			await loadStatus();
		}
	});

	async function loadStatus() {
		try {
			const data = await api.albumStatus(artistPath);
			albumStatus = Object.fromEntries((data.albums ?? []).map((a) => [a.path, a]));
		} catch { albumStatus = {}; }
	}

	function saved() {
		refreshLibrary();
		onDone();
		closeSheet();
	}
</script>

<Sheet title={TITLES[tool]} sub={artist?.name ?? album?.name ?? ''} tall {onClose}>
	<div class="meta-layout tool">
		{#if tool === 'audit'}
			<ArtistAudit {artistPath} />
		{:else if tool === 'renumber'}
			{#if tracks}
				<AlbumReorder {albumPath} {tracks} onSaved={saved} onCancel={onClose} />
			{:else}
				<div class="spinner" aria-label="Chargement"></div>
			{/if}
		{:else if tool === 'genre' && artist}
			<ArtistGenre {artist} albums={artist.albums ?? []} {albumStatus} onApplied={() => { loadStatus(); refreshLibrary(); }} />
		{/if}
	</div>
</Sheet>

<style>
	.tool { height: auto; display: block; }
</style>
