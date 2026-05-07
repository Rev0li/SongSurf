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

	const ISSUE_COLORS = { title: '#ff453a', artist: '#ff9f0a', album: '#ff9f0a', year: '#bf5af2', unreadable: '#ff453a' };

	function fmtBytes(n) {
		if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
		return `${(n / 1048576).toFixed(2)} MB`;
	}

	function songDisplayName(name) {
		return name.replace(/\.mp3$/i, '');
	}

	const ID3_LABELS = {
		title: 'Titre', artist: 'Artiste', album_artist: 'Artiste album',
		conductor: 'Chef d\'orchestre', album: 'Album', year: 'Année',
		track_number: 'N° piste', disc_number: 'N° disque', genre: 'Genre',
		composer: 'Compositeur', copyright: 'Copyright', publisher: 'Éditeur',
		bpm: 'BPM', key: 'Tonalité', language: 'Langue',
		encoded_by: 'Encodé par', encoder_settings: 'Paramètres encodeur',
		isrc: 'ISRC', length_ms: 'Durée (ms)', comment: 'Commentaire',
		lyrics_text: 'Paroles',
	};

	const ID3_ORDER = [
		'title', 'artist', 'album_artist', 'album', 'year', 'track_number', 'disc_number',
		'genre', 'composer', 'conductor', 'bpm', 'key', 'language', 'isrc',
		'publisher', 'copyright', 'encoded_by', 'encoder_settings', 'length_ms',
		'comment', 'lyrics_text',
	];

	$: id3Entries = !meta?.id3 ? [] : ID3_ORDER
		.filter((k) => meta.id3[k] !== undefined)
		.map((k) => ({ key: k, label: ID3_LABELS[k] ?? k, value: String(meta.id3[k]) }));

	$: extraId3 = !meta?.id3 ? [] : Object.keys(meta.id3)
		.filter((k) => !ID3_ORDER.includes(k) && k !== 'has_embedded_cover' && k !== 'custom_tags')
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
			<button class="btn btn-sm {showIssues ? 'btn-orange' : 'btn-ghost'}" on:click={toggleIssues} title="Afficher les fichiers avec des problèmes de métadonnées">
				⚠️ Problèmes
			</button>
		</div>

		<div class="sidebar-scroll">
			{#if showIssues}
				<!-- Issues list -->
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
									<span class="issue-badge" style="background:{ISSUE_COLORS[issue] ?? '#718096'}20;color:{ISSUE_COLORS[issue] ?? '#718096'}">
										{issue}
									</span>
								{/each}
							</span>
						</button>
					{/each}
				{/if}
			{:else}
				<!-- Normal tree -->
				{#if tree === null}
					<div class="sidebar-empty">Chargement…</div>
				{:else if isEmpty}
					<div class="sidebar-empty">{filter ? 'Aucun résultat.' : 'Bibliothèque vide.'}</div>
				{:else}
					{#each filteredArtists as artist (artist.path)}
						<div class="tree-artist">
							<button
								class="tree-node tree-artist-row"
								on:click={() => toggleExpand(artist.path)}
							>
								<span class="tree-caret">{expanded.has(artist.path) || q ? '▾' : '▸'}</span>
								<span class="tree-icon">🎤</span>
								<span class="tree-label">{artist.name}</span>
								<span class="tree-count">{artist.albums.reduce((n, al) => n + al.songs.length, 0)}</span>
							</button>

							{#if expanded.has(artist.path) || q}
								{#each artist.albums as album (album.path)}
									<div class="tree-album">
										<button
											class="tree-node tree-album-row"
											on:click={() => toggleExpand(album.path)}
										>
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
							<button
								class="tree-node tree-artist-row"
								on:click={() => toggleExpand(pl.path)}
							>
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
				<!-- File path breadcrumb -->
				<div class="meta-breadcrumb">{meta.path}</div>

				<!-- Sections -->
				<div class="meta-sections">

					<!-- File info -->
					<section class="meta-section">
						<h3 class="section-title">📄 Fichier</h3>
						<div class="meta-grid">
							<div class="meta-row"><span class="meta-key">Nom</span><span class="meta-val">{meta.file_name}</span></div>
							<div class="meta-row"><span class="meta-key">Taille</span><span class="meta-val">{fmtBytes(meta.file_size)} ({meta.file_size_mb} MB)</span></div>
						</div>
					</section>

					<!-- Audio info -->
					{#if meta.audio}
						<section class="meta-section">
							<h3 class="section-title">🔊 Audio</h3>
							<div class="meta-grid">
								<div class="meta-row"><span class="meta-key">Durée</span><span class="meta-val">{meta.audio.duration_fmt} ({meta.audio.duration_s}s)</span></div>
								<div class="meta-row"><span class="meta-key">Débit</span><span class="meta-val">{meta.audio.bitrate_kbps} kbps</span></div>
								<div class="meta-row"><span class="meta-key">Fréquence</span><span class="meta-val">{meta.audio.sample_rate} Hz</span></div>
								<div class="meta-row"><span class="meta-key">Canaux</span><span class="meta-val">{meta.audio.channels}</span></div>
								{#if meta.audio.mode !== ''}
									<div class="meta-row"><span class="meta-key">Mode</span><span class="meta-val mono">{meta.audio.mode}</span></div>
								{/if}
							</div>
						</section>
					{/if}

					<!-- ID3 tags -->
					{#if meta.id3}
						<section class="meta-section">
							<h3 class="section-title">🏷️ Tags ID3</h3>
							<div class="meta-grid">
								{#each id3Entries as entry (entry.key)}
									<div class="meta-row">
										<span class="meta-key">{entry.label}</span>
										<span class="meta-val {entry.key === 'isrc' || entry.key === 'encoded_by' || entry.key === 'encoder_settings' ? 'mono' : ''}">{entry.value}</span>
									</div>
								{/each}
								{#each extraId3 as entry (entry.key)}
									<div class="meta-row">
										<span class="meta-key mono">{entry.label}</span>
										<span class="meta-val">{entry.value}</span>
									</div>
								{/each}
							</div>
						</section>

						<!-- Cover art -->
						<section class="meta-section">
							<h3 class="section-title">🖼️ Pochette</h3>
							<div class="meta-grid">
								<div class="meta-row">
									<span class="meta-key">Intégrée (APIC)</span>
									<span class="meta-val {meta.id3.has_embedded_cover ? 'tag-present' : 'tag-absent'}">
										{meta.id3.has_embedded_cover ? '✅ Oui' : '❌ Non'}
									</span>
								</div>
								<div class="meta-row">
									<span class="meta-key">Fichiers externes</span>
									<span class="meta-val">
										{#if meta.cover_files?.length > 0}
											{meta.cover_files.join(', ')}
										{:else}
											<span class="tag-absent">Aucun</span>
										{/if}
									</span>
								</div>
							</div>
						</section>

						<!-- Custom TXXX tags -->
						{#if customTags.length > 0}
							<section class="meta-section">
								<h3 class="section-title">🔧 Tags personnalisés (TXXX)</h3>
								<div class="meta-grid">
									{#each customTags as [k, v]}
										<div class="meta-row">
											<span class="meta-key mono">{k}</span>
											<span class="meta-val">{v}</span>
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

	.sidebar-scroll {
		flex: 1;
		overflow-y: auto;
		padding: var(--s2) 0;
	}

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
		border-radius: 0;
		transition: background .1s, color .1s;
	}
	.tree-node:hover { background: rgba(255,255,255,.05); color: var(--text); }

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
	.song-row.selected {
		background: rgba(10, 132, 255, .15);
		color: var(--blue);
	}
	.song-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

	.song-row--flat { padding-left: var(--s3); }

	.issue-badges {
		display: flex;
		flex-wrap: wrap;
		gap: 3px;
		margin-top: 2px;
	}
	.issue-badge {
		font-size: 10px;
		font-weight: 600;
		padding: 1px 5px;
		border-radius: 4px;
		letter-spacing: .03em;
	}

	/* ── Main ────────────────────────────────────────────────────── */
	.meta-main {
		flex: 1;
		overflow-y: auto;
		padding: var(--s6);
		background: var(--bg);
	}

	.meta-empty {
		height: 100%;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--s3);
		color: var(--text-3);
		text-align: center;
	}
	.meta-empty-icon { font-size: 40px; }
	.meta-empty p { font-size: 14px; max-width: 280px; line-height: 1.5; margin: 0; }

	.meta-content { max-width: 700px; }

	.meta-breadcrumb {
		font-size: 12px;
		color: var(--text-3);
		font-family: 'SF Mono', 'Menlo', monospace;
		margin-bottom: var(--s5);
		word-break: break-all;
	}

	.meta-sections { display: flex; flex-direction: column; gap: var(--s5); }

	.meta-section {
		background: var(--bg-2);
		border: 1px solid var(--sep);
		border-radius: var(--r-md);
		overflow: hidden;
	}

	.section-title {
		margin: 0;
		padding: var(--s3) var(--s4);
		font-size: 12px;
		font-weight: 700;
		letter-spacing: .05em;
		text-transform: uppercase;
		color: var(--text-2);
		border-bottom: 1px solid var(--sep);
		background: var(--bg-3);
	}

	.meta-grid { display: flex; flex-direction: column; }

	.meta-row {
		display: flex;
		align-items: flex-start;
		gap: var(--s4);
		padding: var(--s2) var(--s4);
		border-bottom: 1px solid rgba(84, 84, 88, .3);
		min-height: 36px;
	}
	.meta-row:last-child { border-bottom: none; }

	.meta-key {
		flex-shrink: 0;
		width: 160px;
		font-size: 12px;
		font-weight: 500;
		color: var(--text-3);
		padding-top: 2px;
	}

	.meta-val {
		flex: 1;
		font-size: 13px;
		color: var(--text);
		word-break: break-word;
		line-height: 1.5;
	}

	.mono { font-family: 'SF Mono', 'Menlo', monospace; font-size: 12px; }
	.tag-present { color: var(--green); }
	.tag-absent  { color: var(--text-3); }

	/* Orange button variant */
	:global(.btn-orange) {
		background: rgba(255, 159, 10, .15);
		color: var(--orange);
		border: 1px solid rgba(255, 159, 10, .3);
	}
	:global(.btn-orange:hover) {
		background: rgba(255, 159, 10, .25);
	}
</style>
