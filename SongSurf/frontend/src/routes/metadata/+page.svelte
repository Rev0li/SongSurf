<script>
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { nrm } from '$lib/utils.js';

	let tree = null;
	let filter = '';
	let expanded = new Set();

	let showIssues = false;
	let issues = null;
	let issuesLoading = false;

	let selectedPath = '';
	let meta = null;
	let metaLoading = false;
	let metaError = '';

	// Collapsible state for detail sections
	let audioDetailsOpen = false;
	let coverDetailsOpen = false;

	onMount(async () => {
		try {
			tree = await api.getLibrary();
		} catch {
			tree = { artists: [], playlists: [] };
		}
	});

	async function loadIssues() {
		if (issues) return;
		issuesLoading = true;
		try {
			const data = await api.libraryIssues();
			issues = data.issues ?? [];
		} catch {
			issues = [];
		} finally {
			issuesLoading = false;
		}
	}

	function toggleIssues() {
		showIssues = !showIssues;
		if (showIssues) loadIssues();
	}

	async function selectSong(path) {
		if (selectedPath === path) return;
		selectedPath = path;
		meta = null;
		metaError = '';
		metaLoading = true;
		audioDetailsOpen = false;
		coverDetailsOpen = false;
		try {
			const data = await api.songMeta(path);
			if (data.success) {
				meta = data;
			} else {
				metaError = data.error ?? 'Erreur inconnue';
			}
		} catch (e) {
			metaError = e.message ?? 'Erreur réseau';
		} finally {
			metaLoading = false;
		}
	}

	function toggleExpand(path) {
		if (expanded.has(path)) expanded.delete(path);
		else expanded.add(path);
		expanded = expanded;
	}

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

	$: filteredIssues = !issues ? [] : issues.filter((i) => !q || nrm(i.path).includes(q));
	$: isEmpty = filteredArtists.length === 0 && filteredPlaylists.length === 0;

	// Issue badge colours
	const ISSUE_COLORS = {
		title:             '#ff453a',
		artist:            '#ff9f0a',
		album:             '#ff9f0a',
		year:              '#bf5af2',
		unreadable:        '#ff453a',
		no_album_cover:    '#0a84ff',
		no_artist_picture: '#636366',
	};
	const ISSUE_LABELS = {
		title:             'titre',
		artist:            'artiste',
		album:             'album',
		year:              'année',
		unreadable:        'illisible',
		no_album_cover:    'pochette',
		no_artist_picture: 'photo artiste',
	};

	function fmtBytes(n) {
		if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
		return `${(n / 1048576).toFixed(2)} MB`;
	}

	function songDisplayName(name) {
		return name.replace(/\.mp3$/i, '');
	}

	// Album folder path derived from song path (Artist/Album/Song.mp3 → Artist/Album)
	$: albumFolderPath = meta?.path ? meta.path.split('/').slice(0, -1).join('/') : '';
	$: albumCoverUrl   = albumFolderPath ? api.getFolderCoverUrl(albumFolderPath) : '';

	// ID3 fields split: primary (Jellyfin-critical) vs secondary
	const ID3_PRIMARY = ['title', 'artist', 'album_artist', 'album', 'year', 'track_number', 'disc_number', 'genre'];
	const ID3_SECONDARY = ['composer', 'conductor', 'bpm', 'key', 'language', 'isrc', 'publisher', 'copyright', 'encoded_by', 'comment', 'lyrics_text', 'length_ms'];

	const ID3_LABELS = {
		title:            'Titre',
		artist:           'Artiste (TPE1)',
		album_artist:     'Artiste album (TPE2)',
		conductor:        'Chef d\'orchestre',
		album:            'Album',
		year:             'Année / Date',
		track_number:     'N° piste (TRCK)',
		disc_number:      'N° disque (TPOS)',
		genre:            'Genre (TCON)',
		composer:         'Compositeur (TCOM)',
		copyright:        'Copyright',
		publisher:        'Éditeur (TPUB)',
		bpm:              'BPM',
		key:              'Tonalité',
		language:         'Langue',
		encoded_by:       'Encodé par',
		isrc:             'ISRC (identifiant)',
		length_ms:        'Durée (ms)',
		comment:          'Commentaire',
		lyrics_text:      'Paroles',
	};

	// Jellyfin-critical fields that are missing
	$: jellyfinMissing = !meta?.id3 ? [] : ['album_artist', 'track_number', 'genre', 'year'].filter((k) => {
		const v = meta.id3[k];
		return !v || v === '' || v.toLowerCase().includes('unknown');
	});

	$: id3Primary = !meta?.id3 ? [] : ID3_PRIMARY
		.filter((k) => meta.id3[k] !== undefined)
		.map((k) => ({ key: k, label: ID3_LABELS[k] ?? k, value: String(meta.id3[k]) }));

	$: id3Secondary = !meta?.id3 ? [] : ID3_SECONDARY
		.filter((k) => meta.id3[k] !== undefined)
		.map((k) => ({ key: k, label: ID3_LABELS[k] ?? k, value: String(meta.id3[k]) }));

	$: id3Extra = !meta?.id3 ? [] : Object.keys(meta.id3)
		.filter((k) => ![...ID3_PRIMARY, ...ID3_SECONDARY].includes(k) && k !== 'has_embedded_cover' && k !== 'custom_tags')
		.map((k) => ({ key: k, label: k, value: String(meta.id3[k]) }));

	$: customTags = meta?.id3?.custom_tags ? Object.entries(meta.id3.custom_tags) : [];
</script>

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
	<!-- ── Left panel: song browser ─────────────────────────── -->
	<aside class="meta-sidebar">
		<div class="sidebar-top">
			<input class="form-input" placeholder="Rechercher…" bind:value={filter} />
			<button
				class="btn btn-sm {showIssues ? 'btn-orange' : 'btn-ghost'}"
				on:click={toggleIssues}
				title="Afficher les fichiers avec des problèmes de métadonnées"
			>
				⚠️ Problèmes
			</button>
		</div>

		<div class="sidebar-scroll">
			{#if showIssues}
				{#if issuesLoading}
					<div class="sidebar-empty">Scan en cours…</div>
				{:else if filteredIssues.length === 0}
					<div class="sidebar-empty">{issues?.length === 0 ? '✅ Aucun problème détecté.' : 'Aucun résultat.'}</div>
				{:else}
					<div class="issues-count">{filteredIssues.length} fichier{filteredIssues.length > 1 ? 's' : ''} avec des problèmes</div>
					{#each filteredIssues as item (item.path)}
						<button
							class="song-row song-row--flat {selectedPath === item.path ? 'selected' : ''}"
							on:click={() => selectSong(item.path)}
						>
							<span class="song-name">{songDisplayName(item.path.split('/').pop())}</span>
							<span class="issue-badges">
								{#each item.issues as issue}
									<span class="issue-badge" style="background:{ISSUE_COLORS[issue] ?? '#718096'}18;color:{ISSUE_COLORS[issue] ?? '#718096'}">
										{ISSUE_LABELS[issue] ?? issue}
									</span>
								{/each}
							</span>
						</button>
					{/each}
				{/if}
			{:else}
				{#if tree === null}
					<div class="sidebar-empty">Chargement…</div>
				{:else if isEmpty}
					<div class="sidebar-empty">{filter ? 'Aucun résultat.' : 'Bibliothèque vide.'}</div>
				{:else}
					{#each filteredArtists as artist (artist.path)}
						<div class="tree-artist">
							<button class="tree-node" on:click={() => toggleExpand(artist.path)}>
								<span class="tree-caret">{expanded.has(artist.path) || q ? '▾' : '▸'}</span>
								<span class="tree-icon">🎤</span>
								<span class="tree-label">{artist.name}</span>
								<span class="tree-count">{artist.albums.reduce((n, al) => n + al.songs.length, 0)}</span>
							</button>
							{#if expanded.has(artist.path) || q}
								{#each artist.albums as album (album.path)}
									<div class="tree-album">
										<button class="tree-node tree-album-node" on:click={() => toggleExpand(album.path)}>
											<span class="tree-caret">{expanded.has(album.path) || q ? '▾' : '▸'}</span>
											<span class="tree-icon">💿</span>
											<span class="tree-label">{album.name}</span>
											<span class="tree-count">{album.songs.length}</span>
										</button>
										{#if expanded.has(album.path) || q}
											{#each album.songs as song (song.path)}
												<button
													class="song-row {selectedPath === song.path ? 'selected' : ''}"
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
						<div class="tree-artist">
							<button class="tree-node" on:click={() => toggleExpand(pl.path)}>
								<span class="tree-caret">{expanded.has(pl.path) || q ? '▾' : '▸'}</span>
								<span class="tree-icon">📁</span>
								<span class="tree-label">{pl.name}</span>
								<span class="tree-count">{pl.songs.length}</span>
							</button>
							{#if expanded.has(pl.path) || q}
								{#each pl.songs as song (song.path)}
									<button
										class="song-row {selectedPath === song.path ? 'selected' : ''}"
										on:click={() => selectSong(song.path)}
									>
										<span class="song-name">{songDisplayName(song.name)}</span>
									</button>
								{/each}
							{/if}
						</div>
					{/each}
				{/if}
			{/if}
		</div>
	</aside>

	<!-- ── Right panel: metadata display ────────────────────── -->
	<main class="meta-main">
		{#if !selectedPath}
			<div class="meta-empty">
				<span class="meta-empty-icon">🎵</span>
				<p>Sélectionne un fichier dans l'arborescence pour voir ses métadonnées.</p>
			</div>
		{:else if metaLoading}
			<div class="meta-empty">
				<span class="meta-empty-icon">⏳</span>
				<p>Lecture des métadonnées…</p>
			</div>
		{:else if metaError}
			<div class="meta-empty">
				<span class="meta-empty-icon">❌</span>
				<p>{metaError}</p>
			</div>
		{:else if meta}
			<div class="meta-content">
				<div class="meta-breadcrumb">{meta.path}</div>

				<div class="meta-sections">

					<!-- ── Fichier ── -->
					<section class="meta-section">
						<h3 class="section-title">📄 Fichier</h3>
						<div class="meta-grid">
							<div class="meta-row"><span class="meta-key">Nom</span><span class="meta-val">{meta.file_name}</span></div>
							<div class="meta-row"><span class="meta-key">Taille</span><span class="meta-val">{fmtBytes(meta.file_size)} ({meta.file_size_mb} MB)</span></div>
						</div>
					</section>

					<!-- ── Audio ── -->
					{#if meta.audio}
						<section class="meta-section">
							<h3 class="section-title">🔊 Audio</h3>
							<div class="meta-grid">
								<div class="meta-row"><span class="meta-key">Durée</span><span class="meta-val">{meta.audio.duration_fmt} ({meta.audio.duration_s} s)</span></div>
								<div class="meta-row"><span class="meta-key">Débit</span><span class="meta-val">{meta.audio.bitrate_kbps} kbps</span></div>
								<div class="meta-row"><span class="meta-key">Fréquence</span><span class="meta-val">{meta.audio.sample_rate} Hz</span></div>
								<div class="meta-row"><span class="meta-key">Canaux</span><span class="meta-val">{meta.audio.channels}</span></div>
							</div>
							{#if meta.audio.mode || meta.audio.encoder_settings}
								<button class="details-toggle" on:click={() => audioDetailsOpen = !audioDetailsOpen}>
									{audioDetailsOpen ? '▾' : '▸'} Plus de détails
								</button>
								{#if audioDetailsOpen}
									<div class="meta-grid details-grid">
										{#if meta.audio.mode}
											<div class="meta-row"><span class="meta-key">Mode</span><span class="meta-val mono">{meta.audio.mode}</span></div>
										{/if}
										{#if meta.audio.encoder_settings}
											<div class="meta-row"><span class="meta-key">Paramètres encodeur</span><span class="meta-val mono small">{meta.audio.encoder_settings}</span></div>
										{/if}
									</div>
								{/if}
							{/if}
						</section>
					{/if}

					<!-- ── Tags ID3 — champs Jellyfin ── -->
					{#if meta.id3}
						<section class="meta-section">
							<h3 class="section-title">
								🏷️ Tags ID3
								{#if jellyfinMissing.length > 0}
									<span class="jellyfin-warn" title="Champs manquants importants pour Jellyfin">⚠️ Jellyfin : {jellyfinMissing.map(k => ID3_LABELS[k]?.split(' ')[0] ?? k).join(', ')}</span>
								{/if}
							</h3>

							<!-- Primary fields -->
							<div class="section-subtitle">Champs principaux (Jellyfin / Ampifin)</div>
							<div class="meta-grid">
								{#each id3Primary as entry (entry.key)}
									<div class="meta-row {jellyfinMissing.includes(entry.key) ? 'row-warn' : ''}">
										<span class="meta-key">{entry.label}</span>
										<span class="meta-val">{entry.value}</span>
									</div>
								{/each}
								{#each ['album_artist', 'track_number', 'genre', 'year'].filter(k => !meta.id3[k]) as missingKey}
									<div class="meta-row row-missing">
										<span class="meta-key">{ID3_LABELS[missingKey]}</span>
										<span class="meta-val tag-absent">— manquant</span>
									</div>
								{/each}
							</div>

							<!-- Secondary fields collapsible -->
							{#if id3Secondary.length > 0 || id3Extra.length > 0}
								<button class="details-toggle" on:click={() => audioDetailsOpen = !audioDetailsOpen}>
									{audioDetailsOpen ? '▾' : '▸'} Champs supplémentaires
								</button>
								{#if audioDetailsOpen}
									<div class="section-subtitle">Autres champs</div>
									<div class="meta-grid details-grid">
										{#each id3Secondary as entry (entry.key)}
											<div class="meta-row">
												<span class="meta-key">{entry.label}</span>
												<span class="meta-val {entry.key === 'isrc' || entry.key === 'encoded_by' ? 'mono' : ''}">{entry.value}</span>
											</div>
										{/each}
										{#each id3Extra as entry (entry.key)}
											<div class="meta-row">
												<span class="meta-key mono">{entry.label}</span>
												<span class="meta-val">{entry.value}</span>
											</div>
										{/each}
									</div>
								{/if}
							{/if}
						</section>

						<!-- ── Pochette ── -->
						<section class="meta-section">
							<h3 class="section-title">🖼️ Pochette</h3>
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
										{:else if meta.artist_picture_files !== undefined}
											<span class="tag-absent">⚠️ Aucune — ajoute artist.jpg dans le dossier artiste</span>
										{:else}
											<span class="tag-absent">—</span>
										{/if}
									</span>
								</div>
							</div>

							<!-- Cover preview collapsible -->
							{#if meta.has_album_cover || meta.id3.has_embedded_cover}
								<button class="details-toggle" on:click={() => coverDetailsOpen = !coverDetailsOpen}>
									{coverDetailsOpen ? '▾' : '▸'} Aperçu pochette
								</button>
								{#if coverDetailsOpen}
									<div class="cover-preview-area">
										{#if meta.has_album_cover && albumCoverUrl}
											<div class="cover-item">
												<img
													class="cover-thumb"
													src={albumCoverUrl}
													alt="Pochette album"
													loading="lazy"
												/>
												<span class="cover-label">Fichier externe</span>
											</div>
										{/if}
										{#if !meta.has_album_cover && !meta.id3.has_embedded_cover}
											<p class="cover-missing-note">Aucune pochette disponible pour l'aperçu.</p>
										{/if}
									</div>
								{/if}
							{/if}
						</section>

						<!-- ── Tags personnalisés (TXXX) ── -->
						{#if customTags.length > 0}
							<section class="meta-section">
								<h3 class="section-title">🔧 Tags personnalisés (TXXX)</h3>
								<div class="section-subtitle">MusicBrainz IDs, ReplayGain, etc.</div>
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
					{/if}

				</div>
			</div>
		{/if}
	</main>
</div>

<style>
	.meta-layout {
		display: flex;
		height: calc(100vh - 56px);
		overflow: hidden;
	}

	/* ── Sidebar ─────────────────────────────────────────────────── */
	.meta-sidebar {
		width: 300px;
		flex-shrink: 0;
		border-right: 1px solid var(--sep);
		display: flex;
		flex-direction: column;
		background: var(--bg-2);
	}
	.sidebar-top {
		padding: var(--s3) var(--s3) var(--s2);
		display: flex;
		flex-direction: column;
		gap: var(--s2);
		border-bottom: 1px solid var(--sep);
	}
	.sidebar-scroll { flex: 1; overflow-y: auto; padding: var(--s2) 0; }
	.sidebar-empty {
		padding: var(--s6) var(--s4);
		text-align: center;
		color: var(--text-3);
		font-size: 13px;
	}
	.issues-count {
		padding: var(--s2) var(--s3);
		font-size: 11px;
		font-weight: 600;
		color: var(--text-3);
		letter-spacing: .04em;
		text-transform: uppercase;
	}

	/* ── Tree ────────────────────────────────────────────────────── */
	.tree-artist { margin-bottom: 2px; }
	.tree-album  { margin-left: 14px; }

	.tree-node {
		display: flex;
		align-items: center;
		gap: 5px;
		width: 100%;
		padding: 5px var(--s3);
		background: none;
		border: none;
		color: var(--text-2);
		font-size: 13px;
		text-align: left;
		cursor: pointer;
		transition: background .1s, color .1s;
	}
	.tree-node:hover { background: rgba(255,255,255,.05); color: var(--text); }
	.tree-album-node { font-size: 12px; }

	.tree-caret { font-size: 10px; color: var(--text-3); flex-shrink: 0; width: 10px; }
	.tree-icon  { font-size: 13px; flex-shrink: 0; }
	.tree-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
	.tree-count { font-size: 11px; color: var(--text-3); flex-shrink: 0; }

	/* ── Song rows ───────────────────────────────────────────────── */
	.song-row {
		display: flex;
		flex-direction: column;
		gap: 2px;
		width: 100%;
		padding: 6px var(--s3) 6px 32px;
		background: none;
		border: none;
		color: var(--text-2);
		font-size: 12px;
		text-align: left;
		cursor: pointer;
		transition: background .1s, color .1s;
	}
	.song-row:hover { background: rgba(255,255,255,.05); color: var(--text); }
	.song-row.selected { background: rgba(10, 132, 255, .15); color: var(--blue); }
	.song-row--flat { padding-left: var(--s3); }
	.song-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

	.issue-badges { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 2px; }
	.issue-badge {
		font-size: 10px; font-weight: 600;
		padding: 1px 5px; border-radius: 4px;
		letter-spacing: .03em;
	}

	/* ── Main ────────────────────────────────────────────────────── */
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
		font-family: 'SF Mono', 'Menlo', monospace;
		margin-bottom: var(--s5); word-break: break-all;
	}
	.meta-sections { display: flex; flex-direction: column; gap: var(--s4); }

	/* ── Sections ────────────────────────────────────────────────── */
	.meta-section {
		background: var(--bg-2);
		border: 1px solid var(--sep);
		border-radius: var(--r-md);
		overflow: hidden;
	}
	.section-title {
		margin: 0;
		padding: var(--s3) var(--s4);
		font-size: 12px; font-weight: 700;
		letter-spacing: .05em; text-transform: uppercase;
		color: var(--text-2);
		border-bottom: 1px solid var(--sep);
		background: var(--bg-3);
		display: flex; align-items: center; gap: var(--s3);
	}
	.section-subtitle {
		padding: var(--s2) var(--s4);
		font-size: 11px; font-weight: 600;
		color: var(--text-3);
		letter-spacing: .04em; text-transform: uppercase;
		border-bottom: 1px solid rgba(84,84,88,.2);
	}
	.jellyfin-warn {
		font-size: 11px; font-weight: 500;
		color: var(--orange);
		text-transform: none; letter-spacing: 0;
	}

	/* ── Meta grid rows ──────────────────────────────────────────── */
	.meta-grid { display: flex; flex-direction: column; }
	.meta-row {
		display: flex; align-items: flex-start;
		gap: var(--s4); padding: var(--s2) var(--s4);
		border-bottom: 1px solid rgba(84,84,88,.25);
		min-height: 34px;
	}
	.meta-row:last-child { border-bottom: none; }
	.meta-row.row-warn { background: rgba(255,159,10,.06); }
	.meta-row.row-missing { background: rgba(255,69,58,.04); }

	.meta-key {
		flex-shrink: 0; width: 190px;
		font-size: 12px; font-weight: 500;
		color: var(--text-3); padding-top: 2px;
	}
	.meta-val {
		flex: 1; font-size: 13px;
		color: var(--text); word-break: break-word; line-height: 1.5;
	}
	.mono  { font-family: 'SF Mono', 'Menlo', monospace; }
	.small { font-size: 11px; }
	.tag-present { color: var(--green); }
	.tag-absent  { color: var(--text-3); }

	/* ── Details toggle ──────────────────────────────────────────── */
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
	.details-grid { background: rgba(0,0,0,.15); }

	/* ── Cover preview ───────────────────────────────────────────── */
	.cover-preview-area {
		padding: var(--s4);
		display: flex; gap: var(--s4); flex-wrap: wrap;
		border-top: 1px solid rgba(84,84,88,.2);
	}
	.cover-item { display: flex; flex-direction: column; align-items: center; gap: var(--s2); }
	.cover-thumb {
		width: 120px; height: 120px; object-fit: cover;
		border-radius: var(--r-sm);
		border: 1px solid var(--sep);
		background: var(--bg-3);
	}
	.cover-label { font-size: 11px; color: var(--text-3); }
	.cover-missing-note { font-size: 12px; color: var(--text-3); margin: 0; padding: var(--s2); }

	/* ── Global variants ─────────────────────────────────────────── */
	:global(.btn-orange) {
		background: rgba(255, 159, 10, .15);
		color: var(--orange);
		border: 1px solid rgba(255, 159, 10, .3);
	}
	:global(.btn-orange:hover) { background: rgba(255, 159, 10, .25); }
</style>
