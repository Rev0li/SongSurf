<script>
	// Panneau titre : charge les métadonnées du fichier, flèches précédent/suivant
	// dans l'album, éditeur de tags, puis les sections avancées (TXXX, audio, pochette).
	import { onMount } from 'svelte';
	import { api } from '$lib/api.js';
	import { addToast, helpOpen } from '$lib/stores.js';
	import {
		tree, selection, imgVersions, bumpImgVersion, pastedImage, albumTracks,
		selectSong, gotoArtistByPath, gotoAlbumByPath,
	} from '$lib/metadata/library.js';
	import { songDisplayName, fmtBytes } from '$lib/metadata/id3.js';
	import Crumbs from './Crumbs.svelte';
	import SongTagsEditor from './SongTagsEditor.svelte';
	import SongDetails from './SongDetails.svelte';

	// Monté une fois par titre sélectionné (clé = selection.seq dans la page)
	const path  = $selection.path;
	const album = $selection.album; // contexte album (flèches) si on vient du panneau album

	let meta    = $state(null);
	let loading = $state(true);
	let error   = $state('');

	onMount(async () => {
		try {
			const data = await api.songMeta(path);
			if (data.success) meta = data;
			else error = data.error ?? 'Erreur inconnue';
		} catch (e) { error = e.message ?? 'Erreur réseau'; }
		finally { loading = false; }
	});

	// ── Fil d'Ariane (déduit du chemin du fichier) ────────────────────────────
	const parts = path.split('/');
	const crumbs = [
		...(parts.length === 3 ? [
			{ label: `🎤 ${parts[0]}`, onClick: () => gotoArtistByPath(parts[0]) },
			{ label: `💿 ${parts[1]}`, onClick: () => gotoAlbumByPath(parts[0], parts.slice(0, 2).join('/')) },
		] : parts.length === 2 ? [{ label: `📁 ${parts[0]}` }] : []),
		{ label: songDisplayName(parts[parts.length - 1] ?? '') },
	];

	// ── Titre précédent / suivant dans l'album ────────────────────────────────
	let ordered = $derived(album ? ($albumTracks ?? album.songs ?? []) : null);
	let index   = $derived(ordered ? ordered.findIndex((t) => t.path === path) : -1);
	let prevTrack = $derived(ordered && index > 0 ? ordered[index - 1] : null);
	let nextTrack = $derived(ordered && index >= 0 && index < ordered.length - 1 ? ordered[index + 1] : null);

	function goPrev() { if (prevTrack) selectSong(prevTrack.path, true); }
	function goNext() { if (nextTrack) selectSong(nextTrack.path, true); }

	function onKeydown(e) {
		if ($helpOpen) return;
		if (e.ctrlKey || e.metaKey || e.altKey) return;
		const tag = e.target?.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable) return;
		if (e.key === 'ArrowLeft' && prevTrack) { e.preventDefault(); goPrev(); }
		else if (e.key === 'ArrowRight' && nextTrack) { e.preventDefault(); goNext(); }
	}

	// ── Titres de l'album visés par « Appliquer à l'album » ───────────────────
	// selection.album si on vient du panneau album, sinon déduits de l'arbre.
	let albumSongs = $derived.by(() => {
		if ($selection.album) return $selection.album.songs ?? [];
		if (!meta?.path || !$tree) return [];
		const p = meta.path.split('/');
		if (p.length < 3) return [];
		const albumPath = p.slice(0, 2).join('/');
		const artist = ($tree.artists ?? []).find((a) => a.path === p[0]);
		return artist?.albums?.find((a) => a.path === albumPath)?.songs ?? [];
	});

	// ── Pochette (écrit l'APIC du titre + cover.jpg du dossier album) ─────────
	let albumFolderPath = $derived(meta?.path ? meta.path.split('/').slice(0, -1).join('/') : '');
	let albumCoverUrl   = $derived(albumFolderPath ? api.getFolderCoverUrl(albumFolderPath, $imgVersions[albumFolderPath] ?? 0) : '');

	let uploadingCover = $state(false);
	let coverError     = $state('');

	async function uploadSongCover(file) {
		if (!file || uploadingCover) return;
		uploadingCover = true; coverError = '';
		try {
			await api.uploadSongCover(path, file);
			bumpImgVersion(albumFolderPath);
			const data = await api.songMeta(path);
			if (data.success) meta = data;
			addToast('Pochette mise à jour.', 'info');
		} catch (e) { coverError = e.message ?? 'Erreur'; }
		finally { uploadingCover = false; }
	}

	function onPaste(e) {
		const file = pastedImage(e);
		if (file) uploadSongCover(file);
	}
</script>

<svelte:window onpaste={onPaste} onkeydown={onKeydown} />

{#if loading}
	<div class="meta-empty"><span class="meta-empty-icon">⏳</span><p>Chargement…</p></div>
{:else if error}
	<div class="meta-empty"><span class="meta-empty-icon">❌</span><p>{error}</p></div>
{:else if meta}
	<div class="song-nav-row">
		{#if album}
			<button
				class="song-nav-arrow"
				disabled={!prevTrack}
				onclick={goPrev}
				title={prevTrack ? `Titre précédent : ${songDisplayName(prevTrack.name)}` : 'Premier titre de l\'album'}
				aria-label="Titre précédent"
			>‹</button>
		{/if}
		<div class="meta-content">
			<Crumbs items={crumbs} />

			<div class="meta-sections">
				<!-- Fichier (lecture seule) -->
				<section class="meta-section">
					<h3 class="section-title">📄 Fichier</h3>
					<div class="meta-grid">
						<div class="meta-row"><span class="meta-key">Nom</span><span class="meta-val">{meta.file_name}</span></div>
						<div class="meta-row"><span class="meta-key">Taille</span><span class="meta-val">{fmtBytes(meta.file_size)}</span></div>
					</div>
				</section>

				{#if meta.id3}
					<SongTagsEditor {path} {meta} {albumSongs} onMetaReloaded={(m) => { meta = m; }} />
					<SongDetails
						{meta}
						{albumCoverUrl}
						uploading={uploadingCover}
						error={coverError}
						onUpload={uploadSongCover}
					/>
				{/if}
			</div>
		</div>
		{#if album}
			<button
				class="song-nav-arrow"
				disabled={!nextTrack}
				onclick={goNext}
				title={nextTrack ? `Titre suivant : ${songDisplayName(nextTrack.name)}` : 'Dernier titre de l\'album'}
				aria-label="Titre suivant"
			>›</button>
		{/if}
	</div>
{/if}

<style>
	/* ── Navigation titre précédent/suivant ──────────────────── */
	.song-nav-row { display: flex; align-items: flex-start; gap: var(--s3); }
	.song-nav-row > .meta-content { flex: 1 1 auto; min-width: 0; }
	.song-nav-arrow {
		flex-shrink: 0;
		position: sticky; top: var(--s6);
		width: 40px; height: 40px; border-radius: 50%;
		display: flex; align-items: center; justify-content: center;
		font-size: 20px; line-height: 1;
		background: var(--bg-2); border: 1px solid var(--sep); color: var(--text);
		cursor: pointer; transition: background .1s, color .1s, border-color .1s, opacity .1s;
	}
	.song-nav-arrow:hover:not(:disabled) { background: rgba(10,132,255,.12); color: var(--blue); border-color: var(--blue); }
	.song-nav-arrow:disabled { opacity: .3; cursor: default; }

	@media (max-width: 480px) {
		/* Song nav arrows: smaller, tighter gap */
		.song-nav-row { gap: var(--s2); }
		.song-nav-arrow { width: 32px; height: 32px; font-size: 16px; }
	}
</style>
