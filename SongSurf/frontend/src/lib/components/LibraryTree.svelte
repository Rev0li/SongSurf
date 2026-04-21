<script>
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { matchesFilter, nrm } from '$lib/utils.js';

	let tree = null;        // { artists: [], playlists: [] }
	let filter = '';
	let expanded = new Set();
	let selectedFolderPath = '';
	let selectedFolderName = '';
	let dragging = false;
	let imageFile = null;
	let coverSrc = '';
	let coverVisible = false;

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
		expanded = expanded; // trigger reactivity
	}

	function selectFolder(path, name) {
		selectedFolderPath = path;
		selectedFolderName = name;
		loadFolderCover(path);
	}

	function loadFolderCover(path) {
		if (!path) { coverSrc = ''; coverVisible = false; return; }
		coverVisible = false;
		coverSrc = api.getFolderCoverUrl(path);
	}

	// ── Drag and drop ─────────────────────────────────────────────────────────
	let dragSongPath = '';

	function dragStart(e, songPath) {
		dragging = true;
		dragSongPath = songPath;
		e.dataTransfer.setData('text/plain', songPath);
	}

	function dragEnd() {
		dragging = false;
	}

	async function drop(e, targetFolder) {
		e.preventDefault();
		e.currentTarget.classList.remove('drop-target');
		const source = e.dataTransfer.getData('text/plain') || dragSongPath;
		if (!source || !targetFolder) return;
		try {
			await api.moveSong(source, targetFolder);
			addToast('Titre déplacé.', 'info');
			await refresh();
		} catch (err) {
			addToast(err.message || 'Déplacement impossible.', 'error');
		}
	}

	function dragOver(e) {
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	function dragLeave(e) {
		e.currentTarget.classList.remove('drop-target');
	}

	// ── Rename ────────────────────────────────────────────────────────────────
	async function renameFolder(path, currentName) {
		const newName = prompt('Nouveau nom du dossier :', currentName);
		if (!newName || newName.trim() === '' || newName.trim() === currentName) return;
		try {
			await api.renameFolder(path, newName.trim());
			addToast('Dossier renommé.', 'info');
			await refresh();
		} catch (err) {
			addToast(err.message || 'Renommage impossible.', 'error');
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
	<h2 class="card-title">📚 Bibliothèque</h2>

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
				{#if coverSrc}
					<img
						src={coverSrc}
						alt="Pochette"
						style={coverVisible ? 'width:100%;height:100%;object-fit:cover;border-radius:4px' : 'display:none'}
						on:load={() => coverVisible = true}
						on:error={() => coverVisible = false}
					/>
				{/if}
				{#if !coverVisible}
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
				>
					<summary on:click|preventDefault={() => { toggleExpand(artist.path); selectFolder(artist.path, artist.name); }}>
						<div class="lib-summary-row">
							<span class="lib-summary-left">
								<span class="lib-caret">{expanded.has(artist.path) || q ? '▾' : '▸'}</span>
								<span class="lib-icon">🎤</span>
								<span class="lib-name">{artist.name}</span>
								<span class="lib-count">{artist.albums.reduce((n, al) => n + al.songs.length, 0)}</span>
							</span>
							<button
								class="folder-actions"
								on:click|stopPropagation={() => renameFolder(artist.path, artist.name)}
							>✏️</button>
						</div>
					</summary>

					{#each artist.albums as album (album.path)}
						<details
							open={q ? true : expanded.has(album.path)}
							on:toggle={(e) => { if (!q) { if (e.currentTarget.open) expanded.add(album.path); else expanded.delete(album.path); expanded = expanded; }}}
							class:selected-folder={selectedFolderPath === album.path}
							on:dragover={dragOver}
							on:dragleave={dragLeave}
							on:drop={(e) => drop(e, album.path)}
						>
							<summary on:click|preventDefault={() => { toggleExpand(album.path); selectFolder(album.path, album.name); }}>
								<div class="lib-summary-row">
									<span class="lib-summary-left">
										<span class="lib-caret">{expanded.has(album.path) || q ? '▾' : '▸'}</span>
										<span class="lib-icon">💿</span>
										<span class="lib-name">{album.name}</span>
										<span class="lib-count">{album.songs.length}</span>
									</span>
									<button
										class="folder-actions"
										on:click|stopPropagation={() => renameFolder(album.path, album.name)}
									>✏️</button>
								</div>
							</summary>
							{#each album.songs as song (song.path)}
								<div
									class="song-item lib-song-row"
									draggable="true"
									on:dragstart={(e) => dragStart(e, song.path)}
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
					on:dragover={dragOver}
					on:dragleave={dragLeave}
					on:drop={(e) => drop(e, pl.path)}
				>
					<summary on:click|preventDefault={() => { toggleExpand(pl.path); selectFolder(pl.path, pl.name); }}>
						<div class="lib-summary-row">
							<span class="lib-summary-left">
								<span class="lib-caret">{expanded.has(pl.path) || q ? '▾' : '▸'}</span>
								<span class="lib-icon">📁</span>
								<span class="lib-name">{pl.name}</span>
								<span class="lib-count">{pl.songs.length}</span>
							</span>
							<button
								class="folder-actions"
								on:click|stopPropagation={() => renameFolder(pl.path, pl.name)}
							>✏️</button>
						</div>
					</summary>
					{#each pl.songs as song (song.path)}
						<div
							class="song-item lib-song-row"
							draggable="true"
							on:dragstart={(e) => dragStart(e, song.path)}
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
