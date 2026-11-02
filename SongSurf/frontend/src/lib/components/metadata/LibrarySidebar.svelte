<script>
	// Arborescence latérale de la bibliothèque (mode expert) : filtre, repli,
	// glisser-déposer d'un titre vers un album / d'un album vers un artiste.
	import { api } from '$lib/api.js';
	import { nrm } from '$lib/utils.js';
	import { addToast } from '$lib/stores.js';
	import {
		LS, lsGet, lsSet, tree, selection, imgVersions,
		selectArtist, selectAlbum, selectSong, dropSelection, refreshTree,
	} from '$lib/metadata/library.js';
	import { songDisplayName, countSongs } from '$lib/metadata/id3.js';

	let filter = '';
	let sidebarCollapsed = lsGet(LS.sidebar) === '1';
	let expanded = new Set();
	try { expanded = new Set(JSON.parse(lsGet(LS.expanded, '[]'))); } catch { /* ignore */ }

	function toggleSidebar() {
		sidebarCollapsed = !sidebarCollapsed;
		lsSet(LS.sidebar, sidebarCollapsed ? '1' : '0');
	}

	function toggleExpand(path) {
		if (expanded.has(path)) expanded.delete(path);
		else expanded.add(path);
		expanded = expanded;
		lsSet(LS.expanded, JSON.stringify([...expanded]));
	}

	// ── Filtre ────────────────────────────────────────────────────────────────
	$: q = nrm(filter);

	$: filteredArtists = !$tree ? [] : ($tree.artists ?? []).map((a) => ({
		...a,
		albums: (a.albums ?? []).map((al) => ({
			...al,
			songs: (al.songs ?? []).filter((s) => !q || nrm([a.name, al.name, s.name].join(' ')).includes(q)),
		})).filter((al) => al.songs.length > 0),
	})).filter((a) => a.albums.length > 0);

	$: filteredPlaylists = !$tree ? [] : ($tree.playlists ?? []).map((pl) => ({
		...pl,
		songs: (pl.songs ?? []).filter((s) => !q || nrm([pl.name, s.name].join(' ')).includes(q)),
	})).filter((pl) => pl.songs.length > 0);

	$: isEmpty = filteredArtists.length === 0 && filteredPlaylists.length === 0;
	$: sel = $selection;

	// ── Glisser-déposer ───────────────────────────────────────────────────────
	let dndType      = ''; // 'song' | 'album'
	let dndSongPath  = '';
	let dndAlbumPath = '';

	function dndStart(e, path, type) {
		dndType = type;
		if (type === 'song') dndSongPath  = path;
		else                 dndAlbumPath = path;
		e.dataTransfer.effectAllowed = 'move';
		e.dataTransfer.setData('text/plain', path);
	}

	function dndEnd() { dndType = ''; dndSongPath = ''; dndAlbumPath = ''; }

	function dndOverAlbum(e) {
		if (dndType !== 'song') return;
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	function dndOverArtist(e) {
		if (dndType !== 'album') return;
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	function dndLeave(e) {
		if (e.relatedTarget && e.currentTarget.contains(e.relatedTarget)) return;
		e.currentTarget.classList.remove('drop-target');
	}

	async function dndDropOnAlbum(e, albumPath) {
		e.preventDefault();
		e.currentTarget.classList.remove('drop-target');
		if (dndType !== 'song') return;
		const source = e.dataTransfer.getData('text/plain') || dndSongPath;
		if (!source || !albumPath) return;
		try {
			await api.moveSong(source, albumPath);
			addToast('Titre déplacé.', 'info');
			if (source === $selection.path) dropSelection({ path: '' });
			await refreshTree();
		} catch (err) { addToast(err.message || 'Déplacement impossible.', 'error'); }
	}

	async function dndDropOnArtist(e, artistPath) {
		e.preventDefault();
		e.currentTarget.classList.remove('drop-target');
		if (dndType !== 'album') return;
		const source = e.dataTransfer.getData('text/plain') || dndAlbumPath;
		if (!source || !artistPath) return;
		try {
			await api.moveFolder(source, artistPath);
			addToast('Album déplacé.', 'info');
			if ($selection.album?.path === source) dropSelection({ album: null });
			await refreshTree();
		} catch (err) { addToast(err.message || 'Déplacement impossible.', 'error'); }
	}
</script>

{#if sidebarCollapsed}
	<button class="sidebar-rail" on:click={toggleSidebar} title="Afficher la bibliothèque">
		<span class="sidebar-rail-icon">»</span>
		<span class="sidebar-rail-label">Bibliothèque</span>
	</button>
{:else}
<aside class="meta-sidebar">
	<div class="sidebar-top">
		<div class="sidebar-search-row">
			<input class="form-input" placeholder="Rechercher…" bind:value={filter} />
			<button class="sidebar-collapse-btn" on:click={toggleSidebar} title="Masquer la bibliothèque">«</button>
		</div>
	</div>

	<div class="sidebar-scroll">
		{#if $tree === null}
			<div class="sidebar-empty">Chargement…</div>
		{:else if isEmpty}
			<div class="sidebar-empty">{filter ? 'Aucun résultat.' : 'Bibliothèque vide.'}</div>
		{:else}
			{#each filteredArtists as artist (artist.path)}
				<!-- Artist = drop zone for albums -->
				<div class="tree-artist"
					on:dragover={dndOverArtist}
					on:dragleave={dndLeave}
					on:drop={(e) => dndDropOnArtist(e, artist.path)}
				>
					<div class="tree-node artist-node {sel.type === 'artist' && sel.artist?.path === artist.path ? 'artist-selected' : ''}">
						<button class="caret-btn" on:click|stopPropagation={() => toggleExpand(artist.path)}>
							{expanded.has(artist.path) || q ? '▾' : '▸'}
						</button>
						<button class="artist-label-btn" on:click={() => selectArtist(artist)}>
							<span class="tree-artist-pic">
								{#if artist.has_picture}
									<img
										src={api.getArtistPictureUrl(artist.path, $imgVersions[artist.path] ?? 0)}
										alt="" loading="lazy"
										on:load={(e) => e.currentTarget.style.display=''}
										on:error={(e) => e.currentTarget.style.display='none'}
									/>
								{/if}
								<span class="tree-artist-pic-fallback">🎤</span>
							</span>
							<span class="tree-label">{artist.name}</span>
							<span class="tree-count">{countSongs(artist.albums)}</span>
						</button>
					</div>

					{#if expanded.has(artist.path) || q}
						{#each artist.albums as album (album.path)}
							<!-- Album = drop zone for songs -->
							<div class="tree-album"
								on:dragover={dndOverAlbum}
								on:dragleave={dndLeave}
								on:drop={(e) => dndDropOnAlbum(e, album.path)}
							>
								<div class="tree-node album-node {sel.type === 'album' && sel.album?.path === album.path ? 'album-selected' : ''}">
									<button class="caret-btn" on:click|stopPropagation={() => toggleExpand(album.path)}>
										{expanded.has(album.path) || q ? '▾' : '▸'}
									</button>
									<span
										class="lib-drag-handle"
										draggable="true"
										title="Glisser l'album vers un autre artiste"
										on:dragstart|stopPropagation={(e) => dndStart(e, album.path, 'album')}
										on:dragend|stopPropagation={dndEnd}
									>⠿</span>
									<button class="album-label-btn" on:click={() => selectAlbum(album, artist)}>
										<span class="tree-icon">💿</span>
										<span class="tree-label">{album.name}</span>
										<span class="tree-count">{album.songs.length}</span>
									</button>
								</div>
								{#if expanded.has(album.path) || q}
									{#each album.songs as song (song.path)}
										<button
											class="song-row {sel.path === song.path ? 'selected' : ''}"
											draggable="true"
											on:dragstart={(e) => dndStart(e, song.path, 'song')}
											on:dragend={dndEnd}
											on:click={() => selectSong(song.path)}
										>
											<span class="song-name">{songDisplayName(song.name)}</span>
										</button>
									{/each}
								{/if}
							</div>
						{/each}
					{/if}
				</div>
			{/each}

			{#each filteredPlaylists as pl (pl.path)}
				<!-- Playlists = drop zone for songs -->
				<div class="tree-artist"
					on:dragover={dndOverAlbum}
					on:dragleave={dndLeave}
					on:drop={(e) => dndDropOnAlbum(e, pl.path)}
				>
					<button class="tree-node" on:click={() => toggleExpand(pl.path)}>
						<span class="tree-caret">{expanded.has(pl.path) || q ? '▾' : '▸'}</span>
						<span class="tree-icon">📁</span>
						<span class="tree-label">{pl.name}</span>
						<span class="tree-count">{pl.songs.length}</span>
					</button>
					{#if expanded.has(pl.path) || q}
						{#each pl.songs as song (song.path)}
							<button
								class="song-row {sel.path === song.path ? 'selected' : ''}"
								draggable="true"
								on:dragstart={(e) => dndStart(e, song.path, 'song')}
								on:dragend={dndEnd}
								on:click={() => selectSong(song.path)}
							>
								<span class="song-name">{songDisplayName(song.name)}</span>
							</button>
						{/each}
					{/if}
				</div>
			{/each}
		{/if}
	</div>
</aside>
{/if}

<style>
	.meta-sidebar {
		width: 300px; flex-shrink: 0;
		border-right: 1px solid var(--sep);
		display: flex; flex-direction: column;
		background: var(--bg-2);
	}
	.sidebar-top {
		padding: var(--s3) var(--s3) var(--s2);
		display: flex; flex-direction: column; gap: var(--s2);
		border-bottom: 1px solid var(--sep);
	}
	.sidebar-search-row { display: flex; align-items: center; gap: var(--s2); }
	.sidebar-search-row .form-input { flex: 1; min-width: 0; }
	.sidebar-collapse-btn {
		flex-shrink: 0;
		width: 28px; height: 28px;
		background: none; border: 1px solid var(--sep);
		border-radius: var(--r-sm);
		color: var(--text-3); font-size: 13px;
		cursor: pointer;
		transition: color .1s, background .1s;
	}
	.sidebar-collapse-btn:hover { color: var(--text); background: rgba(255,255,255,.06); }

	/* Rail affiché quand la sidebar est repliée */
	.sidebar-rail {
		flex-shrink: 0;
		width: 28px;
		display: flex; flex-direction: column; align-items: center;
		gap: var(--s3); padding-top: var(--s3);
		background: var(--bg-2);
		border: none; border-right: 1px solid var(--sep);
		color: var(--text-3); cursor: pointer;
		transition: color .1s, background .1s;
	}
	.sidebar-rail:hover { color: var(--text); background: rgba(255,255,255,.04); }
	.sidebar-rail-icon { font-size: 13px; }
	.sidebar-rail-label {
		font-size: 11px; letter-spacing: .08em;
		writing-mode: vertical-rl;
	}
	.sidebar-scroll { flex: 1; overflow-y: auto; padding: var(--s2) 0; }
	.sidebar-empty { padding: var(--s6) var(--s4); text-align: center; color: var(--text-3); font-size: 13px; }

	/* ── Tree nodes ───────────────────────────────────────────── */
	.tree-artist {
		margin-bottom: 1px;
		border-top: 1px solid rgba(84,84,88,.18);
	}
	.tree-artist:first-child { border-top: none; }

	.tree-album {
		padding-left: 16px;
		border-left: 2px solid rgba(84,84,88,.2);
		margin-left: 14px;
	}

	/* Artist row */
	.artist-node {
		display: flex; align-items: center;
		border-radius: 0;
	}
	.artist-node.artist-selected { background: rgba(10,132,255,.08); }

	/* Album row (same split pattern as artist) */
	.album-node {
		display: flex; align-items: center;
	}
	.album-node.album-selected { background: rgba(10,132,255,.08); }

	.caret-btn {
		flex-shrink: 0;
		width: 28px; height: 100%; min-height: 30px;
		background: none; border: none;
		color: var(--text-3); font-size: 10px;
		cursor: pointer; display: flex; align-items: center; justify-content: center;
		transition: color .1s;
	}
	.caret-btn:hover { color: var(--text); }

	.artist-label-btn, .album-label-btn {
		flex: 1; min-width: 0;
		display: flex; align-items: center; gap: 5px;
		background: none; border: none;
		text-align: left; cursor: pointer;
		padding: 5px var(--s3) 5px 0;
		transition: background .1s, color .1s;
	}
	.artist-label-btn {
		color: var(--text); font-size: 13px; font-weight: 600;
	}
	.album-label-btn {
		color: var(--text-2); font-size: 12px; font-weight: 400;
	}
	.artist-label-btn:hover, .album-label-btn:hover { color: var(--text); background: rgba(255,255,255,.04); }

	.lib-drag-handle {
		flex-shrink: 0;
		cursor: grab;
		color: var(--text-3);
		font-size: 13px;
		padding: 0 2px;
		user-select: none;
		line-height: 1;
		opacity: 0;
		transition: opacity .1s;
	}
	.album-node:hover .lib-drag-handle { opacity: 1; }
	.lib-drag-handle:active { cursor: grabbing; }

	.tree-node {
		display: flex; align-items: center; gap: 5px;
		width: 100%; padding: 5px var(--s3);
		background: none; border: none;
		color: var(--text-2); font-size: 13px;
		text-align: left; cursor: pointer;
		transition: background .1s, color .1s;
	}
	.tree-node:hover { background: rgba(255,255,255,.05); color: var(--text); }

	.tree-caret { font-size: 10px; color: var(--text-3); flex-shrink: 0; width: 10px; }
	.tree-icon  { font-size: 13px; flex-shrink: 0; }

	/* Vignette artiste dans l'arbre (photo ronde, 🎤 en repli) */
	.tree-artist-pic {
		position: relative; flex-shrink: 0;
		width: 22px; height: 22px;
		border-radius: 50%; overflow: hidden;
		background: var(--bg-3); border: 1px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.tree-artist-pic img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover; z-index: 1;
	}
	.tree-artist-pic-fallback { font-size: 11px; z-index: 0; }
	.tree-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.tree-count { font-size: 11px; color: var(--text-3); flex-shrink: 0; }

	.song-row {
		position: relative;
		display: flex; align-items: center;
		width: 100%; padding: 5px var(--s3) 5px 32px;
		background: none; border: none;
		color: var(--text-2); font-size: 12px;
		text-align: left; cursor: pointer;
		transition: background .1s, color .1s;
	}
	.song-row:hover { background: rgba(255,255,255,.05); color: var(--text); }
	.song-row.selected { background: rgba(10,132,255,.15); color: var(--blue); }
	.song-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

	/* ── Responsive (sm < 480px) ─────────────────────────────── */
	@media (max-width: 480px) {
		/* Two-panel → stacked */
		.meta-sidebar { width: 100%; height: 300px; border-right: none; border-bottom: 1px solid var(--sep); }

		/* Rail replié : barre horizontale en haut */
		.sidebar-rail {
			width: 100%; flex-direction: row; justify-content: center;
			padding: var(--s2); gap: var(--s2);
			border-right: none; border-bottom: 1px solid var(--sep);
		}
		.sidebar-rail-label { writing-mode: horizontal-tb; }

		/* Hide drag handles (D&D is desktop-only) */
		.lib-drag-handle { display: none; }
	}
</style>
