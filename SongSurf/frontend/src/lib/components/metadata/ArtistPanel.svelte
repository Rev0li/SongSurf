<script>
	// Panneau artiste : photo (upload), infos, grille des albums avec badges de
	// complétude, puis les outils experts (genre de l'artiste, suppression, audit).
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { addToast, user, confirmAction } from '$lib/stores.js';
	import {
		tree, selection, imgVersions, bumpImgVersion, pastedImage,
		selectAlbum, goHome, refreshTree,
	} from '$lib/metadata/library.js';
	import { countSongs } from '$lib/metadata/id3.js';
	import Crumbs from './Crumbs.svelte';
	import ArtistGenre from './ArtistGenre.svelte';
	import ArtistAudit from './ArtistAudit.svelte';

	// Monté une fois par sélection (clé = selection.seq dans la page)
	const artist = $selection.artist;

	let isAdmin = $derived($user?.role === 'admin');

	// Liste complète (non filtrée) des albums de l'artiste
	let artistAlbums = $derived(($tree?.artists ?? []).find((a) => a.path === artist.path)?.albums ?? []);
	let nSongs = $derived(countSongs(artistAlbums));
	let artistPicUrl = $derived(api.getArtistPictureUrl(artist.path, $imgVersions[artist.path] ?? 0));

	// ── Photo artiste ─────────────────────────────────────────────────────────
	let artistPicMissing = $state(false); // true quand la photo ne se charge pas
	let uploadingArtist  = $state(false);

	async function uploadArtistPic(file) {
		if (!file || uploadingArtist) return;
		uploadingArtist = true;
		try {
			await api.uploadArtistCover(artist.path, file);
			bumpImgVersion(artist.path);
			addToast('Photo artiste mise à jour.', 'info');
		} catch (e) { addToast(e.message ?? 'Erreur upload', 'error'); }
		finally { uploadingArtist = false; }
	}

	function onPaste(e) {
		const file = pastedImage(e);
		if (file) uploadArtistPic(file);
	}

	// ── Statut de complétude des albums (badges) ──────────────────────────────
	let albumStatus = $state({}); // album path → {tracks, missing: {genre, year, track_number}, complete, genres}
	let destroyed = false;

	async function loadAlbumStatus() {
		albumStatus = {};
		try {
			const data = await api.albumStatus(artist.path);
			if (destroyed) return; // sélection changée entre-temps
			albumStatus = Object.fromEntries((data.albums ?? []).map((a) => [a.path, a]));
		} catch { /* badges absents, pas bloquant */ }
	}

	function statusTooltip(st) {
		const parts = [];
		if (st.missing.genre)        parts.push(`genre (${st.missing.genre})`);
		if (st.missing.year)         parts.push(`année (${st.missing.year})`);
		if (st.missing.track_number) parts.push(`n° de piste (${st.missing.track_number})`);
		return parts.length ? `Manque : ${parts.join(', ')}` : 'Tags complets';
	}

	onMount(() => {
		loadAlbumStatus();
		return () => { destroyed = true; };
	});

	// ── Suppression du dossier (admin — la bibliothèque admin est permanente) ──
	let deletingFolder = $state(false);

	async function deleteArtistFolder() {
		if (deletingFolder) return;
		const ok = await confirmAction({
			title: `Supprimer « ${artist.name} » ?`,
			message: `${artistAlbums.length} album${artistAlbums.length > 1 ? 's' : ''}, ${nSongs} titre${nSongs > 1 ? 's' : ''} seront supprimés.\n`
				+ 'Cette action est irréversible.',
			confirmLabel: 'Supprimer',
			danger: true,
		});
		if (!ok) return;
		deletingFolder = true;
		try {
			const res = await api.deleteFolder(artist.path);
			addToast(`Dossier supprimé (${res.deleted_songs} titre${res.deleted_songs > 1 ? 's' : ''}).`, 'info');
			goHome();
			await refreshTree();
		} catch (e) { addToast(e.message ?? 'Suppression impossible.', 'error'); }
		finally { deletingFolder = false; }
	}
</script>

<svelte:window onpaste={onPaste} />

<div class="meta-content">
	<Crumbs items={[{ label: `🎤 ${artist.name}` }]} />

	<!-- En-tête : photo + nom + upload -->
	<div class="artist-panel">
		<div class="artist-pic-zone">
			{#key artistPicUrl}
				<img
					class="artist-pic"
					src={artistPicUrl}
					alt=""
					onload={() => { artistPicMissing = false; }}
					onerror={(e) => { e.currentTarget.style.display='none'; artistPicMissing = true; }}
				/>
			{/key}
			<div class="artist-pic-placeholder">🎤</div>
		</div>

		<div class="artist-info">
			<div class="artist-folder-label">Dossier artiste</div>
			<div class="artist-name">{artist.name}</div>
			{#if artistPicMissing}
				<div class="artist-pic-warn">⚠️ Photo artiste manquante — Jellyfin ne pourra pas afficher l'image de l'artiste</div>
			{/if}
			<div class="artist-album-count-label">
				{artistAlbums.length} album{artistAlbums.length > 1 ? 's' : ''} ·
				{nSongs} titres
			</div>

			<div class="cover-upload-zone" style="border-top:none;padding-left:0;padding-right:0">
				<p class="cover-hint">Photo artiste — glisse, colle (Ctrl+V) ou clique</p>
				<div class="cover-drop-row">
					<input
						type="file" accept="image/*" id="artist-pic-file" class="hidden-file"
						onchange={(e) => uploadArtistPic(e.currentTarget.files?.[0])}
					/>
					<label for="artist-pic-file" class="btn btn-ghost btn-sm" class:loading={uploadingArtist}>
						{uploadingArtist ? '⏳…' : '📁 Choisir'}
					</label>
				</div>
			</div>

			<ArtistGenre {artist} albums={artistAlbums} {albumStatus} onApplied={loadAlbumStatus} />

			{#if isAdmin}
				<button
					class="btn btn-danger btn-sm folder-delete-btn"
					onclick={deleteArtistFolder}
					disabled={deletingFolder}
					title="Supprime le dossier artiste et tout son contenu (irréversible)"
				>
					{deletingFolder ? '⏳…' : '🗑️ Supprimer le dossier'}
				</button>
			{/if}
		</div>
	</div>

	{#if artistAlbums.length > 0}
		<div class="meta-sections">
			<section class="meta-section">
				<h3 class="section-title">💿 Albums — {artistAlbums.length}</h3>
				<div class="artist-album-grid">
					{#each artistAlbums as album (album.path)}
						<button class="artist-album-card" onclick={() => selectAlbum(album, artist)}>
							<div class="artist-album-cover">
								<img
									src={api.getFolderCoverUrl(album.path, $imgVersions[album.path] ?? 0)}
									alt=""
									loading="lazy"
									onload={(e) => e.currentTarget.style.display=''}
									onerror={(e) => e.currentTarget.style.display='none'}
								/>
								<div class="artist-album-placeholder">💿</div>
								{#if albumStatus[album.path]}
									{#if albumStatus[album.path].complete}
										<span class="album-badge album-badge-ok" title="Genre, année et n° de piste complets">✓</span>
									{:else}
										<span class="album-badge album-badge-warn" title={statusTooltip(albumStatus[album.path])}>!</span>
									{/if}
								{/if}
							</div>
							<div class="artist-album-name" title={album.name}>{album.name}</div>
							<div class="artist-album-count">{album.songs.length} titre{album.songs.length > 1 ? 's' : ''}</div>
						</button>
					{/each}
				</div>
			</section>

			<!-- Audit métadonnées (tous les membres : scan iTunes de leur bibliothèque) -->
			<ArtistAudit artistPath={artist.path} />
		</div>
	{/if}
</div>

<style>
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

	/* ── Grille des albums ────────────────────────────────────── */
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
		width: 100%; height: 100%; object-fit: cover; z-index: 1;
	}
	.artist-album-placeholder { font-size: 26px; color: var(--text-3); z-index: 0; }

	/* Badge de complétude des tags (genre/année/n° de piste) */
	.album-badge {
		position: absolute; top: 4px; right: 4px; z-index: 2;
		width: 18px; height: 18px;
		display: flex; align-items: center; justify-content: center;
		border-radius: 50%;
		font-size: 11px; font-weight: 700;
		cursor: help;
	}
	.album-badge-ok   { background: rgba(48,209,88,.2);  color: var(--green);  border: 1px solid rgba(48,209,88,.4); }
	.album-badge-warn { background: rgba(255,159,10,.25); color: var(--orange); border: 1px solid rgba(255,159,10,.5); }
	.artist-album-name {
		font-size: 12px; font-weight: 500; color: var(--text);
		width: 100%;
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.artist-album-count { font-size: 11px; color: var(--text-3); }

	@media (max-width: 480px) {
		/* Artist header: stack photo + info */
		.artist-panel { flex-direction: column; gap: var(--s4); padding: var(--s3) 0; }
		.artist-pic-zone { width: 100px; height: 100px; }
	}
</style>
