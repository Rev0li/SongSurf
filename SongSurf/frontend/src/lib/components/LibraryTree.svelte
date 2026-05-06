<script>
	import { onMount, tick } from 'svelte';
	import { api } from '$lib/api.js';
	import { addToast, user } from '$lib/stores.js';
	import { matchesFilter, nrm } from '$lib/utils.js';

	let tree = null;        // { artists: [], playlists: [] }
	let filter = '';
	let expanded = new Set();
	let selectedFolderPath = '';
	let selectedFolderName = '';
	let dragging = false;
	let imageFile = null;
	let coverSrc = '';
	let coverLoading = false;

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

	function selectFolder(path, name) {
		selectedFolderPath = path;
		selectedFolderName = name;
		loadFolderCover(path);
	}

	async function loadFolderCover(path) {
		coverSrc = '';
		coverLoading = false;
		if (!path) return;
		coverLoading = true;
		await tick();
		await new Promise(r => requestAnimationFrame(r));
		const url = api.getFolderCoverUrl(path);
		const img = new Image();
		img.onload = () => { coverSrc = url; coverLoading = false; };
		img.onerror = () => { coverLoading = false; };
		img.src = url;
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

	// dragOver for album drop zones (accepts songs)
	function dragOverAlbum(e) {
		if (dragType !== 'song') return;
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	// dragOver for artist drop zones (accepts albums)
	function dragOverArtist(e) {
		if (dragType !== 'album') return;
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	function dragLeave(e) {
		// Ignore if pointer moved to a child of the same container
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

	// ── Rename ────────────────────────────────────────────────────────────────
	async function renameFolder(path, currentName) {
		const newName = prompt('Nouveau nom du dossier :', currentName);
		if (!newName || newName.trim() === '' || newName.trim() === currentName) return;
		try {
			const res = await api.renameFolder(path, newName.trim());
			const msg = res.merged ? 'Dossiers fusionnés.' : 'Dossier renommé.';
			if (selectedFolderPath === path) {
				selectedFolderPath = res.new_path ?? '';
				selectedFolderName = newName.trim();
			}
			addToast(msg, 'info');
			await refresh();
		} catch (err) {
			addToast(err.message || 'Renommage impossible.', 'error');
		}
	}

	// ── Delete ────────────────────────────────────────────────────────────────
	async function deleteFolder(path, name, type) {
		const label = type === 'artist' ? 'artiste' : 'album';
		if (!confirm(`Supprimer ${label} "${name}" et tous ses fichiers ?\n\nCette action est irréversible.`)) return;
		try {
			await api.deleteFolder(path);
			if (selectedFolderPath === path || selectedFolderPath.startsWith(path + '/')) {
				selectedFolderPath = '';
				selectedFolderName = '';
				coverSrc = '';
			}
			addToast(`"${name}" supprimé.`, 'info');
			await refresh();
		} catch (err) {
			addToast(err.message || 'Suppression impossible.', 'error');
		}
	}

	// ── Image upload ──────────────────────────────────────────────────────────
	async function uploadImage() {
		if (!selectedFolderPath) { addToast('Sélectionne d\'abord un dossier.', 'error'); return; }
		if (!imageFile) { addToast('Aucun fichier image sélectionné.', 'error'); return; }
		try {
			await api.uploadLibraryImage(imageFile, selectedFolderPath);
			addToast(`Image ajoutée dans ${selectedFolderName}.`, 'info');
			loadFolderCover(selectedFolderPath);
			imageFile = null;
		} catch (err) {
			addToast(err.message || 'Upload impossible.', 'error');
		}
	}

	// ── Clipboard paste ───────────────────────────────────────────────────────
	async function onPaste(e) {
		for (const item of (e.clipboardData?.items ?? [])) {
			if (item.kind !== 'file') continue;
			const file = item.getAsFile();
			if (!file || !file.type.startsWith('image/')) continue;
			e.preventDefault();
			imageFile = file;
			await uploadImage();
			break;
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

<svelte:window on:paste={onPaste} />

<div class="card">
	<div class="lib-header">
		<h2 class="card-title" style="margin:0">📚 Bibliothèque</h2>
		<button class="btn btn-success btn-sm" on:click={downloadZip} disabled={zipping}>
			{zipping ? '⏳ Préparation…' : '📥 Télécharger ZIP'}
		</button>
	</div>

	<!-- Toolbar -->
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

	<!-- Cover + upload (shown when folder selected) -->
	{#if selectedFolderPath}
		<div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:12px;flex-wrap:wrap">
			<div class="cover-preview-box" style="width:80px;height:80px;flex-shrink:0">
				{#if coverLoading}
					<div class="cover-spinner"></div>
				{:else if coverSrc}
					<img class="metadata-thumb" src={coverSrc} alt="Pochette" />
				{:else}
					<div class="cover-placeholder" style="font-size:11px">Pas de pochette</div>
				{/if}
			</div>
			<div style="flex:1;min-width:160px">
				<div class="progress-subtext" style="margin-bottom:6px">
					Dossier : <strong>{selectedFolderName}</strong>
				</div>
				<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
					<input
						type="file"
						accept="image/*"
						style="display:none"
						id="lib-image-file"
						on:change={(e) => { imageFile = e.currentTarget.files?.[0] ?? null; }}
					/>
					<label for="lib-image-file" class="btn btn-ghost btn-sm" style="cursor:pointer">
						📁 Choisir image
					</label>
					<button class="btn btn-primary btn-sm" on:click={uploadImage} disabled={!imageFile}>
						⬆️ Uploader
					</button>
					{#if imageFile}
						<span class="progress-subtext">{imageFile.name}</span>
					{/if}
				</div>
			</div>
		</div>
	{/if}

	<!-- Tree -->
	{#if tree === null}
		<div class="empty-state-text">Chargement…</div>
	{:else if isEmpty}
		<div class="empty-state-text">
			{filter ? 'Aucun résultat.' : 'Aucune musique dans la bibliothèque.'}
		</div>
	{:else}
		<div class="library-tree">
			<!-- Artists -->
			{#each filteredArtists as artist (artist.path)}
				<details
					open={q ? true : expanded.has(artist.path)}
					on:toggle={(e) => { if (!q) { if (e.currentTarget.open) expanded.add(artist.path); else expanded.delete(artist.path); expanded = expanded; }}}
					class:selected-folder={selectedFolderPath === artist.path}
					on:dragover={dragOverArtist}
					on:dragleave={dragLeave}
					on:drop={(e) => dropOnArtist(e, artist.path)}
				>
					<summary on:click|preventDefault={() => { toggleExpand(artist.path); selectFolder(artist.path, artist.name); }}>
						<div class="lib-summary-row">
							<span class="lib-summary-left">
								<span class="lib-caret">{expanded.has(artist.path) || q ? '▾' : '▸'}</span>
								<span class="lib-icon">🎤</span>
								<span class="lib-name">{artist.name}</span>
								<span class="lib-count">{artist.albums.reduce((n, al) => n + al.songs.length, 0)}</span>
							</span>
							<span class="folder-actions">
								<button
									class="lib-action-btn"
									title="Renommer"
									on:click|stopPropagation={() => renameFolder(artist.path, artist.name)}
								>✏️</button>
								<button
									class="lib-action-btn lib-action-btn--danger"
									title="Supprimer"
									on:click|stopPropagation={() => deleteFolder(artist.path, artist.name, 'artist')}
								>🗑️</button>
							</span>
						</div>
					</summary>

					{#each artist.albums as album (album.path)}
						<details
							open={q ? true : expanded.has(album.path)}
							on:toggle={(e) => { if (!q) { if (e.currentTarget.open) expanded.add(album.path); else expanded.delete(album.path); expanded = expanded; }}}
							class:selected-folder={selectedFolderPath === album.path}
							on:dragover={dragOverAlbum}
							on:dragleave={dragLeave}
							on:drop={(e) => dropOnAlbum(e, album.path)}
						>
							<summary on:click|preventDefault={() => { toggleExpand(album.path); selectFolder(album.path, album.name); }}>
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
									<span class="folder-actions">
										<button
											class="lib-action-btn"
											title="Renommer"
											on:click|stopPropagation={() => renameFolder(album.path, album.name)}
										>✏️</button>
										<button
											class="lib-action-btn lib-action-btn--danger"
											title="Supprimer"
											on:click|stopPropagation={() => deleteFolder(album.path, album.name, 'album')}
										>🗑️</button>
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

			<!-- Playlists -->
			{#each filteredPlaylists as pl (pl.path)}
				<details
					open={q ? true : expanded.has(pl.path)}
					on:toggle={(e) => { if (!q) { if (e.currentTarget.open) expanded.add(pl.path); else expanded.delete(pl.path); expanded = expanded; }}}
					class:selected-folder={selectedFolderPath === pl.path}
					on:dragover={dragOverAlbum}
					on:dragleave={dragLeave}
					on:drop={(e) => dropOnAlbum(e, pl.path)}
				>
					<summary on:click|preventDefault={() => { toggleExpand(pl.path); selectFolder(pl.path, pl.name); }}>
						<div class="lib-summary-row">
							<span class="lib-summary-left">
								<span class="lib-caret">{expanded.has(pl.path) || q ? '▾' : '▸'}</span>
								<span class="lib-icon">📁</span>
								<span class="lib-name">{pl.name}</span>
								<span class="lib-count">{pl.songs.length}</span>
							</span>
							<span class="folder-actions">
								<button
									class="lib-action-btn"
									title="Renommer"
									on:click|stopPropagation={() => renameFolder(pl.path, pl.name)}
								>✏️</button>
								<button
									class="lib-action-btn lib-action-btn--danger"
									title="Supprimer"
									on:click|stopPropagation={() => deleteFolder(pl.path, pl.name, 'album')}
								>🗑️</button>
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

	/* Drop zone highlight */
	:global(.drop-target) {
		outline: 2px dashed var(--blue) !important;
		outline-offset: -2px;
		background: rgba(10, 132, 255, 0.08) !important;
	}

	/* Album drag handle */
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

	/* Folder action buttons (rename + delete) */
	.folder-actions {
		display: flex;
		gap: 2px;
		flex-shrink: 0;
	}
	.lib-action-btn {
		background: none;
		border: none;
		cursor: pointer;
		font-size: 13px;
		padding: 2px 4px;
		border-radius: var(--r-sm);
		opacity: 0;
		transition: opacity .15s, background .15s;
		line-height: 1;
	}
	.lib-summary-row:hover .lib-action-btn { opacity: 1; }
	.lib-action-btn:hover { background: rgba(255,255,255,.1); }
	.lib-action-btn--danger:hover { background: rgba(255, 59, 48, .2); }
</style>
