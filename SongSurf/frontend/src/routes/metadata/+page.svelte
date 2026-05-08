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
	let songIssueMap   = new Map();
	let albumHasIssue  = new Map();
	let artistHasIssue = new Map();

	// ── Dismissed album warnings (persisted in localStorage) ─────────────────────
	let dismissedAlbums = new Set();

	// ── Selection ─────────────────────────────────────────────────────────────────
	// selectedType: null | 'artist' | 'album' | 'song'
	let selectedType   = null;
	let selectedArtist = null; // { path, name }
	let selectedAlbum  = null; // { path, name, songs[], artist: { path, name } }
	let selectedPath   = '';   // song relative path

	// ── Song panel state ──────────────────────────────────────────────────────────
	let meta          = null;
	let metaLoading   = false;
	let metaError     = '';
	let detailsOpen   = false;

	// ── Editing ───────────────────────────────────────────────────────────────────
	let editValues       = {};
	let dirty            = false;
	let saving           = false;
	let saveError        = '';
	let lastEditedField  = null;  // tracks the most-recently-modified field
	let applyingToAlbum  = false;

	// ── Cover upload ──────────────────────────────────────────────────────────────
	let uploadingCover      = false;
	let coverError          = '';
	let coverTs             = Date.now();

	// ── Album panel state ─────────────────────────────────────────────────────────
	let albumCoverTs        = Date.now();
	let uploadingAlbumCover = false;

	// ── Artist panel state ────────────────────────────────────────────────────────
	let artistPicTs     = Date.now();
	let artistTs        = Date.now(); // cache buster for album grid covers
	let artistPicMissing = false;     // true when artist picture fails to load
	let uploadingArtist = false;

	// ── Drag and drop ─────────────────────────────────────────────────────────────
	let dndType      = ''; // 'song' | 'album'
	let dndSongPath  = '';
	let dndAlbumPath = '';

	function dndStart(e, path, type) {
		dndType = type;
		if (type === 'song')  dndSongPath  = path;
		else                  dndAlbumPath = path;
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
			if (source === selectedPath) { selectedType = null; selectedPath = ''; meta = null; }
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
			if (selectedAlbum?.path === source) { selectedType = null; selectedAlbum = null; }
			await refreshTree();
		} catch (err) { addToast(err.message || 'Déplacement impossible.', 'error'); }
	}

	async function refreshTree() {
		try {
			const data = await api.getLibrary();
			tree = data;
			// Keep selectedAlbum songs in sync if the album still exists
			if (selectedAlbum) {
				const newArtist = (data.artists ?? []).find(a => a.path === selectedAlbum.artist.path);
				const newAlbum  = newArtist?.albums?.find(a => a.path === selectedAlbum.path);
				if (newAlbum) selectedAlbum = { ...selectedAlbum, songs: newAlbum.songs };
				else { selectedType = null; selectedAlbum = null; }
			}
		} catch { /* ignore */ }
	}

	// ── Lifecycle ─────────────────────────────────────────────────────────────────
	onMount(async () => {
		try {
			const raw = localStorage.getItem('ss_dismissed_albums');
			if (raw) dismissedAlbums = new Set(JSON.parse(raw));
		} catch { /* ignore */ }
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
			// Remove dismissed albums from results
			for (const albumPath of dismissedAlbums) {
				for (const key of s.keys()) {
					if (key.startsWith(albumPath + '/')) s.delete(key);
				}
				al.delete(albumPath);
			}
			// Clean up artist flags where all albums are dismissed
			for (const artistPath of ar.keys()) {
				if (![...al.keys()].some(k => k.startsWith(artistPath + '/'))) ar.delete(artistPath);
			}
			songIssueMap = s; albumHasIssue = al; artistHasIssue = ar;
			scanDone = true;
		} catch { /* ignore */ }
		finally { scanning = false; }
	}

	function dismissAlbumIssues(albumPath) {
		for (const key of [...songIssueMap.keys()]) {
			if (key.startsWith(albumPath + '/')) songIssueMap.delete(key);
		}
		albumHasIssue.delete(albumPath);
		const artistPath = albumPath.split('/')[0];
		if (![...albumHasIssue.keys()].some(k => k.startsWith(artistPath + '/'))) {
			artistHasIssue.delete(artistPath);
		}
		songIssueMap = songIssueMap; albumHasIssue = albumHasIssue; artistHasIssue = artistHasIssue;
		dismissedAlbums = new Set([...dismissedAlbums, albumPath]);
		try { localStorage.setItem('ss_dismissed_albums', JSON.stringify([...dismissedAlbums])); } catch {}
		addToast('Avertissements ignorés pour cet album.', 'info');
	}

	function resetDismissed() {
		dismissedAlbums = new Set();
		try { localStorage.removeItem('ss_dismissed_albums'); } catch {}
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
		selectedAlbum  = null;
		selectedPath   = '';
		meta           = null;
		coverError     = '';
		uploadingArtist  = false;
		artistTs         = Date.now();
		artistPicMissing = false;
	}

	function selectAlbum(album, artist) {
		selectedType   = 'album';
		selectedAlbum  = { ...album, artist };
		selectedArtist = null;
		selectedPath   = '';
		meta           = null;
		metaError      = '';
		dirty          = false;
		detailsOpen    = false;
		albumCoverTs   = Date.now();
	}

	// keepAlbumCtx: true when navigating from album panel (back button works)
	async function selectSong(path, keepAlbumCtx = false) {
		if (selectedPath === path && selectedType === 'song') return;
		if (!keepAlbumCtx) selectedAlbum = null;
		selectedType    = 'song';
		selectedPath    = path;
		selectedArtist  = null;
		lastEditedField = null;
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

	function backToAlbum() {
		selectedType = 'album';
		selectedPath = '';
		meta = null;
		dirty = false;
	}

	function goHome() {
		selectedType   = null;
		selectedPath   = '';
		meta           = null;
		selectedAlbum  = null;
		selectedArtist = null;
		dirty          = false;
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
		lastEditedField = k;
	}

	async function saveTags() {
		if (!dirty || saving) return;
		saving = true; saveError = '';
		try {
			await api.saveSongMeta(selectedPath, editValues);
			addToast('Tags sauvegardés.', 'info');
			dirty = false;
			const data = await api.songMeta(selectedPath);
			if (data.success) { meta = data; initEdit(data); }
		} catch (e) { saveError = e.message ?? 'Erreur'; }
		finally { saving = false; }
	}

	// ── Apply field to whole album ────────────────────────────────────────────────
	// Songs to target: use selectedAlbum if we came from album panel, else derive from tree
	$: albumSongsForApply = (() => {
		if (selectedAlbum) return selectedAlbum.songs ?? [];
		if (!meta?.path || !tree) return [];
		const parts = meta.path.split('/');
		if (parts.length < 3) return [];
		const albumPath = parts.slice(0, 2).join('/');
		const artist = (tree.artists ?? []).find(a => a.path === parts[0]);
		return artist?.albums?.find(a => a.path === albumPath)?.songs ?? [];
	})();

	async function applyToAlbum() {
		if (!lastEditedField || applyingToAlbum) return;
		const songs = albumSongsForApply;
		if (songs.length === 0) return;
		applyingToAlbum = true;
		const fieldValue = editValues[lastEditedField] ?? '';
		let done = 0, errors = 0;
		for (const song of songs) {
			try {
				await api.saveSongMeta(song.path, { [lastEditedField]: fieldValue });
				if (song.path === selectedPath) dirty = false;
				done++;
			} catch { errors++; }
		}
		applyingToAlbum = false;
		const label = ID3_LABELS[lastEditedField] ?? lastEditedField;
		if (errors === 0) addToast(`« ${label} » appliqué à ${done} titre${done > 1 ? 's' : ''}.`, 'info');
		else addToast(`${done} OK, ${errors} erreur${errors > 1 ? 's' : ''}.`, 'error');
	}

	// ── Cover upload (song) ───────────────────────────────────────────────────────
	async function uploadSongCover(file) {
		if (!file || uploadingCover) return;
		uploadingCover = true; coverError = '';
		try {
			await api.uploadSongCover(selectedPath, file);
			coverTs = Date.now();
			const data = await api.songMeta(selectedPath);
			if (data.success) meta = data;
			addToast('Pochette mise à jour.', 'info');
		} catch (e) { coverError = e.message ?? 'Erreur'; }
		finally { uploadingCover = false; }
	}

	// ── Cover upload (album) ──────────────────────────────────────────────────────
	async function uploadAlbumCover(file) {
		if (!file || uploadingAlbumCover) return;
		uploadingAlbumCover = true;
		try {
			await api.uploadAlbumCover(selectedAlbum.path, file);
			albumCoverTs = Date.now();
			addToast('Pochette album mise à jour.', 'info');
		} catch (e) { addToast(e.message ?? 'Erreur upload', 'error'); }
		finally { uploadingAlbumCover = false; }
	}

	// ── Cover upload (artist) ─────────────────────────────────────────────────────
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
			if (selectedType === 'song')   uploadSongCover(file);
			else if (selectedType === 'album')  uploadAlbumCover(file);
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

	// Full (unfiltered) album list for the selected artist panel
	$: artistAlbums = selectedArtist
		? (tree?.artists ?? []).find(a => a.path === selectedArtist.path)?.albums ?? []
		: [];

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
	$: selectedAlbumCoverUrl = selectedAlbum
		? `/api/library/folder-cover?folder_path=${encodeURIComponent(selectedAlbum.path)}&t=${albumCoverTs}`
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
			<div class="sidebar-top-actions">
				<button
					class="btn btn-sm {scanning ? 'btn-ghost' : scanDone ? 'btn-orange' : 'btn-ghost'}"
					on:click={runScan} disabled={scanning}
					title="Scanner toute la bibliothèque pour les problèmes de métadonnées"
				>
					{scanning ? '⏳ Scan…' : '🔍 Scan all'}
				</button>
				{#if dismissedAlbums.size > 0}
					<button class="btn btn-sm btn-ghost dismissed-badge" on:click={resetDismissed}
						title="Réinitialiser les albums ignorés">
						{dismissedAlbums.size} ignoré{dismissedAlbums.size > 1 ? 's' : ''} ✕
					</button>
				{/if}
			</div>
		</div>

		<div class="sidebar-scroll">
			{#if tree === null}
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
								<!-- Album = drop zone for songs -->
								<div class="tree-album"
									on:dragover={dndOverAlbum}
									on:dragleave={dndLeave}
									on:drop={(e) => dndDropOnAlbum(e, album.path)}
								>
									<div class="tree-node album-node {selectedType === 'album' && selectedAlbum?.path === album.path ? 'album-selected' : ''}">
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
											{#if scanDone && albumHasIssue.has(album.path)}
												<span class="row-warn">⚠️</span>
											{/if}
										</button>
									</div>
									{#if expanded.has(album.path) || q}
										{#each album.songs as song (song.path)}
											<button
												class="song-row {selectedPath === song.path ? 'selected' : ''}"
												draggable="true"
												on:dragstart={(e) => dndStart(e, song.path, 'song')}
												on:dragend={dndEnd}
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
							{#if scanDone && albumHasIssue.has(pl.path)}
								<span class="row-warn">⚠️</span>
							{/if}
						</button>
						{#if expanded.has(pl.path) || q}
							{#each pl.songs as song (song.path)}
								<button
									class="song-row {selectedPath === song.path ? 'selected' : ''}"
									draggable="true"
									on:dragstart={(e) => dndStart(e, song.path, 'song')}
									on:dragend={dndEnd}
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

		<!-- ── Home / Artist gallery ── -->
		{#if selectedType === null}
			{#if tree && (tree.artists?.length ?? 0) > 0}
				<div class="home-gallery">
					<div class="home-gallery-grid">
						{#each (tree.artists ?? []) as artist (artist.path)}
							<button class="home-artist-card" on:click={() => { toggleExpand(artist.path); selectArtist(artist); }}>
								<div class="home-artist-cover">
									<img
										src={`/api/library/artist-picture?folder_path=${encodeURIComponent(artist.path)}&t=1`}
										alt="" loading="lazy"
										on:error={(e) => e.currentTarget.style.display='none'}
									/>
									<div class="home-artist-placeholder">🎤</div>
								</div>
								<div class="home-artist-name" title={artist.name}>{artist.name}</div>
								<div class="home-artist-meta">
									{artist.albums?.length ?? 0} album{(artist.albums?.length ?? 0) > 1 ? 's' : ''}
									· {artist.albums?.reduce((n, al) => n + al.songs.length, 0) ?? 0} titres
								</div>
							</button>
						{/each}
					</div>
				</div>
			{:else}
				<div class="meta-empty">
					<span class="meta-empty-icon">🎵</span>
					<p>Sélectionne un artiste, un album ou un fichier dans l'arborescence.</p>
				</div>
			{/if}

		<!-- ── Artist panel ── -->
		{:else if selectedType === 'artist'}
			<div class="meta-content">
				<div class="panel-nav">
					<button class="home-btn" on:click={goHome}>🏠 Accueil</button>
				</div>
				<!-- Artist header: photo + name + upload -->
				<div class="artist-panel">
					<div class="artist-pic-zone">
						{#key `${selectedArtist?.path}:${artistPicTs}`}
							<img
								class="artist-pic"
								src={artistPicUrl}
								alt=""
								on:load={() => { artistPicMissing = false; }}
								on:error={(e) => { e.currentTarget.style.display='none'; artistPicMissing = true; }}
							/>
						{/key}
						<div class="artist-pic-placeholder">🎤</div>
					</div>

					<div class="artist-info">
						<div class="artist-folder-label">Dossier artiste</div>
						<div class="artist-name">{selectedArtist.name}</div>
						{#if artistPicMissing}
							<div class="artist-pic-warn">⚠️ Photo artiste manquante — Jellyfin ne pourra pas afficher l'image de l'artiste</div>
						{/if}
						<div class="artist-album-count-label">
							{artistAlbums.length} album{artistAlbums.length > 1 ? 's' : ''} ·
							{artistAlbums.reduce((n, al) => n + al.songs.length, 0)} titres
						</div>

						<div class="cover-upload-zone" style="border-top:none;padding-left:0;padding-right:0">
							<p class="cover-hint">Photo artiste — glisse, colle (Ctrl+V) ou clique</p>
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

				<!-- Album grid -->
				{#if artistAlbums.length > 0}
					<div class="meta-sections">
						<section class="meta-section">
							<h3 class="section-title">💿 Albums — {artistAlbums.length}</h3>
							<div class="artist-album-grid">
								{#each artistAlbums as album (album.path)}
									<button class="artist-album-card" on:click={() => selectAlbum(album, selectedArtist)}>
										<div class="artist-album-cover">
											<img
												src={`/api/library/folder-cover?folder_path=${encodeURIComponent(album.path)}&t=${artistTs}`}
												alt=""
												loading="lazy"
												on:error={(e) => e.currentTarget.style.display='none'}
											/>
											<div class="artist-album-placeholder">💿</div>
										</div>
										<div class="artist-album-name" title={album.name}>{album.name}</div>
										<div class="artist-album-count">{album.songs.length} titre{album.songs.length > 1 ? 's' : ''}</div>
									</button>
								{/each}
							</div>
						</section>
					</div>
				{/if}
			</div>

		<!-- ── Album panel ── -->
		{:else if selectedType === 'album'}
			<div class="meta-content">
				<!-- Breadcrumb + Home -->
				<div class="panel-nav">
					<button class="home-btn" on:click={goHome}>🏠 Accueil</button>
					<div class="meta-breadcrumb" style="margin:0">
						<button class="breadcrumb-link" on:click={() => selectArtist(selectedAlbum.artist)}>
							🎤 {selectedAlbum.artist.name}
						</button>
						<span class="breadcrumb-sep">›</span>
						<span>💿 {selectedAlbum.name}</span>
					</div>
				</div>

				<!-- Album header: cover + info -->
				<div class="album-header">
					<div class="album-cover-zone">
						{#key `${selectedAlbum?.path}:${albumCoverTs}`}
							<img
								class="album-cover-img"
								src={selectedAlbumCoverUrl}
								alt=""
								on:error={(e) => e.currentTarget.style.display='none'}
							/>
						{/key}
						<div class="album-cover-placeholder">💿</div>
						<label
							class="album-cover-overlay"
							for="album-cover-file"
							title="Remplacer la pochette"
							class:loading={uploadingAlbumCover}
						>
							{uploadingAlbumCover ? '⏳' : '📁'}
						</label>
						<input
							type="file" accept="image/*" id="album-cover-file" class="hidden-file"
							on:change={(e) => uploadAlbumCover(e.currentTarget.files?.[0])}
						/>
					</div>

					<div class="album-info">
						<div class="album-artist-chip">{selectedAlbum.artist.name}</div>
						<div class="album-title">{selectedAlbum.name}</div>
						<div class="album-track-count">
							{selectedAlbum.songs.length} titre{selectedAlbum.songs.length > 1 ? 's' : ''}
						</div>
						{#if scanDone && albumHasIssue.has(selectedAlbum.path)}
							<div class="album-issue-row">
								<div class="album-issue-badge">⚠️ Problèmes de métadonnées détectés</div>
								<button class="btn btn-ghost btn-sm" style="font-size:11px"
									on:click={() => dismissAlbumIssues(selectedAlbum.path)}
									title="Ne plus afficher les avertissements pour cet album">
									Ignorer
								</button>
							</div>
						{/if}
						<p class="cover-hint" style="margin-top:var(--s4)">
							Pochette : glisse ou colle <kbd>Ctrl+V</kbd> pour remplacer
						</p>
					</div>
				</div>

				<!-- Tracklist -->
				<div class="meta-sections">
					<section class="meta-section">
						<h3 class="section-title">🎵 Titres</h3>
						<div class="tracklist">
							{#each selectedAlbum.songs as song, i (song.path)}
								<button
									class="track-row {selectedPath === song.path ? 'track-selected' : ''}"
									on:click={() => selectSong(song.path, true)}
								>
									<span class="track-num">{i + 1}</span>
									<span class="track-name">{songDisplayName(song.name)}</span>
									{#if scanDone && songIssueMap.has(song.path)}
										<span class="song-warn" title={issueTitle(songIssueMap.get(song.path))}>⚠️</span>
									{/if}
									<span class="track-chevron">›</span>
								</button>
							{/each}
						</div>
					</section>
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
					<!-- Back to album or breadcrumb -->
					<div class="panel-nav">
						<button class="home-btn" on:click={goHome}>🏠 Accueil</button>
						{#if selectedAlbum}
							<button class="back-btn" on:click={backToAlbum}>
								‹ {selectedAlbum.name}
							</button>
						{/if}
					</div>
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
									{#if lastEditedField && albumSongsForApply.length > 1}
										<button
											class="btn btn-ghost btn-sm"
											on:click={applyToAlbum}
											disabled={applyingToAlbum}
											title="Appliquer « {ID3_LABELS[lastEditedField] ?? lastEditedField} » à tous les titres de l'album"
										>
											{applyingToAlbum ? '⏳…' : '📋 Appliquer à l\'album'}
										</button>
									{/if}
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
	.tree-artist {
		margin-bottom: 1px;
		border-top: 1px solid rgba(84,84,88,.18);
	}
	.tree-artist:first-child { border-top: none; }

	.tree-album {
		margin-left: 0;
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

	:global(.drop-target) {
		outline: 2px dashed var(--blue) !important;
		outline-offset: -2px;
		background: rgba(10, 132, 255, 0.07) !important;
	}

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
		display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
	}
	.breadcrumb-link {
		background: none; border: none; padding: 0;
		color: var(--blue); font-size: 12px; cursor: pointer;
		font-family: 'SF Mono','Menlo',monospace;
		text-decoration: underline; text-underline-offset: 2px;
	}
	.breadcrumb-link:hover { opacity: .8; }
	.breadcrumb-sep { color: var(--text-3); }

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
	.artist-name { font-size: 22px; font-weight: 700; color: var(--text); margin-bottom: var(--s2); }
	.artist-pic-warn {
		font-size: 12px; color: var(--orange);
		background: rgba(255,159,10,.08);
		border: 1px solid rgba(255,159,10,.2);
		border-radius: var(--r-sm);
		padding: 5px 10px;
		margin-bottom: var(--s3);
		line-height: 1.4;
	}
	.artist-album-count-label { font-size: 13px; color: var(--text-3); margin-bottom: var(--s4); }

	/* ── Artist album grid ────────────────────────────────────── */
	.artist-album-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
		gap: var(--s3);
		padding: var(--s4);
	}
	.artist-album-card {
		display: flex; flex-direction: column; align-items: center;
		gap: var(--s2); padding: var(--s3);
		background: none; border: none;
		border-radius: var(--r-md); cursor: pointer;
		transition: background .15s;
		text-align: center;
	}
	.artist-album-card:hover { background: rgba(255,255,255,.06); }
	.artist-album-cover {
		position: relative;
		width: 100%; aspect-ratio: 1;
		border-radius: var(--r-sm); overflow: hidden;
		background: var(--bg-3); border: 1px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.artist-album-cover img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover;
	}
	.artist-album-placeholder { font-size: 26px; color: var(--text-3); z-index: 0; }
	.artist-album-name {
		font-size: 12px; font-weight: 500; color: var(--text);
		width: 100%;
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.artist-album-count { font-size: 11px; color: var(--text-3); }

	/* ── Album panel ──────────────────────────────────────────── */
	.album-header {
		display: flex; gap: var(--s6); align-items: flex-start;
		padding: var(--s4) 0 var(--s6);
	}
	.album-cover-zone {
		position: relative; width: 160px; height: 160px; flex-shrink: 0;
		border-radius: var(--r-md); overflow: hidden;
		background: var(--bg-3); border: 1px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
		cursor: pointer;
	}
	.album-cover-img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover;
	}
	.album-cover-placeholder { font-size: 52px; color: var(--text-3); z-index: 0; }
	.album-cover-overlay {
		position: absolute; inset: 0;
		display: flex; align-items: center; justify-content: center;
		background: rgba(0,0,0,.45);
		font-size: 20px; cursor: pointer;
		opacity: 0; transition: opacity .15s;
		z-index: 2;
	}
	.album-cover-zone:hover .album-cover-overlay { opacity: 1; }

	.album-info { flex: 1; min-width: 0; padding-top: var(--s2); }
	.album-artist-chip {
		display: inline-block;
		font-size: 11px; font-weight: 700; color: var(--text-3);
		letter-spacing: .05em; text-transform: uppercase;
		margin-bottom: var(--s2);
	}
	.album-title {
		font-size: 22px; font-weight: 700; color: var(--text);
		margin-bottom: var(--s2);
		word-break: break-word;
	}
	.album-track-count {
		font-size: 13px; color: var(--text-3);
		margin-bottom: var(--s2);
	}
	.album-issue-badge {
		display: inline-block;
		font-size: 12px; color: var(--orange);
		background: rgba(255,159,10,.1);
		border: 1px solid rgba(255,159,10,.25);
		border-radius: var(--r-sm);
		padding: 3px 10px;
		margin-bottom: var(--s2);
	}

	/* ── Tracklist ────────────────────────────────────────────── */
	.tracklist { display: flex; flex-direction: column; }
	.track-row {
		display: flex; align-items: center; gap: var(--s3);
		width: 100%; padding: 9px var(--s4);
		background: none; border: none;
		border-bottom: 1px solid rgba(84,84,88,.2);
		color: var(--text-2); font-size: 13px;
		text-align: left; cursor: pointer;
		transition: background .1s, color .1s;
	}
	.track-row:last-child { border-bottom: none; }
	.track-row:hover { background: rgba(255,255,255,.05); color: var(--text); }
	.track-row.track-selected { background: rgba(10,132,255,.12); color: var(--blue); }
	.track-num {
		flex-shrink: 0; width: 24px;
		font-size: 12px; color: var(--text-3);
		font-family: 'SF Mono','Menlo',monospace;
		text-align: right;
	}
	.track-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.track-chevron { flex-shrink: 0; font-size: 14px; color: var(--text-3); }

	/* ── Back button (song → album) ───────────────────────────── */
	.song-back-bar {
		margin-bottom: var(--s3);
	}
	.back-btn {
		background: none; border: none; padding: 0;
		color: var(--blue); font-size: 13px; font-weight: 500;
		cursor: pointer;
	}
	.back-btn:hover { text-decoration: underline; }

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
	.cover-hint kbd {
		font-size: 11px; background: var(--bg-4);
		border: 1px solid var(--sep); border-radius: 3px;
		padding: 1px 5px; font-family: inherit;
	}
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

	/* ── Panel navigation bar (Home + back) ───────────────────── */
	.panel-nav {
		display: flex; align-items: center; gap: var(--s3);
		margin-bottom: var(--s4);
	}
	.home-btn {
		background: none; border: none; padding: 0;
		color: var(--text-3); font-size: 12px; cursor: pointer;
		transition: color .1s;
	}
	.home-btn:hover { color: var(--blue); }

	/* ── Sidebar top actions row ──────────────────────────────── */
	.sidebar-top-actions { display: flex; align-items: center; gap: var(--s2); flex-wrap: wrap; }
	.dismissed-badge { font-size: 10px; color: var(--text-3); padding: 2px 7px; }

	/* ── Album issue dismiss row ──────────────────────────────── */
	.album-issue-row { display: flex; align-items: center; gap: var(--s2); flex-wrap: wrap; margin-bottom: var(--s2); }

	/* ── Home gallery (artist grid) ───────────────────────────── */
	.home-gallery {
		padding: var(--s6);
		overflow-y: auto;
	}
	.home-gallery-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: var(--s4);
	}
	.home-artist-card {
		display: flex; flex-direction: column; align-items: center;
		gap: var(--s2); padding: var(--s3);
		background: none; border: none;
		border-radius: var(--r-md); cursor: pointer;
		transition: background .15s;
		text-align: center;
	}
	.home-artist-card:hover { background: rgba(255,255,255,.06); }
	.home-artist-cover {
		position: relative;
		width: 100%; aspect-ratio: 1;
		border-radius: 50%; overflow: hidden;
		background: var(--bg-3); border: 2px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.home-artist-cover img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover;
	}
	.home-artist-placeholder { font-size: 32px; color: var(--text-3); z-index: 0; }
	.home-artist-name {
		font-size: 13px; font-weight: 600; color: var(--text);
		width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.home-artist-meta { font-size: 11px; color: var(--text-3); }
</style>
