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

	// cover
	let coverCandidates = [];
	let coverIdx = 0;
	let coverSrc = '';
	let coverLoading = false;

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
			// All CDN candidates exhausted — no cover preview available
			coverSrc = '';
			coverLoading = false;
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

	// ── Extract ───────────────────────────────────────────────────────────────
	let extracting = false;

	async function onExtract() {
		const raw = url.trim();
		if (!raw) { addToast('Colle un lien YouTube Music.', 'error'); return; }

		extracting = true;

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
				panelActive = true;
				await tick();
				setCoverCandidates(candidates);
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
			label: asText(playlistAlbum, extract.title ?? 'Album'),
			playlistMetadata: {
				title:  asText(playlistAlbum, 'Unknown Album'),
				artist: asText(playlistArtist, 'Unknown Artist'),
				year:   asText(playlistYear),
				songs:  extract.songs ?? [],
			},
		} : {
			isPlaylist: false,
			label: `${asText(artist, '?')} — ${asText(title, '?')}`,
			url:    extract.url ?? '',
			title:  asText(title,  'Unknown Title'),
			artist: asText(artist, 'Unknown Artist'),
			album:  asText(album,  'Unknown Album'),
			year:   '',
			track_number: extract.track_number ?? '',
			album_artist: extract.album_artist ?? '',
			// Artiste modifié à la main → la liste multi-artistes extraite n'est plus fiable
			artists: asText(artist) === asText(extract.artist, 'Unknown Artist') ? (extract.artists ?? []) : [],
		};

		onAddToQueue(item);
		reset();
	}

	// ── Reset ─────────────────────────────────────────────────────────────────
	function reset() {
		extract = null;
		panelActive = false;
		title = artist = album = playlistArtist = playlistAlbum = playlistYear = '';
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

			</aside>

			<!-- Fields -->
			<div class="metadata-main">
				{#if !extract?.is_playlist}
					<div class="form-group">
						<label class="form-label">Titre</label>
						<input class="form-input" bind:value={title} placeholder="Titre" />
					</div>
					<div class="form-group compact-row">
						<div>
							<label class="form-label">Artiste</label>
							<input class="form-input" bind:value={artist} placeholder="Artiste" />
						</div>
						<div>
							<label class="form-label">Album</label>
							<input class="form-input" bind:value={album} placeholder="Album" />
						</div>
					</div>
				{:else}
					<div class="playlist-title">{extract.title ?? ''}</div>
					<div class="form-group compact-row">
						<div>
							<label class="form-label">Artiste</label>
							<input class="form-input" bind:value={playlistArtist} placeholder="Artiste" />
						</div>
						<div>
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
