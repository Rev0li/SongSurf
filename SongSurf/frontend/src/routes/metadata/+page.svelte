<script>
	// Page /metadata : arborescence à gauche, panneau de la sélection à droite.
	// L'état partagé vit dans $lib/metadata/library.js, chaque panneau dans
	// $lib/components/metadata/ (voir docs/FRONTEND_MAP.md).
	import { onMount, tick } from 'svelte';
	import '$lib/styles/metadata.css';
	import { api } from '$lib/api.js';
	import Header from '$lib/components/Header.svelte';
	import LibrarySidebar from '$lib/components/metadata/LibrarySidebar.svelte';
	import ArtistGallery from '$lib/components/metadata/ArtistGallery.svelte';
	import ArtistPanel from '$lib/components/metadata/ArtistPanel.svelte';
	import AlbumPanel from '$lib/components/metadata/AlbumPanel.svelte';
	import SongPanel from '$lib/components/metadata/SongPanel.svelte';
	import {
		LS, lsGet, lsSet, tree, selection, secondaryOpen, persistTree, restoreSelection,
	} from '$lib/metadata/library.js';

	// ── Position de scroll de la galerie d'artistes ───────────────────────────
	// Restaurée après un remount (ex : aller sur Téléchargement puis revenir).
	let metaMainEl = $state();
	let homeScrollSaveTimer = null;

	function saveHomeScroll() {
		if ($selection.type !== null || !metaMainEl) return;
		clearTimeout(homeScrollSaveTimer);
		homeScrollSaveTimer = setTimeout(() => {
			lsSet(LS.homeScroll, String(metaMainEl.scrollTop));
		}, 150);
	}

	async function restoreHomeScroll() {
		await tick();
		if ($selection.type !== null || !metaMainEl) return;
		metaMainEl.scrollTop = parseInt(lsGet(LS.homeScroll, '0'), 10) || 0;
	}

	onMount(async () => {
		secondaryOpen.set(false); // comme avant le découpage : replié à chaque ouverture de la page

		// Stale-while-revalidate : affiche le dernier arbre connu pendant le fetch
		let cached = null;
		try { cached = JSON.parse(lsGet(LS.tree, 'null')); } catch { /* ignore */ }
		if (cached?.artists) {
			tree.set(cached);
			restoreSelection();
			restoreHomeScroll();
		}

		try {
			const fresh = await api.getLibrary();
			// Si rien n'a changé depuis le cache, on garde l'affichage tel quel
			if (!cached?.artists || JSON.stringify(fresh) !== JSON.stringify(cached)) {
				tree.set(fresh);
				persistTree();
				// Re-résout la sélection contre l'arbre frais (les objets du cache sont périmés)
				restoreSelection();
				restoreHomeScroll();
			}
		} catch {
			if (!$tree) tree.set({ artists: [], playlists: [] });
		}
	});
</script>

<svelte:head><title>Métadonnées — SongSurf</title></svelte:head>

<Header />

<div class="meta-layout">
	<LibrarySidebar />

	<main class="meta-main" bind:this={metaMainEl} onscroll={saveHomeScroll}>
		<!-- Un remount par sélection : chaque panneau repart d'un état local vierge -->
		{#key $selection.seq}
			{#if $selection.type === null}
				<ArtistGallery />
			{:else if $selection.type === 'artist'}
				<ArtistPanel />
			{:else if $selection.type === 'album'}
				<AlbumPanel />
			{:else if $selection.type === 'song'}
				<SongPanel />
			{/if}
		{/key}
	</main>
</div>

<style>
	.meta-layout {
		display: flex;
		/* 93px = header (52) + onglets (40) + bordure (1) — voir Header.svelte */
		height: calc(100dvh - 93px);
		overflow: hidden;
	}

	.meta-main { flex: 1; overflow-y: auto; padding: var(--s6); background: var(--bg); }

	@media (max-width: 480px) {
		/* Two-panel → stacked */
		.meta-layout { flex-direction: column; height: auto; overflow: visible; }
		.meta-main { overflow-y: visible; padding: var(--s3); }
	}
</style>
