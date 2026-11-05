<script module>
	// Recherche et onglet gardés quand on revient d'une page artiste / album
	import { writable } from 'svelte/store';
	const ui = writable({ seg: 'artists', q: '' });
</script>

<script>
	// Accueil de « Ma musique » (SSF-13) : recherche, Artistes / Albums / Titres,
	// bouton « À remplir », et pour les membres « Récupérer ma musique ».
	import { user } from '$lib/stores.js';
	import { myDownloads } from '$lib/downloads.js';
	import { openSheet } from '$lib/ui/sheets.js';
	import {
		tree, treeLoaded, todo, allAlbums, allSongs, artistUrl, albumUrl, coverUrl, pictureUrl,
		songTitle, plural, countSongs,
	} from '$lib/library/data.js';
	import { trackMenu } from '$lib/library/actions.js';
	import { matcher } from '$lib/utils.js';
	import { zoomFrom } from '$lib/ui/albumZoom.js';
	import Icon from '../ui/Icon.svelte';
	import Cover from '../ui/Cover.svelte';
	import TrackRow from './TrackRow.svelte';

	const PAGE = 200;
	let limit = $state(PAGE);

	let isAdmin = $derived($user?.role === 'admin');
	let artists = $derived($tree?.artists ?? []);
	let albums = $derived(allAlbums($tree));
	let songs = $derived(allSongs($tree).sort((a, b) => a.song.name.localeCompare(b.song.name, 'fr')));
	let todoCount = $derived(($todo ?? []).length);
	let todoSet = $derived(new Set(($todo ?? []).map((a) => a.path)));

	// Recherche permissive (accents, casse, ponctuation, ordre des mots) : un album
	// se trouve aussi par son artiste, un titre par son artiste ou son album.
	let q = $derived($ui.q.trim());
	let found = $derived.by(() => {
		if (!q) return null;
		const hit = matcher(q);
		return {
			artists: artists.filter((a) => hit(a.name)),
			albums: albums.filter(({ artist, album }) => hit(`${album.name} ${artist?.name ?? ''}`)),
			songs: songs.filter(({ artist, album, song }) => hit(`${song.name} ${artist?.name ?? ''} ${album.name}`)).slice(0, 100),
		};
	});

	const setSeg = (seg) => { ui.update((u) => ({ ...u, seg })); limit = PAGE; };
	const songSub = ({ artist, album }) => `${artist?.name ?? 'Playlist'} · ${album.name}`;
</script>

{#snippet artistGrid(list)}
	<div class="grid-artists">
		{#each list as a (a.path)}
			<a class="tile center" href={artistUrl(a.path)}>
				<Cover src={a.has_picture ? pictureUrl(a.path) : ''} label={a.name} round />
				<span class="tile-name">{a.name}</span>
				<span class="tile-meta">{plural(a.albums.length, 'album')}</span>
			</a>
		{/each}
	</div>
{/snippet}

{#snippet albumGrid(list)}
	<div class="grid-albums">
		{#each list as { artist, album } (album.path)}
			<a class="tile" href={albumUrl(album.path)} data-morph={album.path} onclick={(e) => zoomFrom(e.currentTarget.querySelector('.cover'), album.path, e)}>
				<Cover src={coverUrl(album.path)} label={album.name} radius={14} />
				{#if todoSet.has(album.path)}<span class="tile-badge" title="Infos à compléter"><Icon name="warn" size={14} /></span>{/if}
				<span class="tile-name">{album.name}</span>
				<span class="tile-meta">{artist?.name ?? 'Playlist'} · {plural(album.songs?.length ?? 0, 'titre')}</span>
			</a>
		{/each}
	</div>
{/snippet}

{#snippet songList(list)}
	<ul class="rows">
		{#each list as s (s.song.path)}
			<TrackRow
				title={songTitle(s.song.name)} sub={songSub(s)} coverSrc={coverUrl(s.album.path)} coverLabel={s.album.name}
				onOpen={() => openSheet('editTrack', { path: s.song.path })}
				onMenu={() => trackMenu({ path: s.song.path, title: songTitle(s.song.name), sub: songSub(s), albumPath: s.album.path })}
			/>
		{/each}
	</ul>
{/snippet}

<section class="page">
	<div>
		<h1 class="ptitle">Ma musique</h1>
		{#if $tree}
			<p class="why sub">{isAdmin ? 'Bibliothèque Jellyfin · ' : ''}{plural(artists.length, 'artiste')} · {plural(songs.length, 'titre')}</p>
		{/if}
	</div>

	{#if !$tree && !$treeLoaded}
		<div class="spinner" aria-label="Chargement"></div>
	{:else if songs.length === 0}
		<div class="empty">
			<Icon name="music" size={32} />
			<h2>Ta bibliothèque est vide</h2>
			<p>Ajoute des titres depuis l'onglet Ajouter : ils apparaîtront ici, rangés par artiste et par album.</p>
			<a class="btn btn-primary with-ico" href="/"><Icon name="plus" />Ajouter de la musique</a>
		</div>
	{:else}
		<label class="search">
			<Icon name="search" />
			<input type="search" placeholder="Rechercher un artiste, un album, un titre" autocomplete="off"
				value={$ui.q} oninput={(e) => ui.update((u) => ({ ...u, q: e.currentTarget.value }))} aria-label="Rechercher dans ma musique" />
		</label>

		{#if todoCount > 0 && !q}
			<button type="button" class="todo" onclick={() => openSheet('fill', {})}>
				<span class="todo-ic"><Icon name="edit" size={16} /></span>
				<span class="todo-txt">
					<b>À remplir</b>
					<small>{plural(todoCount, 'album')} avec des infos manquantes : on les complète ensemble, étape par étape</small>
				</span>
				<Icon name="next" size={16} />
			</button>
		{/if}

		{#if found}
			{#if !found.artists.length && !found.albums.length && !found.songs.length}
				<div class="empty"><h2>Aucun résultat</h2><p>Rien ne correspond à « {$ui.q} ». Vérifie l'orthographe ou cherche un autre mot.</p></div>
			{/if}
			{#if found.artists.length}<div class="group-title">Artistes</div>{@render artistGrid(found.artists)}{/if}
			{#if found.albums.length}<div class="group-title">Albums</div>{@render albumGrid(found.albums)}{/if}
			{#if found.songs.length}<div class="group-title">Titres</div>{@render songList(found.songs)}{/if}
		{:else}
			<div class="segs" role="tablist" aria-label="Affichage">
				{#each [['artists', 'Artistes'], ['albums', 'Albums'], ['songs', 'Titres']] as [k, l] (k)}
					<button type="button" role="tab" aria-selected={$ui.seg === k} onclick={() => setSeg(k)}>{l}</button>
				{/each}
			</div>
			{#if $ui.seg === 'artists'}
				{@render artistGrid(artists)}
			{:else if $ui.seg === 'albums'}
				{@render albumGrid(albums)}
			{:else}
				{@render songList(songs.slice(0, limit))}
				{#if songs.length > limit}
					<button type="button" class="btn btn-soft" onclick={() => (limit += PAGE)}>Afficher {Math.min(PAGE, songs.length - limit)} titres de plus</button>
				{/if}
			{/if}
		{/if}
	{/if}
</section>

{#if !isAdmin && songs.length > 0}
	<div class="recover-space" aria-hidden="true"></div>
	<div class="recover" class:lifted={$myDownloads.active}>
		<button type="button" class="btn btn-dark btn-big btn-block" onclick={() => openSheet('recover')}>
			<span class="with-ico"><Icon name="down" />Récupérer ma musique</span>
			<small>{plural(songs.length, 'titre')} · ZIP</small>
		</button>
	</div>
{/if}

<style>
	.sub { margin-top: 4px; font-size: 14px; }
	.with-ico { display: inline-flex; align-items: center; gap: 8px; }
	a.btn { text-decoration: none; }
	.tile { text-decoration: none; }
	.search {
		display: flex; align-items: center; gap: 8px; padding: 0 12px; border-radius: 12px;
		background: var(--bg-4); color: var(--text-2);
	}
	.search input { flex: 1; min-width: 0; border: 0; background: none; outline: none; padding: 11px 0; color: var(--text); font: inherit; }
	.segs { display: grid; grid-template-columns: repeat(3, 1fr); background: var(--bg-4); border-radius: 11px; padding: 3px; }
	.segs button { padding: 7px 0; border-radius: 9px; border: 0; background: none; font: inherit; font-size: 14px; font-weight: 600; color: var(--text-2); cursor: pointer; }
	.segs button[aria-selected='true'] { background: var(--bg-2); color: var(--text); box-shadow: 0 1px 4px rgba(0, 0, 0, .08); }
	.todo {
		display: flex; align-items: center; gap: 12px; width: 100%; text-align: left; padding: 12px 14px;
		border-radius: 16px; background: var(--warn-soft); border: 0; color: var(--text); font: inherit; cursor: pointer;
	}
	.todo-ic { width: 36px; height: 36px; border-radius: 50%; background: var(--orange); color: #111; display: grid; place-items: center; flex: none; }
	.todo-txt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
	.todo-txt small { color: var(--text-2); font-size: 13px; }
	.recover {
		position: fixed; z-index: 150; left: 0; right: 0; bottom: calc(var(--tabbar-h) + var(--safe-b));
		padding: 12px var(--s4); max-width: var(--content-w); margin: 0 auto;
		background: linear-gradient(to top, var(--bg) 70%, transparent);
	}
	.recover .btn { display: flex; justify-content: space-between; align-items: center; }
	.recover small { font-weight: 500; opacity: .75; }
	.recover.lifted { bottom: calc(var(--tabbar-h) + var(--safe-b) + 64px); }
	.recover-space { height: 72px; }
	@media (min-width: 900px) {
		.recover { position: static; padding: var(--s5) 0 0; background: none; }
		.recover-space { display: none; }
	}
</style>
