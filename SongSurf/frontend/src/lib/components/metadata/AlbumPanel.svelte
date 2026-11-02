<script>
	// Panneau album : pochette (upload), infos, tracklist triée par TRCK réels,
	// et les outils experts (renumérotation, suppression).
	import { api } from '$lib/api.js';
	import { addToast, user, confirmAction } from '$lib/stores.js';
	import {
		selection, imgVersions, bumpImgVersion, pastedImage, albumTracks, albumTracksLoading,
		loadAlbumTracks, sortByTrck, trackNum, selectArtist, selectSong, gotoArtistByPath, refreshTree,
	} from '$lib/metadata/library.js';
	import { songDisplayName } from '$lib/metadata/id3.js';
	import Crumbs from './Crumbs.svelte';
	import AlbumReorder from './AlbumReorder.svelte';

	// Suit les titres rafraîchis par refreshTree ; garde la dernière valeur si
	// l'album disparaît (le panneau est alors démonté par la page).
	let album = $selection.album;
	$: album = $selection.album ?? album;
	$: isAdmin = $user?.role === 'admin';
	$: coverUrl = api.getFolderCoverUrl(album.path, $imgVersions[album.path] ?? 0);

	function trackDisplayNum(t) {
		const n = trackNum(t);
		return isNaN(n) ? '—' : String(n);
	}

	// ── Pochette ──────────────────────────────────────────────────────────────
	let uploadingCover = false;

	async function uploadAlbumCover(file) {
		if (!file || uploadingCover) return;
		uploadingCover = true;
		try {
			await api.uploadAlbumCover(album.path, file);
			bumpImgVersion(album.path);
			addToast('Pochette album mise à jour.', 'info');
		} catch (e) { addToast(e.message ?? 'Erreur upload', 'error'); }
		finally { uploadingCover = false; }
	}

	function onPaste(e) {
		const file = pastedImage(e);
		if (file) uploadAlbumCover(file);
	}

	// ── Renumérotation (mode « Numéroter les pistes ») ───────────────────────
	let reorderMode    = false;
	let reorderTracks  = [];
	let reorderLoading = false;

	async function enterReorder() {
		if (reorderLoading) return;
		reorderLoading = true;
		try {
			const data = await api.albumTracks(album.path);
			reorderTracks = sortByTrck(data.tracks ?? []);
			reorderMode = true;
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { reorderLoading = false; }
	}

	function exitReorder() { reorderMode = false; reorderTracks = []; }

	function onReorderSaved() {
		exitReorder();
		loadAlbumTracks(album.path);
	}

	// ── Suppression du dossier (admin) ────────────────────────────────────────
	let deletingFolder = false;

	async function deleteAlbumFolder() {
		if (deletingFolder) return;
		const artistPath = album.artist.path;
		const nSongs = album.songs.length;
		const ok = await confirmAction({
			title: `Supprimer l'album « ${album.name} » ?`,
			message: `${nSongs} titre${nSongs > 1 ? 's' : ''} seront supprimés.\nCette action est irréversible.`,
			confirmLabel: 'Supprimer',
			danger: true,
		});
		if (!ok) return;
		deletingFolder = true;
		try {
			const res = await api.deleteFolder(album.path);
			addToast(`Album supprimé (${res.deleted_songs} titre${res.deleted_songs > 1 ? 's' : ''}).`, 'info');
			await refreshTree();
			gotoArtistByPath(artistPath); // retombe sur l'accueil si l'artiste a disparu (dernier album)
		} catch (e) { addToast(e.message ?? 'Suppression impossible.', 'error'); }
		finally { deletingFolder = false; }
	}
</script>

<svelte:window on:paste={onPaste} />

<div class="meta-content">
	<Crumbs items={[
		{ label: `🎤 ${album.artist.name}`, onClick: () => selectArtist(album.artist) },
		{ label: `💿 ${album.name}` },
	]} />

	<!-- En-tête : pochette + infos -->
	<div class="album-header">
		<div class="album-cover-zone">
			{#key coverUrl}
				<img
					class="album-cover-img"
					src={coverUrl}
					alt=""
					on:error={(e) => e.currentTarget.style.display='none'}
				/>
			{/key}
			<div class="album-cover-placeholder">💿</div>
			<label
				class="album-cover-overlay"
				for="album-cover-file"
				title="Remplacer la pochette"
				class:loading={uploadingCover}
			>
				{uploadingCover ? '⏳' : '📁'}
			</label>
			<input
				type="file" accept="image/*" id="album-cover-file" class="hidden-file"
				on:change={(e) => uploadAlbumCover(e.currentTarget.files?.[0])}
			/>
		</div>

		<div class="album-info">
			<div class="album-artist-chip">{album.artist.name}</div>
			<div class="album-title">{album.name}</div>
			<div class="album-track-count">
				{album.songs.length} titre{album.songs.length > 1 ? 's' : ''}
			</div>
			<p class="cover-hint" style="margin-top:var(--s4)">
				Pochette : glisse ou colle <kbd>Ctrl+V</kbd> pour remplacer
			</p>

			{#if isAdmin}
				<button
					class="btn btn-danger btn-sm folder-delete-btn"
					on:click={deleteAlbumFolder}
					disabled={deletingFolder}
					title="Supprime le dossier album et tous ses titres (irréversible)"
				>
					{deletingFolder ? '⏳…' : "🗑️ Supprimer l'album"}
				</button>
			{/if}
		</div>
	</div>

	<!-- Tracklist -->
	<div class="meta-sections">
		<section class="meta-section">
			<h3 class="section-title">
				🎵 Titres
				{#if !reorderMode}
					<button
						class="section-action"
						on:click={enterReorder}
						disabled={reorderLoading}
						title="Réordonner les titres puis écrire les numéros de piste 1..N (TRCK n/total)"
					>
						{reorderLoading ? '⏳…' : '🔢 Numéroter les pistes'}
					</button>
				{/if}
			</h3>

			{#if reorderMode}
				<AlbumReorder
					albumPath={album.path}
					tracks={reorderTracks}
					onSaved={onReorderSaved}
					onCancel={exitReorder}
				/>
			{:else if $albumTracks}
				<!-- TRCK réels (triés par numéro, sans-numéro à la fin) -->
				<div class="tracklist">
					{#each $albumTracks as track (track.path)}
						<button
							class="track-row {$selection.path === track.path ? 'track-selected' : ''}"
							on:click={() => selectSong(track.path, true)}
						>
							<span class="track-num {trackDisplayNum(track) === '—' ? 'track-num-missing' : ''}">{trackDisplayNum(track)}</span>
							<span class="track-name">{songDisplayName(track.name)}</span>
							{#if trackDisplayNum(track) === '—'}
								<span class="reorder-badge reorder-badge-missing">sans n°</span>
							{/if}
							<span class="track-chevron">›</span>
						</button>
					{/each}
				</div>
			{:else if $albumTracksLoading}
				<!-- Chargement des TRCK réels : pas d'affichage intermédiaire pour éviter le clip visuel -->
				<div class="meta-empty"><span class="meta-empty-icon">⏳</span><p>Chargement des titres…</p></div>
			{:else}
				<!-- Repli : ordre alphabétique si la lecture des TRCK a échoué -->
				<div class="tracklist">
					{#each album.songs as song, i (song.path)}
						<button
							class="track-row {$selection.path === song.path ? 'track-selected' : ''}"
							on:click={() => selectSong(song.path, true)}
						>
							<span class="track-num">{i + 1}</span>
							<span class="track-name">{songDisplayName(song.name)}</span>
							<span class="track-chevron">›</span>
						</button>
					{/each}
				</div>
			{/if}
		</section>
	</div>
</div>

<style>
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
		width: 100%; height: 100%; object-fit: cover; z-index: 1;
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

	.track-chevron { flex-shrink: 0; font-size: 14px; color: var(--text-3); }

	/* Bouton « Numéroter les pistes » dans le titre de section */
	.section-action {
		margin-left: auto;
		background: none; border: 1px solid var(--sep);
		border-radius: var(--r-sm);
		color: var(--blue); font-size: 11px; font-weight: 500;
		text-transform: none; letter-spacing: 0;
		padding: 3px 8px; cursor: pointer;
		transition: background .1s;
	}
	.section-action:hover { background: rgba(10,132,255,.08); }
	.section-action:disabled { opacity: .5; pointer-events: none; }

	@media (max-width: 480px) {
		/* Album header: stack cover + info */
		.album-header { flex-direction: column; gap: var(--s4); padding: var(--s3) 0 var(--s4); }
		.album-cover-zone { width: 120px; height: 120px; }
	}
</style>
