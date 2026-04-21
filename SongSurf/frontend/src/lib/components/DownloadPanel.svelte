<script>
	import { workerBusy } from '$lib/stores.js';
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import {
		asText, primaryArtist, inferPlaylistArtist,
		resolveCoverCandidates, bustUrl,
	} from '$lib/utils.js';

	export let onDownloadQueued = () => {};

	// ── State ──────────────────────────────────────────────────────────────────
	let url = '';
	let extract = null;
	let panelActive = false;

	// single song fields
	let title = '';
	let artist = '';
	let album = '';

	// playlist fields
	let playlistArtist = '';
	let playlistAlbum = '';
	let playlistYear = '';

	// options
	let playlistMode = false;
	let mp4Mode = false;

	// cover
	let coverCandidates = [];
	let coverIdx = 0;
	let coverSrc = '';
	let coverVisible = false;

	// prefetch
	let prefetchToken = '';
	let prefetchTimer = null;

	// ── Cover handling ────────────────────────────────────────────────────────
	function setCoverCandidates(candidates) {
		coverCandidates = candidates ?? [];
		coverIdx = 0;
		coverSrc = '';
		coverVisible = false;
		tryNextCover();
	}

	function tryNextCover() {
		if (coverIdx >= coverCandidates.length) {
			coverSrc = '';
			coverVisible = false;
			return;
		}
		coverSrc = bustUrl(coverCandidates[coverIdx]);
		coverIdx++;
	}

	function handleCoverLoad() {
		coverVisible = true;
	}

	function handleCoverError() {
		tryNextCover();
	}

	function stopPrefetchPolling() {
		if (prefetchTimer) { clearInterval(prefetchTimer); prefetchTimer = null; }
	}

	function startPrefetchPolling(token, fallbackCandidates) {
		stopPrefetchPolling();
		if (!token) return;
		let tries = 0;
		const maxTries = 25;

		function probe() {
			tries++;
			const probeUrl = api.getPrefetchCoverUrl(token) + `&probe=${Date.now()}`;
			const img = new Image();
			img.onload = () => {
				stopPrefetchPolling();
				setCoverCandidates([api.getPrefetchCoverUrl(token), ...fallbackCandidates]);
			};
			img.onerror = () => { if (tries >= maxTries) stopPrefetchPolling(); };
			img.src = probeUrl;
		}

		probe();
		prefetchTimer = setInterval(probe, 1200);
	}

	async function cancelPrefetch() {
		if (!prefetchToken) return;
		const token = prefetchToken;
		prefetchToken = '';
		stopPrefetchPolling();
		try { await api.cancelPrefetch(token); } catch { /* stale token, ignore */ }
	}

	// ── Extract ───────────────────────────────────────────────────────────────
	let extracting = false;

	async function onExtract() {
		const raw = url.trim();
		if (!raw) { addToast('Colle un lien YouTube Music.', 'error'); return; }

		extracting = true;
		await cancelPrefetch();

		try {
			const data = await api.extract(raw);
			if (!data.success) { addToast(data.error || 'Extraction impossible.', 'error'); return; }

			extract = data;
			url = '';

			if (data.is_playlist) {
				playlistArtist = inferPlaylistArtist(data);
				playlistAlbum = asText(data.title, 'Unknown Album');
				playlistYear = asText(data.year, '');
				const candidates = resolveCoverCandidates(data, raw);
				setCoverCandidates(candidates);
				prefetchToken = asText(data.prefetch_token);
				if (prefetchToken) startPrefetchPolling(prefetchToken, candidates);
			} else {
				title = asText(data.title, 'Unknown Title');
				artist = primaryArtist(data.artist);
				album = asText(data.album, 'Unknown Album');
				setCoverCandidates(resolveCoverCandidates(data, raw));
			}

			panelActive = true;
			addToast('Métadonnées chargées. Ajuste puis télécharge.', 'info');
		} catch (err) {
			addToast(err.message || 'Erreur extraction.', 'error');
		} finally {
			extracting = false;
		}
	}

	// ── Download ──────────────────────────────────────────────────────────────
	let downloading = false;

	async function onDownload() {
		if (!extract) { addToast('Commence par analyser un lien.', 'error'); return; }

		downloading = true;
		try {
			let res;
			if (extract.is_playlist) {
				res = await api.downloadPlaylist({
					playlist_mode: playlistMode,
					mp4_mode: mp4Mode,
					playlist_metadata: {
						title: asText(playlistAlbum, 'Unknown Album'),
						artist: asText(playlistArtist, 'Unknown Artist'),
						year: asText(playlistYear),
						songs: extract.songs ?? [],
					},
				});
			} else {
				res = await api.download({
					url: extract.url ?? '',
					playlist_mode: playlistMode,
					mp4_mode: mp4Mode,
					title: asText(title, 'Unknown Title'),
					artist: asText(artist, 'Unknown Artist'),
					album: asText(album, 'Unknown Album'),
					year: '',
				});
			}

			if (!res.success) { addToast(res.error || 'Échec du téléchargement.', 'error'); return; }

			stopPrefetchPolling();
			prefetchToken = '';
			addToast('Ajouté à la file de téléchargement.', 'info');
			reset();
			onDownloadQueued();
		} catch (err) {
			addToast(err.message || 'Erreur téléchargement.', 'error');
		} finally {
			downloading = false;
		}
	}

	// ── Reset ─────────────────────────────────────────────────────────────────
	async function reset() {
		await cancelPrefetch();
		extract = null;
		panelActive = false;
		title = artist = album = playlistArtist = playlistAlbum = playlistYear = '';
		playlistMode = mp4Mode = false;
		coverSrc = '';
		coverVisible = false;
	}

	// ── Keyboard shortcut: Enter on URL input ────────────────────────────────
	function onKeydown(e) {
		if (e.key === 'Enter') onExtract();
	}

	$: dlDisabled = !panelActive || $workerBusy || downloading;
	$: dlLabel = downloading ? '⏳ Envoi…' : ($workerBusy ? '⏳ En attente de Worker' : '⬇️ Télécharger');
</script>

<!-- ── URL Bar ───────────────────────────────────────────────────────────── -->
<section class="top-analyzer-wrap">
	<div class="card top-analyzer-card">
		<h2 class="card-title">🔗 Coller un lien YouTube Music</h2>
		<div class="url-group">
			<input
				type="text"
				class="form-input"
				bind:value={url}
				placeholder="https://music.youtube.com/watch?v=..."
				autocomplete="off"
				on:keydown={onKeydown}
				disabled={extracting}
			/>
			<button class="btn btn-primary" on:click={onExtract} disabled={extracting}>
				{extracting ? '⏳ Analyse…' : '🔍 Analyser'}
			</button>
		</div>
	</div>
</section>

<!-- ── Metadata Panel ────────────────────────────────────────────────────── -->
<div class="card metadata-panel">
	<h2 class="card-title">🎛️ Panneau d'analyse</h2>
	<div class="metadata-preview" class:analysis-disabled={!panelActive}>
		<div class="metadata-layout">
			<div class="metadata-main">

				<!-- Single song fields -->
				{#if !extract?.is_playlist}
					<div class="metadata-info">
						<div class="form-group">
							<label class="form-label">Titre</label>
							<input class="form-input" bind:value={title} placeholder="Titre" disabled={!panelActive} />
						</div>
						<div class="form-group compact-row">
							{#if !playlistMode}
								<div>
									<label class="form-label">Artiste</label>
									<input class="form-input" bind:value={artist} placeholder="Artiste" disabled={!panelActive} />
								</div>
							{/if}
							<div style={playlistMode ? 'grid-column: 1 / -1' : ''}>
								<label class="form-label">Album</label>
								<input class="form-input" bind:value={album} placeholder="Album" disabled={!panelActive} />
							</div>
						</div>
					</div>
				{/if}

				<!-- Playlist fields -->
				{#if extract?.is_playlist}
					<div class="metadata-info">
						<div style="font-weight:600;font-size:14px;margin-bottom:10px;">
							{extract.title ?? ''}
						</div>
						<div class="form-group compact-row">
							{#if !playlistMode}
								<div>
									<label class="form-label">Artiste</label>
									<input class="form-input" bind:value={playlistArtist} placeholder="Artiste" disabled={!panelActive} />
								</div>
							{/if}
							<div style={playlistMode ? 'grid-column: 1 / -1' : ''}>
								<label class="form-label">Album / Playlist</label>
								<input class="form-input" bind:value={playlistAlbum} placeholder="Nom de l'album" disabled={!panelActive} />
							</div>
						</div>
						<div class="form-group" style="max-width:130px">
							<label class="form-label">Année</label>
							<input class="form-input" bind:value={playlistYear} placeholder="2024" disabled={!panelActive} />
						</div>
						{#if (extract?.songs?.length ?? 0) > 0}
							<div class="form-group">
								<label class="form-label">Titres ({extract.songs.length})</label>
								<div class="song-list-preview">
									{#each extract.songs as song, i}
										<div class="song-row">{i + 1}. {song.title ?? ''}</div>
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{/if}

				<div class="metadata-actions">
					<button class="btn btn-brand btn-block" on:click={onDownload} disabled={dlDisabled}>
						{dlLabel}
					</button>
					<button class="btn btn-danger btn-sm" on:click={reset} disabled={!panelActive}>
						✕ Annuler
					</button>
				</div>
			</div>

			<!-- Options + Cover -->
			<aside class="metadata-options-column">
				<div class="cover-preview-box">
					<div class="progress-subtext">Pochette</div>
					{#if coverSrc}
						<img
							class="metadata-thumb"
							src={coverSrc}
							alt="Pochette"
							style={coverVisible ? '' : 'display:none'}
							on:load={handleCoverLoad}
							on:error={handleCoverError}
						/>
					{/if}
					{#if !coverVisible}
						<div class="cover-placeholder">Aperçu pochette</div>
					{/if}
				</div>

				<div class="option-card">
					<div class="toggle-row option-toggle-row">
						<div class="toggle-description">
							<strong>🎵 Mode Playlist</strong>
							<small>Actif : pas de tri artiste.</small>
							<small>Inactif : tri Artist/Album/Titre.</small>
						</div>
						<label class="toggle-switch">
							<input type="checkbox" bind:checked={playlistMode} disabled={!panelActive} />
							<span class="toggle-slider"></span>
						</label>
					</div>
					<div class="toggle-row option-toggle-row">
						<div class="toggle-description">
							<strong>🎬 Mode MP4 (max 1080p)</strong>
						</div>
						<label class="toggle-switch">
							<input type="checkbox" bind:checked={mp4Mode} disabled={!panelActive} />
							<span class="toggle-slider"></span>
						</label>
					</div>
				</div>
			</aside>
		</div>
	</div>
</div>
