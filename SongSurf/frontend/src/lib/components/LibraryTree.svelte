<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { addToast, user } from '$lib/stores.js';
	import { matchesFilter, nrm } from '$lib/utils.js';

	let tree = null;
	let filter = '';
	let expanded = new Set();
	let dragging = false;

	onMount(refresh);

	export async function refresh() {
		if (dragging) return;
		try {
			const data = await api.getLibrary();
			tree = data;
		} catch {
			if (!tree) tree = { artists: [], playlists: [] };
		}
	}

	function toggleExpand(path) {
		if (expanded.has(path)) expanded.delete(path);
		else expanded.add(path);
		expanded = expanded;
	}

	// ── Drag and drop ─────────────────────────────────────────────────────────
	let dragSongPath  = '';
	let dragAlbumPath = '';
	let dragType      = ''; // 'song' | 'album'

	function dragStart(e, path, type) {
		dragging  = true;
		dragType  = type;
		if (type === 'song')  dragSongPath  = path;
		else                  dragAlbumPath = path;
		e.dataTransfer.effectAllowed = 'move';
		e.dataTransfer.setData('text/plain', path);
	}

	function dragEnd() {
		dragging      = false;
		dragType      = '';
		dragSongPath  = '';
		dragAlbumPath = '';
	}

	function dragOverAlbum(e) {
		if (dragType !== 'song') return;
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	function dragOverArtist(e) {
		if (dragType !== 'album') return;
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	function dragLeave(e) {
		if (e.relatedTarget && e.currentTarget.contains(e.relatedTarget)) return;
		e.currentTarget.classList.remove('drop-target');
	}

	async function dropOnAlbum(e, albumPath) {
		e.preventDefault();
		e.currentTarget.classList.remove('drop-target');
		if (dragType !== 'song') return;
		const source = e.dataTransfer.getData('text/plain') || dragSongPath;
		if (!source || !albumPath || source === albumPath) return;
		try {
			await api.moveSong(source, albumPath);
			addToast('Titre déplacé.', 'info');
			await refresh();
		} catch (err) {
			addToast(err.message || 'Déplacement impossible.', 'error');
		}
	}

	async function dropOnArtist(e, artistPath) {
		e.preventDefault();
		e.currentTarget.classList.remove('drop-target');
		if (dragType !== 'album') return;
		const source = e.dataTransfer.getData('text/plain') || dragAlbumPath;
		if (!source || !artistPath) return;
		try {
			await api.moveFolder(source, artistPath);
			addToast('Album déplacé.', 'info');
			await refresh();
		} catch (err) {
			addToast(err.message || 'Déplacement impossible.', 'error');
		}
	}

	// ── ZIP download ──────────────────────────────────────────────────────────
	let zipping = false;

	async function downloadZip() {
		const isPermanent = $user?.role === 'admin';
		if (!isPermanent) {
			const ok = confirm(
				'Télécharger la bibliothèque en ZIP ?\n\n' +
				'⚠️ Votre musique sera supprimée du serveur 60 secondes après le téléchargement.'
			);
			if (!ok) return;
		}
		zipping = true;
		try {
			const res = await api.prepareZip();
			if (!res.success) { addToast(res.error || 'Impossible de créer le ZIP.', 'error'); return; }
			addToast(`ZIP prêt : ${res.count} fichiers (${res.size_mb} MB). Téléchargement…`, 'info');
			window.location.href = (res.download_url || '/api/download-zip') + '?t=' + Date.now();
		} catch (err) {
			addToast(err.message || 'Erreur ZIP.', 'error');
		} finally {
			zipping = false;
		}
	}

	$: q = nrm(filter);

	$: filteredArtists = (tree?.artists ?? []).map((a) => ({
		...a,
		albums: (a.albums ?? []).map((al) => ({
			...al,
			songs: (al.songs ?? []).filter((s) =>
				matchesFilter([a.name, al.name, s.name].join(' '), q)
			),
		})).filter((al) => al.songs.length > 0 || matchesFilter(`${a.name} ${al.name}`, q)),
	})).filter((a) => a.albums.length > 0);

	$: filteredPlaylists = (tree?.playlists ?? []).map((pl) => ({
		...pl,
		songs: (pl.songs ?? []).filter((s) =>
			matchesFilter([pl.name, s.name].join(' '), q)
		),
	})).filter((pl) => pl.songs.length > 0 || matchesFilter(pl.name, q));

	$: isEmpty = filteredArtists.length === 0 && filteredPlaylists.length === 0;
</script>

<div class="card">
	<div class="lib-header">
		<h2 class="card-title" style="margin:0">📚 Bibliothèque</h2>
		<button class="btn btn-success btn-sm" on:click={downloadZip} disabled={zipping}>
			{zipping ? '⏳ Préparation…' : '📥 Télécharger ZIP'}
		</button>
	</div>

	<div class="lib-toolbar" style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
		<input
			class="form-input"
			placeholder="Rechercher…"
			bind:value={filter}
			style="flex:1;min-width:140px"
		/>
		<button class="btn btn-ghost btn-sm" on:click={() => { expanded = new Set(
			[...filteredArtists, ...filteredPlaylists].flatMap(a =>
				[(a.path), ...(a.albums ?? []).map(al => al.path)]
			)
		)}}>Tout ouvrir</button>
		<button class="btn btn-ghost btn-sm" on:click={() => expanded = new Set()}>Tout fermer</button>
	</div>

	{#if tree === null}
		<div class="empty-state-text">Chargement…</div>
	{:else if isEmpty}
		<div class="empty-state-text">
			{filter ? 'Aucun résultat.' : 'Aucune musique dans la bibliothèque.'}
		</div>
	{:else}
		<div class="library-tree">
			{#each filteredArtists as artist (artist.path)}
				<details
					open={q ? true : expanded.has(artist.path)}
					on:dragover={dragOverArtist}
					on:dragleave={dragLeave}
					on:drop={(e) => dropOnArtist(e, artist.path)}
				>
					<summary on:click|preventDefault={() => toggleExpand(artist.path)}>
						<div class="lib-summary-row">
							<span class="lib-summary-left">
								<span class="lib-caret">{expanded.has(artist.path) || q ? '▾' : '▸'}</span>
								<span class="lib-icon">🎤</span>
								<span class="lib-name">{artist.name}</span>
								<span class="lib-count">{artist.albums.reduce((n, al) => n + al.songs.length, 0)}</span>
							</span>
						</div>
					</summary>

					{#each artist.albums as album (album.path)}
						<details
							open={q ? true : expanded.has(album.path)}
							on:dragover={dragOverAlbum}
							on:dragleave={dragLeave}
							on:drop={(e) => dropOnAlbum(e, album.path)}
						>
							<summary on:click|preventDefault={() => toggleExpand(album.path)}>
								<div class="lib-summary-row">
									<span class="lib-summary-left">
										<span
											class="lib-drag-handle"
											draggable="true"
											title="Glisser l'album vers un autre artiste"
											on:dragstart|stopPropagation={(e) => dragStart(e, album.path, 'album')}
											on:dragend|stopPropagation={dragEnd}
										>⠿</span>
										<span class="lib-caret">{expanded.has(album.path) || q ? '▾' : '▸'}</span>
										<span class="lib-icon">💿</span>
										<span class="lib-name">{album.name}</span>
										<span class="lib-count">{album.songs.length}</span>
									</span>
								</div>
							</summary>
							{#each album.songs as song (song.path)}
								<div
									class="song-item lib-song-row"
									draggable="true"
									on:dragstart={(e) => dragStart(e, song.path, 'song')}
									on:dragend={dragEnd}
								>
									<span class="lib-song-name">{song.name}</span>
									<span class="lib-drag-hint">drag</span>
								</div>
							{/each}
						</details>
					{/each}
				</details>
			{/each}

			{#each filteredPlaylists as pl (pl.path)}
				<details
					open={q ? true : expanded.has(pl.path)}
					on:dragover={dragOverAlbum}
					on:dragleave={dragLeave}
					on:drop={(e) => dropOnAlbum(e, pl.path)}
				>
					<summary on:click|preventDefault={() => toggleExpand(pl.path)}>
						<div class="lib-summary-row">
							<span class="lib-summary-left">
								<span class="lib-caret">{expanded.has(pl.path) || q ? '▾' : '▸'}</span>
								<span class="lib-icon">📁</span>
								<span class="lib-name">{pl.name}</span>
								<span class="lib-count">{pl.songs.length}</span>
							</span>
						</div>
					</summary>
					{#each pl.songs as song (song.path)}
						<div
							class="song-item lib-song-row"
							draggable="true"
							on:dragstart={(e) => dragStart(e, song.path, 'song')}
							on:dragend={dragEnd}
						>
							<span class="lib-song-name">{song.name}</span>
							<span class="lib-drag-hint">drag</span>
						</div>
					{/each}
				</details>
			{/each}
		</div>
	{/if}
</div>

<style>
	.lib-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: var(--s4);
	}

	:global(.drop-target) {
		outline: 2px dashed var(--blue) !important;
		outline-offset: -2px;
		background: rgba(10, 132, 255, 0.08) !important;
	}

	.lib-drag-handle {
		cursor: grab;
		color: var(--text-3);
		font-size: 14px;
		padding: 0 4px;
		flex-shrink: 0;
		user-select: none;
		line-height: 1;
	}
	.lib-drag-handle:active { cursor: grabbing; }
</style>
