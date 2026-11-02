<script>
	// Page d'un artiste : photo, albums. « ⋯ » : photo, et outils experts pour l'admin.
	import { tree, treeLoaded, todo, findArtist, albumUrl, coverUrl, pictureUrl, LIBRARY_URL, plural, countSongs, pastedImage } from '$lib/library/data.js';
	import { artistMenu, changeArtistPicture, pickImage } from '$lib/library/actions.js';
	import Icon from '../ui/Icon.svelte';
	import Cover from '../ui/Cover.svelte';

	let { path, onBack } = $props();

	let artist = $derived(findArtist($tree, path));
	let todoSet = $derived(new Set(($todo ?? []).map((a) => a.path)));

	function onPaste(e) {
		const file = pastedImage(e);
		if (file) changeArtistPicture(path, file);
	}
</script>

<svelte:window onpaste={onPaste} />
<svelte:head><title>{artist?.name ?? 'Artiste'} — SongSurf</title></svelte:head>

<section class="page">
	<button type="button" class="link-btn back" onclick={() => onBack(LIBRARY_URL)}><Icon name="back" />Ma musique</button>

	{#if !artist}
		{#if $treeLoaded}
			<div class="empty"><h2>Artiste introuvable</h2><p>Il a peut-être été déplacé ou supprimé.</p></div>
		{:else}
			<div class="spinner" aria-label="Chargement"></div>
		{/if}
	{:else}
		<div class="hero">
			<div class="avatar"><Cover src={artist.has_picture ? pictureUrl(path) : ''} label={artist.name} round /></div>
			<h1>{artist.name}</h1>
			<p class="why">{plural(artist.albums.length, 'album')} · {plural(countSongs(artist.albums), 'titre')}</p>
			<div class="actions">
				<button type="button" class="btn btn-soft btn-sm with-ico" onclick={async () => changeArtistPicture(path, await pickImage())}>
					<Icon name="image" size={16} />Changer la photo
				</button>
				<button type="button" class="icon-btn" onclick={() => artistMenu(path)} aria-label="Plus d'actions sur {artist.name}"><Icon name="more" /></button>
			</div>
		</div>

		<h2 class="sec-title">Albums</h2>
		<div class="grid-albums">
			{#each artist.albums as album (album.path)}
				<a class="tile" href={albumUrl(album.path)}>
					<Cover src={coverUrl(album.path)} label={album.name} radius={14} />
					{#if todoSet.has(album.path)}<span class="tile-badge" title="Infos à compléter"><Icon name="warn" size={14} /></span>{/if}
					<span class="tile-name">{album.name}</span>
					<span class="tile-meta">{plural(album.songs?.length ?? 0, 'titre')}</span>
				</a>
			{/each}
		</div>
	{/if}
</section>

<style>
	.back { display: inline-flex; align-items: center; gap: 2px; align-self: flex-start; padding: 4px 0; }
	.hero { display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; }
	.hero h1 { margin: 0; font-size: 26px; }
	.avatar { width: 132px; }
	.actions { display: flex; gap: var(--s2); align-items: center; margin-top: 4px; }
	.with-ico { display: inline-flex; align-items: center; gap: 6px; }
	.tile { text-decoration: none; }
</style>
