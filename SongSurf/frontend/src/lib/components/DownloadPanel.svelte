<script>
	import { tick } from 'svelte';
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import {
		asText, inferPlaylistArtist,
		resolveCoverCandidates, bustUrl,
	} from '$lib/utils.js';

	export let onAddToQueue = () => {};

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
	let coverLoading = false;

	// prefetch
	let prefetchToken = '';
	let prefetchTimer = null;

	// ── Cover handling ────────────────────────────────────────────────────────
	function setCoverCandidates(candidates) {
		coverCandidates = candidates ?? [];
		coverIdx = 0;
		coverSrc = '';
		coverLoading = false;
		tryNextCover();
	}

	async function tryNextCover() {
		if (coverIdx >= coverCandidates.length) {
			// All candidates exhausted — keep spinner if prefetch is still in flight
			if (!prefetchTimer) {
				coverSrc = '';
				coverLoading = false;
			}
			return;
		}
		if (!coverLoading) {
			// First probe in this series: ensure spinner renders before starting
			coverLoading = true;
			await tick();
			await new Promise(r => requestAnimationFrame(r));
		}
		const url = bustUrl(coverCandidates[coverIdx]);
		coverIdx++;
		const img = new Image();
		img.onload = () => { coverSrc = url; coverLoading = false; };
		img.onerror = tryNextCover;
		img.src = url;
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
				const newUrl = api.getPrefetchCoverUrl(token);
				if (coverSrc) {
					// Cover already visible — update silently, no spinner flash
					coverSrc = newUrl;
				} else {
					// Spinner still running (all CDN candidates failed) — set cover directly
					coverLoading = false;
					coverSrc = newUrl;
				}
			};
			img.onerror = () => {
				if (tries >= maxTries) {
					stopPrefetchPolling();
					// Prefetch gave up — fall back to CDN candidates as last resort
					if (!coverSrc) tryNextCover();
				}
			};
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

			extract = { ...data, url: raw };
			url = '';

			if (data.is_playlist) {
				playlistArtist = inferPlaylistArtist(data);
				playlistAlbum = asText(data.title, 'Unknown Album');
				playlistYear = asText(data.year, '');
				const candidates = resolveCoverCandidates(data, raw);
				prefetchToken = asText(data.prefetch_token);
				panelActive = true;
				await tick();
				if (prefetchToken) {
					// Skip grey CDN probes — spinner until prefetch delivers the real cover
					coverCandidates = candidates; // kept as fallback if prefetch times out
					coverIdx = 0;
					coverSrc = '';
					coverLoading = true;
					await new Promise(r => requestAnimationFrame(r));
					startPrefetchPolling(prefetchToken, candidates);
				} else {
					setCoverCandidates(candidates);
				}
			} else {
				title = asText(data.title, 'Unknown Title');
				artist = asText(data.artist, 'Unknown Artist');
				album = asText(data.album, 'Unknown Album');
				const candidates = resolveCoverCandidates(data, raw);
				panelActive = true;
				await tick();
				setCoverCandidates(candidates);
			}

			addToast('Métadonnées chargées. Ajuste puis télécharge.', 'info');
		} catch (err) {
			addToast(err.message || 'Erreur extraction.', 'error');
		} finally {
			extracting = false;
		}
	}

	// ── Add to queue ─────────────────────────────────────────────────────────
	function addToQueue() {
		if (!extract) return;

		const item = extract.is_playlist ? {
			isPlaylist: true,
			label: asText(playlistAlbum, extract.title ?? 'Playlist'),
			playlistMode,
			mp4Mode,
			playlistMetadata: {
				title:  asText(playlistAlbum, 'Unknown Album'),
				artist: asText(playlistArtist, 'Unknown Artist'),
				year:   asText(playlistYear),
				songs:  extract.songs ?? [],
			},
		} : {
			isPlaylist: false,
			label: `${asText(artist, '?')} — ${asText(title, '?')}`,
			url:          extract.url ?? '',
			playlistMode,
			mp4Mode,
			title:        asText(title,  'Unknown Title'),
			artist:       asText(artist, 'Unknown Artist'),
			album:        asText(album,  'Unknown Album'),
			year:         '',
		};

		stopPrefetchPolling();
		prefetchToken = '';
		onAddToQueue(item);
		reset();
	}

	// ── Reset ─────────────────────────────────────────────────────────────────
	async function reset() {
		await cancelPrefetch();
		extract = null;
		panelActive = false;
		title = artist = album = playlistArtist = playlistAlbum = playlistYear = '';
		playlistMode = mp4Mode = false;
		coverSrc = '';
		coverLoading = false;
	}

	// ── Keyboard shortcut: Enter on URL input ────────────────────────────────
	function onKeydown(e) {
		if (e.key === 'Enter') onExtract();
	}

</script>

<!-- ── URL Bar (sticky) ──────────────────────────────────────────────────── -->
<section class="top-analyzer-wrap">
	<div class="card top-analyzer-card">
		<div class="url-group">
			<input
				type="text"
				class="form-input"
				bind:value={url}
				placeholder="Coller un lien YouTube Music…"
				autocomplete="off"
				on:keydown={onKeydown}
				disabled={extracting}
			/>
			<button class="btn btn-primary" on:click={onExtract} disabled={extracting}>
				{extracting ? 'Analyse…' : 'Analyser'}
			</button>
		</div>
	</div>
</section>

<!-- ── Metadata Panel (only when a URL has been analysed) ───────────────── -->
{#if panelActive}
<div class="page-body" style="padding-bottom:0">
	<div class="card metadata-panel">
		<div class="metadata-layout">
			<!-- Cover -->
			<aside class="metadata-options-column">
				<div class="cover-preview-box">
					{#if coverLoading}
						<div class="cover-spinner"></div>
					{:else if coverSrc}
						<img class="metadata-thumb" src={coverSrc} alt="Pochette" />
					{:else}
						<div class="cover-placeholder">Pochette</div>
					{/if}
				</div>

				<div class="option-card">
					<div class="toggle-row option-toggle-row">
						<div class="toggle-description">
							<strong>Mode Playlist</strong>
							<small>Pas de tri artiste.</small>
						</div>
						<label class="toggle-switch">
							<input type="checkbox" bind:checked={playlistMode} />
							<span class="toggle-slider"></span>
						</label>
					</div>
					<div class="toggle-row option-toggle-row">
						<div class="toggle-description">
							<strong>Mode MP4</strong>
							<small>Vidéo max 1080p</small>
						</div>
						<label class="toggle-switch">
							<input type="checkbox" bind:checked={mp4Mode} />
							<span class="toggle-slider"></span>
						</label>
					</div>
				</div>
			</aside>

			<!-- Fields -->
			<div class="metadata-main">
				{#if !extract?.is_playlist}
					<div class="form-group">
						<label class="form-label">Titre</label>
						<input class="form-input" bind:value={title} placeholder="Titre" />
					</div>
					<div class="form-group compact-row">
						{#if !playlistMode}
							<div>
								<label class="form-label">Artiste</label>
								<input class="form-input" bind:value={artist} placeholder="Artiste" />
							</div>
						{/if}
						<div style={playlistMode ? 'grid-column:1/-1' : ''}>
							<label class="form-label">Album</label>
							<input class="form-input" bind:value={album} placeholder="Album" />
						</div>
					</div>
				{:else}
					<div class="playlist-title">{extract.title ?? ''}</div>
					<div class="form-group compact-row">
						{#if !playlistMode}
							<div>
								<label class="form-label">Artiste</label>
								<input class="form-input" bind:value={playlistArtist} placeholder="Artiste" />
							</div>
						{/if}
						<div style={playlistMode ? 'grid-column:1/-1' : ''}>
							<label class="form-label">Album / Playlist</label>
							<input class="form-input" bind:value={playlistAlbum} placeholder="Nom" />
						</div>
					</div>
					<div class="form-group" style="max-width:120px">
						<label class="form-label">Année</label>
						<input class="form-input" bind:value={playlistYear} placeholder="2024" />
					</div>
					{#if (extract?.songs?.length ?? 0) > 0}
						<div class="form-group">
							<label class="form-label">{extract.songs.length} titres</label>
							<div class="song-list-preview">
								{#each extract.songs as song, i}
									<div class="song-row">{i + 1}. {song.title ?? ''}</div>
								{/each}
							</div>
						</div>
					{/if}
				{/if}

				<div class="metadata-actions">
					<button class="btn btn-primary btn-block" on:click={addToQueue}>
						➕ Ajouter à la file
					</button>
					<button class="btn btn-ghost btn-sm" on:click={reset}>Annuler</button>
				</div>
			</div>
		</div>
	</div>
</div>
{/if}


<style>
.playlist-title {
	font-weight: 600;
	font-size: 15px;
	margin-bottom: 12px;
	color: var(--text);
}
.metadata-layout {
	display: grid;
	grid-template-columns: 200px 1fr;
	gap: 20px;
	align-items: start;
}
@media (max-width: 900px) {
	.metadata-layout { grid-template-columns: 1fr; }
}
</style>
