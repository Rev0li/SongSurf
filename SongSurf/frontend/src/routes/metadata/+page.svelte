<script>
	import { onMount, tick } from 'svelte';
	import { api } from '$lib/api.js';
	import { nrm } from '$lib/utils.js';
	import { addToast } from '$lib/stores.js';

	// ── Library tree ──────────────────────────────────────────────────────────────
	let tree = null;
	let filter = '';
	let expanded = new Set();

	// ── Scan (inline warnings) ────────────────────────────────────────────────────
	let scanning = false;
	let scanDone = false;
	let songIssueMap   = new Map(); // song path  → issue[]   (excludes no_artist_picture)
	let albumHasIssue  = new Map(); // album path → true       (excludes no_artist_picture)
	let artistHasIssue = new Map(); // artist path → true      (all issues including no_artist_picture)

	// ── Selection ─────────────────────────────────────────────────────────────────
	// selectedType: null | 'artist' | 'song'
	let selectedType   = null;
	let selectedArtist = null; // { path, name }
	let selectedPath   = '';   // song relative path

	// ── Song panel state ──────────────────────────────────────────────────────────
	let meta          = null;
	let metaLoading   = false;
	let metaError     = '';
	let detailsOpen   = false; // audio + cover collapsible

	// ── Editing ───────────────────────────────────────────────────────────────────
	let editValues    = {};
	let dirty         = false;
	let saving        = false;
	let saveError     = '';

	// ── Cover upload ──────────────────────────────────────────────────────────────
	let uploadingCover = false;
	let coverError     = '';
	let coverTs        = Date.now(); // bumped after upload to bust cache

	// ── Artist panel state ────────────────────────────────────────────────────────
	let artistPicTs    = Date.now();
	let uploadingArtist = false;

	// ── Lifecycle ─────────────────────────────────────────────────────────────────
	onMount(async () => {
		try { tree = await api.getLibrary(); }
		catch { tree = { artists: [], playlists: [] }; }
	});

	// ── Scan ──────────────────────────────────────────────────────────────────────
	async function runScan() {
		if (scanning) return;
		scanning = true;
		try {
			const data = await api.libraryIssues();
			const s = new Map(), al = new Map(), ar = new Map();
			for (const item of (data.issues ?? [])) {
				const songOnly = item.issues.filter((i) => i !== 'no_artist_picture');
				if (songOnly.length) s.set(item.path, songOnly);
				const parts = item.path.split('/');
				if (parts.length >= 2 && songOnly.length) al.set(parts.slice(0, -1).join('/'), true);
				if (parts.length >= 1 && item.issues.length) ar.set(parts[0], true);
			}
			songIssueMap = s; albumHasIssue = al; artistHasIssue = ar;
			scanDone = true;
		} catch { /* ignore */ }
		finally { scanning = false; }
	}

	// ── Selection helpers ─────────────────────────────────────────────────────────
	function toggleExpand(path) {
		if (expanded.has(path)) expanded.delete(path);
		else expanded.add(path);
		expanded = expanded;
	}

	function selectArtist(artist) {
		selectedType   = 'artist';
		selectedArtist = artist;
		selectedPath   = '';
		meta           = null;
		coverError     = '';
		uploadingArtist = false;
	}

	async function selectSong(path) {
		if (selectedPath === path) return;
		selectedType = 'song';
		selectedPath = path;
		selectedArtist = null;
		meta = null; metaError = ''; metaLoading = true;
		detailsOpen = false; dirty = false; saveError = ''; coverError = '';
		try {
			const data = await api.songMeta(path);
			if (data.success) {
				meta = data;
				initEdit(data);
			} else {
				metaError = data.error ?? 'Erreur inconnue';
			}
		} catch (e) { metaError = e.message ?? 'Erreur réseau'; }
		finally { metaLoading = false; }
	}

	// ── Edit helpers ──────────────────────────────────────────────────────────────
	const EDITABLE_KEYS = [
		'title', 'artist', 'album_artist', 'album', 'year',
		'track_number', 'disc_number', 'genre', 'composer', 'conductor',
		'bpm', 'key', 'language', 'isrc', 'publisher', 'copyright',
		'encoded_by', 'comment',
	];

	function initEdit(m) {
		const v = {};
		for (const k of EDITABLE_KEYS) v[k] = m.id3?.[k] ?? '';
		editValues = v;
		dirty = false;
	}

	function setField(k, v) {
		editValues = { ...editValues, [k]: v };
		dirty = true;
	}

	async function saveTags() {
		if (!dirty || saving) return;
		saving = true; saveError = '';
		try {
			await api.saveSongMeta(selectedPath, editValues);
			addToast('Tags sauvegardés.', 'info');
			dirty = false;
			// Refresh read-only display fields (audio, covers, etc.)
			const data = await api.songMeta(selectedPath);
			if (data.success) { meta = data; initEdit(data); }
		} catch (e) { saveError = e.message ?? 'Erreur'; }
		finally { saving = false; }
	}

	// ── Cover upload (song) ───────────────────────────────────────────────────────
	async function uploadSongCover(file) {
		if (!file || uploadingCover) return;
		uploadingCover = true; coverError = '';
		try {
			await api.uploadSongCover(selectedPath, file);
			coverTs = Date.now();
			// Refresh meta to update has_album_cover / has_embedded_cover
			const data = await api.songMeta(selectedPath);
			if (data.success) meta = data;
			addToast('Pochette mise à jour.', 'info');
		} catch (e) { coverError = e.message ?? 'Erreur'; }
		finally { uploadingCover = false; }
	}

	async function uploadArtistPic(file) {
		if (!file || uploadingArtist) return;
		uploadingArtist = true;
		try {
			await api.uploadArtistCover(selectedArtist.path, file);
			artistPicTs = Date.now();
			addToast('Photo artiste mise à jour.', 'info');
		} catch (e) { addToast(e.message ?? 'Erreur upload', 'error'); }
		finally { uploadingArtist = false; }
	}

	function onCoverPaste(e) {
		for (const item of (e.clipboardData?.items ?? [])) {
			if (item.kind !== 'file') continue;
			const file = item.getAsFile();
			if (!file?.type.startsWith('image/')) continue;
			e.preventDefault();
			if (selectedType === 'song') uploadSongCover(file);
			else if (selectedType === 'artist') uploadArtistPic(file);
			break;
		}
	}

	// ── Derived / filters ─────────────────────────────────────────────────────────
	$: q = nrm(filter);

	$: filteredArtists = !tree ? [] : (tree.artists ?? []).map((a) => ({
		...a,
		albums: (a.albums ?? []).map((al) => ({
			...al,
			songs: (al.songs ?? []).filter((s) => !q || nrm([a.name, al.name, s.name].join(' ')).includes(q)),
		})).filter((al) => al.songs.length > 0),
	})).filter((a) => a.albums.length > 0);

	$: filteredPlaylists = !tree ? [] : (tree.playlists ?? []).map((pl) => ({
		...pl,
		songs: (pl.songs ?? []).filter((s) => !q || nrm([pl.name, s.name].join(' ')).includes(q)),
	})).filter((pl) => pl.songs.length > 0);

	$: isEmpty = filteredArtists.length === 0 && filteredPlaylists.length === 0;

	function issueTitle(issues) {
		const L = { title:'titre', artist:'artiste', album:'album', year:'année',
		            no_album_cover:'pochette manquante', unreadable:'illisible' };
		return issues.map((i) => L[i] ?? i).join(', ');
	}

	function songDisplayName(name) { return name.replace(/\.mp3$/i, ''); }
	function fmtBytes(n) {
		if (n < 1048576) return `${(n/1024).toFixed(1)} KB`;
		return `${(n/1048576).toFixed(2)} MB`;
	}

	// ── Derived for right panel ───────────────────────────────────────────────────
	$: albumFolderPath = meta?.path ? meta.path.split('/').slice(0, -1).join('/') : '';
	$: albumCoverUrl   = albumFolderPath
		? `/api/library/folder-cover?folder_path=${encodeURIComponent(albumFolderPath)}&t=${coverTs}`
		: '';
	$: artistPicUrl    = selectedArtist
		? `/api/library/artist-picture?folder_path=${encodeURIComponent(selectedArtist.path)}&t=${artistPicTs}`
		: '';

	// ID3 layout
	const ID3_PRIMARY   = ['title','artist','album_artist','album','year','track_number','disc_number','genre'];
	const ID3_SECONDARY = ['composer','conductor','bpm','key','language','isrc','publisher','copyright','encoded_by','comment'];

	const ID3_LABELS = {
		title:'Titre', artist:'Artiste (TPE1)', album_artist:'Artiste album (TPE2)',
		conductor:'Chef d\'orchestre', album:'Album', year:'Année / Date',
		track_number:'N° piste (TRCK)', disc_number:'N° disque (TPOS)',
		genre:'Genre (TCON)', composer:'Compositeur (TCOM)',
		copyright:'Copyright', publisher:'Éditeur (TPUB)',
		bpm:'BPM', key:'Tonalité', language:'Langue',
		encoded_by:'Encodé par', isrc:'ISRC', comment:'Commentaire',
	};

	$: jellyfinMissing = !meta?.id3 ? [] : ['album_artist','track_number','genre','year'].filter((k) => {
		const v = editValues[k] ?? meta.id3[k];
		return !v || v === '' || String(v).toLowerCase().includes('unknown');
	});

	$: customTags = meta?.id3?.custom_tags ? Object.entries(meta.id3.custom_tags) : [];

	let secondaryOpen = false;
</script>

<svelte:window on:paste={onCoverPaste} />
<svelte:head><title>Métadonnées — SongSurf</title></svelte:head>

<header class="header">
	<div class="header-brand">
		<span class="header-logo">🎵</span>
		<h1 class="header-title">SongSurf</h1>
	</div>
	<nav class="header-nav">
		<a href="/" class="btn btn-ghost btn-sm">← Dashboard</a>
	</nav>
</header>

<div class="meta-layout">

	<!-- ── Left: tree ──────────────────────────────────────────── -->
	<aside class="meta-sidebar">
		<div class="sidebar-top">
			<input class="form-input" placeholder="Rechercher…" bind:value={filter} />
			<button
				class="btn btn-sm {scanning ? 'btn-ghost' : scanDone ? 'btn-orange' : 'btn-ghost'}"
				on:click={runScan} disabled={scanning}
				title="Scanner toute la bibliothèque pour les problèmes de métadonnées"
			>
				{scanning ? '⏳ Scan…' : '🔍 Scan all'}
			</button>
		</div>

		<div class="sidebar-scroll">
			{#if tree === null}
				<div class="sidebar-empty">Chargement…</div>
			{:else if isEmpty}
				<div class="sidebar-empty">{filter ? 'Aucun résultat.' : 'Bibliothèque vide.'}</div>
			{:else}
				{#each filteredArtists as artist (artist.path)}
					<div class="tree-artist">
						<!-- Artist row: caret expands, name selects artist panel -->
						<div class="tree-node artist-node {selectedType === 'artist' && selectedArtist?.path === artist.path ? 'artist-selected' : ''}">
							<button class="caret-btn" on:click|stopPropagation={() => toggleExpand(artist.path)}>
								{expanded.has(artist.path) || q ? '▾' : '▸'}
							</button>
							<button class="artist-label-btn" on:click={() => { toggleExpand(artist.path); selectArtist(artist); }}>
								<span class="tree-icon">🎤</span>
								<span class="tree-label">{artist.name}</span>
								<span class="tree-count">{artist.albums.reduce((n,al)=>n+al.songs.length,0)}</span>
								{#if scanDone && artistHasIssue.has(artist.path)}
									<span class="row-warn" title="Problèmes de métadonnées">⚠️</span>
								{/if}
							</button>
						</div>

						{#if expanded.has(artist.path) || q}
							{#each artist.albums as album (album.path)}
								<div class="tree-album">
									<button class="tree-node tree-album-node" on:click={() => toggleExpand(album.path)}>
										<span class="tree-caret">{expanded.has(album.path) || q ? '▾' : '▸'}</span>
										<span class="tree-icon">💿</span>
										<span class="tree-label">{album.name}</span>
										<span class="tree-count">{album.songs.length}</span>
										{#if scanDone && albumHasIssue.has(album.path)}
											<span class="row-warn">⚠️</span>
										{/if}
									</button>
									{#if expanded.has(album.path) || q}
										{#each album.songs as song (song.path)}
											<button
												class="song-row {selectedPath === song.path ? 'selected' : ''}"
												on:click={() => selectSong(song.path)}
											>
												<span class="song-name">{songDisplayName(song.name)}</span>
												{#if scanDone && songIssueMap.has(song.path)}
													<span class="song-warn" title={issueTitle(songIssueMap.get(song.path))}>⚠️</span>
												{/if}
											</button>
										{/each}
									{/if}
								</div>
							{/each}
						{/if}
					</div>
				{/each}

				{#each filteredPlaylists as pl (pl.path)}
					<div class="tree-artist">
						<button class="tree-node" on:click={() => toggleExpand(pl.path)}>
							<span class="tree-caret">{expanded.has(pl.path) || q ? '▾' : '▸'}</span>
							<span class="tree-icon">📁</span>
							<span class="tree-label">{pl.name}</span>
							<span class="tree-count">{pl.songs.length}</span>
							{#if scanDone && albumHasIssue.has(pl.path)}
								<span class="row-warn">⚠️</span>
							{/if}
						</button>
						{#if expanded.has(pl.path) || q}
							{#each pl.songs as song (song.path)}
								<button
									class="song-row {selectedPath === song.path ? 'selected' : ''}"
									on:click={() => selectSong(song.path)}
								>
									<span class="song-name">{songDisplayName(song.name)}</span>
									{#if scanDone && songIssueMap.has(song.path)}
										<span class="song-warn" title={issueTitle(songIssueMap.get(song.path))}>⚠️</span>
									{/if}
								</button>
							{/each}
						{/if}
					</div>
				{/each}
			{/if}
		</div>
	</aside>

	<!-- ── Right: panel ─────────────────────────────────────────── -->
	<main class="meta-main">

		<!-- ── Empty ── -->
		{#if selectedType === null}
			<div class="meta-empty">
				<span class="meta-empty-icon">🎵</span>
				<p>Sélectionne un artiste ou un fichier dans l'arborescence.</p>
			</div>

		<!-- ── Artist panel ── -->
		{:else if selectedType === 'artist'}
			<div class="meta-content">
				<div class="artist-panel">
					<div class="artist-pic-zone">
						{#key artistPicTs}
							<img
								class="artist-pic"
								src={artistPicUrl}
								alt=""
								on:error={(e) => e.currentTarget.style.display='none'}
							/>
						{/key}
						<div class="artist-pic-placeholder">🎤</div>
					</div>

					<div class="artist-info">
						<div class="artist-folder-label">Dossier artiste</div>
						<div class="artist-name">{selectedArtist.name}</div>

						<div class="cover-upload-zone">
							<p class="cover-hint">Photo artiste (artist.jpg) — glisse, colle (Ctrl+V) ou clique</p>
							<div class="cover-drop-row">
								<input
									type="file" accept="image/*" id="artist-pic-file" class="hidden-file"
									on:change={(e) => uploadArtistPic(e.currentTarget.files?.[0])}
								/>
								<label for="artist-pic-file" class="btn btn-ghost btn-sm" class:loading={uploadingArtist}>
									{uploadingArtist ? '⏳…' : '📁 Choisir'}
								</label>
							</div>
						</div>
					</div>
				</div>
			</div>

		<!-- ── Song panel ── -->
		{:else if selectedType === 'song'}
			{#if metaLoading}
				<div class="meta-empty"><span class="meta-empty-icon">⏳</span><p>Chargement…</p></div>
			{:else if metaError}
				<div class="meta-empty"><span class="meta-empty-icon">❌</span><p>{metaError}</p></div>
			{:else if meta}
				<div class="meta-content">
					<div class="meta-breadcrumb">{meta.path}</div>

					<div class="meta-sections">

						<!-- Fichier (read-only) -->
						<section class="meta-section">
							<h3 class="section-title">📄 Fichier</h3>
							<div class="meta-grid">
								<div class="meta-row"><span class="meta-key">Nom</span><span class="meta-val">{meta.file_name}</span></div>
								<div class="meta-row"><span class="meta-key">Taille</span><span class="meta-val">{fmtBytes(meta.file_size)}</span></div>
							</div>
						</section>

						<!-- Tags ID3 (editable) -->
						{#if meta.id3}
							<section class="meta-section">
								<h3 class="section-title">
									🏷️ Tags ID3
									{#if jellyfinMissing.length > 0}
										<span class="jellyfin-warn">⚠️ Jellyfin manque : {jellyfinMissing.map(k=>ID3_LABELS[k]?.split(' ')[0]??k).join(', ')}</span>
									{/if}
								</h3>

								<div class="section-subtitle">Principaux (Jellyfin / Ampifin)</div>
								<div class="meta-grid">
									{#each ID3_PRIMARY as key}
										<div class="meta-row {jellyfinMissing.includes(key) ? 'row-warn' : ''}">
											<label class="meta-key" for="f-{key}">{ID3_LABELS[key]}</label>
											<input
												id="f-{key}"
												class="meta-input {jellyfinMissing.includes(key) ? 'input-warn' : ''}"
												value={editValues[key] ?? ''}
												placeholder="—"
												on:input={(e) => setField(key, e.currentTarget.value)}
											/>
										</div>
									{/each}
								</div>

								<button class="details-toggle" on:click={() => secondaryOpen = !secondaryOpen}>
									{secondaryOpen ? '▾' : '▸'} Champs supplémentaires
								</button>
								{#if secondaryOpen}
									<div class="section-subtitle">Autres champs</div>
									<div class="meta-grid details-grid">
										{#each ID3_SECONDARY as key}
											<div class="meta-row">
												<label class="meta-key" for="f-{key}">{ID3_LABELS[key]}</label>
												<input
													id="f-{key}"
													class="meta-input {key === 'isrc' || key === 'encoded_by' ? 'mono' : ''}"
													value={editValues[key] ?? ''}
													placeholder="—"
													on:input={(e) => setField(key, e.currentTarget.value)}
												/>
											</div>
										{/each}
									</div>
								{/if}

								<!-- Save bar -->
								<div class="save-bar">
									{#if saveError}<span class="save-error">{saveError}</span>{/if}
									<button
										class="btn btn-primary btn-sm"
										on:click={saveTags}
										disabled={!dirty || saving}
									>
										{saving ? '⏳ Sauvegarde…' : dirty ? '💾 Sauvegarder' : '✓ Sauvegardé'}
									</button>
								</div>
							</section>

							<!-- Custom TXXX (read-only) -->
							{#if customTags.length > 0}
								<section class="meta-section">
									<h3 class="section-title">🔧 Tags TXXX (MusicBrainz, ReplayGain…)</h3>
									<div class="meta-grid">
										{#each customTags as [k, v]}
											<div class="meta-row">
												<span class="meta-key mono small">{k}</span>
												<span class="meta-val mono small">{v}</span>
											</div>
										{/each}
									</div>
								</section>
							{/if}

							<!-- Plus de détails: Audio + Pochette -->
							<section class="meta-section">
								<button class="section-title-btn" on:click={() => detailsOpen = !detailsOpen}>
									<span>{detailsOpen ? '▾' : '▸'} Plus de détails</span>
									<span class="details-sub">Audio · Pochette</span>
								</button>

								{#if detailsOpen}
									<!-- Audio -->
									{#if meta.audio}
										<div class="section-subtitle">🔊 Audio</div>
										<div class="meta-grid">
											<div class="meta-row"><span class="meta-key">Durée</span><span class="meta-val">{meta.audio.duration_fmt} ({meta.audio.duration_s} s)</span></div>
											<div class="meta-row"><span class="meta-key">Débit</span><span class="meta-val">{meta.audio.bitrate_kbps} kbps</span></div>
											<div class="meta-row"><span class="meta-key">Fréquence</span><span class="meta-val">{meta.audio.sample_rate} Hz</span></div>
											<div class="meta-row"><span class="meta-key">Canaux</span><span class="meta-val">{meta.audio.channels}</span></div>
											{#if meta.audio.mode}
												<div class="meta-row"><span class="meta-key">Mode</span><span class="meta-val mono">{meta.audio.mode}</span></div>
											{/if}
											{#if meta.audio.encoder_settings}
												<div class="meta-row"><span class="meta-key">Paramètres encodeur</span><span class="meta-val mono small">{meta.audio.encoder_settings}</span></div>
											{/if}
										</div>
									{/if}

									<!-- Pochette -->
									<div class="section-subtitle">🖼️ Pochette</div>
									<div class="meta-grid">
										<div class="meta-row">
											<span class="meta-key">Intégrée (APIC)</span>
											<span class="meta-val {meta.id3.has_embedded_cover ? 'tag-present' : 'tag-absent'}">
												{meta.id3.has_embedded_cover ? '✅ Oui' : '❌ Non'}
											</span>
										</div>
										<div class="meta-row {!meta.has_album_cover ? 'row-warn' : ''}">
											<span class="meta-key">Pochette album</span>
											<span class="meta-val">
												{#if meta.has_album_cover}
													<span class="tag-present">✅ {meta.cover_files.join(', ')}</span>
												{:else}
													<span class="tag-absent">⚠️ Aucune — Jellyfin ne trouvera pas la couverture</span>
												{/if}
											</span>
										</div>
										<div class="meta-row {meta.artist_picture_files?.length === 0 ? 'row-warn' : ''}">
											<span class="meta-key">Photo artiste</span>
											<span class="meta-val">
												{#if meta.artist_picture_files?.length > 0}
													<span class="tag-present">✅ {meta.artist_picture_files.join(', ')}</span>
												{:else}
													<span class="tag-absent">⚠️ Aucune — clique sur l'artiste dans la liste pour en ajouter une</span>
												{/if}
											</span>
										</div>
									</div>

									<!-- Preview -->
									{#if meta.has_album_cover && albumCoverUrl}
										<div class="cover-preview-area">
											<div class="cover-item">
												{#key coverTs}
													<img class="cover-thumb" src={albumCoverUrl} alt="Pochette" loading="lazy" />
												{/key}
												<span class="cover-label">Fichier externe</span>
											</div>
										</div>
									{/if}

									<!-- Upload zone -->
									<div class="cover-upload-zone">
										<p class="cover-hint">Remplacer la pochette — glisse, colle (Ctrl+V) ou clique</p>
										{#if coverError}<p class="save-error">{coverError}</p>{/if}
										<div class="cover-drop-row">
											<input
												type="file" accept="image/*" id="cover-file" class="hidden-file"
												on:change={(e) => uploadSongCover(e.currentTarget.files?.[0])}
											/>
											<label for="cover-file" class="btn btn-ghost btn-sm" class:loading={uploadingCover}>
												{uploadingCover ? '⏳…' : '📁 Choisir une image'}
											</label>
											{#if uploadingCover}<span class="cover-hint">Upload en cours…</span>{/if}
										</div>
									</div>
								{/if}
							</section>
						{/if}

					</div>
				</div>
			{/if}
		{/if}
	</main>
</div>

<style>
	.meta-layout {
		display: flex;
		height: calc(100vh - 56px);
		overflow: hidden;
	}

	/* ── Sidebar ──────────────────────────────────────────────── */
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
	.sidebar-scroll { flex: 1; overflow-y: auto; padding: var(--s2) 0; }
	.sidebar-empty { padding: var(--s6) var(--s4); text-align: center; color: var(--text-3); font-size: 13px; }

	/* ── Tree nodes ───────────────────────────────────────────── */
	.tree-artist { margin-bottom: 2px; }
	.tree-album  { margin-left: 12px; }

	/* Artist row: caret + label as sibling flex children */
	.artist-node {
		display: flex; align-items: center;
		border-radius: 0;
	}
	.artist-node.artist-selected { background: rgba(10,132,255,.08); }

	.caret-btn {
		flex-shrink: 0;
		width: 28px; height: 100%; min-height: 30px;
		background: none; border: none;
		color: var(--text-3); font-size: 10px;
		cursor: pointer; display: flex; align-items: center; justify-content: center;
		transition: color .1s;
	}
	.caret-btn:hover { color: var(--text); }

	.artist-label-btn {
		flex: 1; min-width: 0;
		display: flex; align-items: center; gap: 5px;
		background: none; border: none;
		color: var(--text-2); font-size: 13px; font-weight: 500;
		text-align: left; cursor: pointer;
		padding: 5px var(--s3) 5px 0;
		transition: background .1s, color .1s;
	}
	.artist-label-btn:hover { color: var(--text); background: rgba(255,255,255,.04); }

	.tree-node {
		display: flex; align-items: center; gap: 5px;
		width: 100%; padding: 5px var(--s3);
		background: none; border: none;
		color: var(--text-2); font-size: 13px;
		text-align: left; cursor: pointer;
		transition: background .1s, color .1s;
	}
	.tree-node:hover { background: rgba(255,255,255,.05); color: var(--text); }
	.tree-album-node { font-size: 12px; }

	.tree-caret { font-size: 10px; color: var(--text-3); flex-shrink: 0; width: 10px; }
	.tree-icon  { font-size: 13px; flex-shrink: 0; }
	.tree-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.tree-count { font-size: 11px; color: var(--text-3); flex-shrink: 0; }
	.row-warn   { font-size: 11px; flex-shrink: 0; }

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
	.song-warn { font-size: 10px; flex-shrink: 0; }

	/* ── Main ─────────────────────────────────────────────────── */
	.meta-main { flex: 1; overflow-y: auto; padding: var(--s6); background: var(--bg); }
	.meta-empty {
		height: 100%; display: flex; flex-direction: column;
		align-items: center; justify-content: center;
		gap: var(--s3); color: var(--text-3); text-align: center;
	}
	.meta-empty-icon { font-size: 40px; }
	.meta-empty p { font-size: 14px; max-width: 280px; line-height: 1.5; margin: 0; }

	.meta-content { max-width: 720px; }
	.meta-breadcrumb {
		font-size: 12px; color: var(--text-3);
		font-family: 'SF Mono','Menlo',monospace;
		margin-bottom: var(--s5); word-break: break-all;
	}
	.meta-sections { display: flex; flex-direction: column; gap: var(--s4); }

	/* ── Artist panel ─────────────────────────────────────────── */
	.artist-panel {
		display: flex; gap: var(--s6); align-items: flex-start;
		padding: var(--s4) 0;
	}
	.artist-pic-zone {
		position: relative; width: 140px; height: 140px; flex-shrink: 0;
		border-radius: var(--r-md); overflow: hidden;
		background: var(--bg-3); border: 1px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.artist-pic {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover;
		border-radius: var(--r-md);
	}
	.artist-pic-placeholder { font-size: 48px; color: var(--text-3); }
	.artist-info { flex: 1; }
	.artist-folder-label { font-size: 11px; font-weight: 700; color: var(--text-3); letter-spacing: .05em; text-transform: uppercase; margin-bottom: 4px; }
	.artist-name { font-size: 22px; font-weight: 700; color: var(--text); margin-bottom: var(--s4); }

	/* ── Sections ─────────────────────────────────────────────── */
	.meta-section {
		background: var(--bg-2); border: 1px solid var(--sep);
		border-radius: var(--r-md); overflow: hidden;
	}
	.section-title {
		margin: 0; padding: var(--s3) var(--s4);
		font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
		color: var(--text-2); border-bottom: 1px solid var(--sep);
		background: var(--bg-3);
		display: flex; align-items: center; gap: var(--s3);
	}
	.section-title-btn {
		display: flex; align-items: center; justify-content: space-between;
		width: 100%; padding: var(--s3) var(--s4);
		background: var(--bg-3); border: none;
		border-bottom: 1px solid var(--sep);
		font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
		color: var(--text-2); cursor: pointer; text-align: left;
		transition: background .1s;
	}
	.section-title-btn:hover { background: var(--bg-4); }
	.details-sub { font-size: 11px; font-weight: 400; color: var(--text-3); text-transform: none; letter-spacing: 0; }

	.section-subtitle {
		padding: var(--s2) var(--s4);
		font-size: 11px; font-weight: 600; color: var(--text-3);
		letter-spacing: .04em; text-transform: uppercase;
		border-bottom: 1px solid rgba(84,84,88,.2);
		background: rgba(0,0,0,.1);
	}
	.jellyfin-warn { font-size: 11px; font-weight: 500; color: var(--orange); text-transform: none; letter-spacing: 0; }

	/* ── Grid rows ────────────────────────────────────────────── */
	.meta-grid { display: flex; flex-direction: column; }
	.details-grid { background: rgba(0,0,0,.08); }

	.meta-row {
		display: flex; align-items: center;
		gap: var(--s3); padding: var(--s2) var(--s4);
		border-bottom: 1px solid rgba(84,84,88,.2);
		min-height: 36px;
	}
	.meta-row:last-child { border-bottom: none; }
	.meta-row.row-warn { background: rgba(255,159,10,.06); }

	.meta-key {
		flex-shrink: 0; width: 180px;
		font-size: 12px; font-weight: 500; color: var(--text-3);
	}
	.meta-val {
		flex: 1; font-size: 13px; color: var(--text);
		word-break: break-word; line-height: 1.5;
	}
	.tag-present { color: var(--green); }
	.tag-absent  { color: var(--text-3); }
	.mono  { font-family: 'SF Mono','Menlo',monospace; }
	.small { font-size: 11px; }

	/* ── Editable inputs ──────────────────────────────────────── */
	.meta-input {
		flex: 1; background: var(--bg-3);
		border: 1px solid rgba(255,255,255,.08);
		border-radius: var(--r-sm);
		color: var(--text); font-size: 13px;
		padding: 5px 10px; outline: none;
		font-family: inherit;
		transition: border-color .15s;
	}
	.meta-input:focus { border-color: var(--blue); background: var(--bg-4); }
	.meta-input.input-warn { border-color: rgba(255,159,10,.4); }

	/* ── Save bar ─────────────────────────────────────────────── */
	.save-bar {
		display: flex; align-items: center; justify-content: flex-end;
		gap: var(--s3); padding: var(--s3) var(--s4);
		border-top: 1px solid var(--sep);
		background: var(--bg-3);
	}
	.save-error { font-size: 12px; color: var(--red); flex: 1; }

	/* ── Details toggle ───────────────────────────────────────── */
	.details-toggle {
		display: flex; align-items: center; gap: 6px;
		width: 100%; padding: var(--s2) var(--s4);
		background: none; border: none;
		border-top: 1px solid rgba(84,84,88,.2);
		color: var(--blue); font-size: 12px; font-weight: 500;
		cursor: pointer; text-align: left;
		transition: background .1s;
	}
	.details-toggle:hover { background: rgba(10,132,255,.06); }

	/* ── Cover upload ─────────────────────────────────────────── */
	.cover-upload-zone {
		padding: var(--s4);
		border-top: 1px solid rgba(84,84,88,.2);
	}
	.cover-hint { font-size: 12px; color: var(--text-3); margin: 0 0 var(--s2); }
	.cover-drop-row { display: flex; align-items: center; gap: var(--s3); flex-wrap: wrap; }
	.hidden-file { display: none; }
	.cover-preview-area {
		padding: var(--s4);
		border-top: 1px solid rgba(84,84,88,.2);
		display: flex; gap: var(--s4);
	}
	.cover-item { display: flex; flex-direction: column; align-items: center; gap: var(--s2); }
	.cover-thumb {
		width: 100px; height: 100px; object-fit: cover;
		border-radius: var(--r-sm); border: 1px solid var(--sep); background: var(--bg-3);
	}
	.cover-label { font-size: 11px; color: var(--text-3); }

	/* ── Global btn variants ──────────────────────────────────── */
	:global(.btn-orange) { background: rgba(255,159,10,.15); color: var(--orange); border: 1px solid rgba(255,159,10,.3); }
	:global(.btn-orange:hover) { background: rgba(255,159,10,.25); }
	:global(.loading) { opacity: .6; pointer-events: none; }
</style>
