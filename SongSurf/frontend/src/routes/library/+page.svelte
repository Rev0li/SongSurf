<script>
	// « Ma musique » (SSF-13) : navigation en pile façon appli de musique.
	// /library → accueil · ?artist=<dossier> → artiste · ?album=<Artiste/Album> → album
	import { onMount } from 'svelte';
	import { goto, afterNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import { refreshLibrary } from '$lib/library/data.js';
	import LibraryHome from '$lib/components/library/LibraryHome.svelte';
	import ArtistView from '$lib/components/library/ArtistView.svelte';
	import AlbumView from '$lib/components/library/AlbumView.svelte';

	let artistPath = $derived(page.url.searchParams.get('artist'));
	let albumPath = $derived(page.url.searchParams.get('album'));

	// Retour : si la page précédente est la page parente, on recule dans l'historique
	// (position de défilement et recherche retrouvées) ; sinon on y va directement.
	let previous = '';
	afterNavigate(({ from }) => {
		previous = from?.url ? from.url.pathname + from.url.search : '';
	});
	function back(parentHref) {
		if (previous === parentHref) history.back();
		else goto(parentHref);
	}

	onMount(refreshLibrary);
</script>

<svelte:head><title>Ma musique — SongSurf</title></svelte:head>

{#if albumPath}
	<AlbumView path={albumPath} onBack={back} />
{:else if artistPath}
	<ArtistView path={artistPath} onBack={back} />
{:else}
	<LibraryHome />
{/if}
