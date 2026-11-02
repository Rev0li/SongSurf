<script>
	import { untrack } from 'svelte';
	// « Déplacer vers… » (SSF-13) : un titre → artiste puis album ; un album → artiste.
	// Une fenêtre dit d'où vers où, et ce qui change dans les infos.
	import { get } from 'svelte/store';
	import { api } from '$lib/api.js';
	import { addToast, confirmAction } from '$lib/stores.js';
	import { closeSheet, closeSheetAndGo } from '$lib/ui/sheets.js';
	import { tree, findAlbum, parentPath, refreshLibrary, albumUrl, coverUrl, pictureUrl, plural, songTitle } from '$lib/library/data.js';
	import Sheet from '../ui/Sheet.svelte';
	import Cover from '../ui/Cover.svelte';
	import Icon from '../ui/Icon.svelte';

	let { what, path, onDone = () => {}, onClose } = $props();

	// Panneau remonté à chaque ouverture : props lues une fois
	const t = get(tree);
	const { isTrack, srcAlbumPath, src, label } = untrack(() => {
		const isTrack = what === 'track';
		const srcAlbumPath = isTrack ? parentPath(path) : path;
		const src = findAlbum(t, srcAlbumPath);
		return { isTrack, srcAlbumPath, src, label: isTrack ? songTitle(path.split('/').pop()) : (src?.album.name ?? path) };
	});

	let artistPath = $state(null); // étape 2 (titre) : artiste choisi
	let busy = $state(false);

	let artists = $derived((t?.artists ?? []).filter((a) => isTrack || a.path !== src?.artist?.path));
	let chosen = $derived(artists.find((a) => a.path === artistPath) ?? null);
	let albums = $derived((chosen?.albums ?? []).filter((al) => al.path !== srcAlbumPath));

	async function moveTrackTo(album) {
		const from = `${src?.artist?.name ?? '?'} › ${src?.album.name ?? '?'}`;
		const changesArtist = chosen.path !== src?.artist?.path;
		const ok = await confirmAction({
			title: `Déplacer « ${label} » ?`,
			message: [
				`De : ${from}`,
				`Vers : ${chosen.name} › ${album.name}`,
				'',
				`Il rejoint l'album ${album.name} : ses infos Album et Artiste de l'album deviennent « ${album.name} » et « ${chosen.name} ».`,
				...(changesArtist ? [`L'artiste principal devient ${chosen.name} ; les artistes invités (featurings) sont gardés.`] : []),
			].join('\n'),
			confirmLabel: 'Déplacer',
		});
		if (!ok) return;
		busy = true;
		try {
			await api.moveSong(path, album.path);
			addToast(`Déplacé dans ${album.name}.`, 'info');
			await refreshLibrary();
			onDone();
			closeSheet();
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { busy = false; }
	}

	async function moveAlbumTo(artist) {
		const n = src?.album.songs?.length ?? 0;
		const ok = await confirmAction({
			title: `Déplacer l'album « ${label} » ?`,
			message: [
				`De : ${src?.artist?.name ?? '?'}`,
				`Vers : ${artist.name}`,
				'',
				`Ses ${plural(n, 'titre')} changent de dossier : leur Artiste de l'album devient « ${artist.name} », l'artiste principal aussi (les featurings sont gardés).`,
			].join('\n'),
			confirmLabel: 'Déplacer',
		});
		if (!ok) return;
		busy = true;
		try {
			const res = await api.moveFolder(path, artist.path);
			addToast(`Album déplacé chez ${artist.name}.`, 'info');
			await refreshLibrary();
			closeSheetAndGo(albumUrl(res.new_path ?? `${artist.path}/${src?.album.name}`));
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { busy = false; }
	}
</script>

<Sheet title="Déplacer vers…" sub="« {label} »" tall {onClose}>
	{#if !isTrack}
		<p class="why">Choisis l'artiste qui doit contenir cet album.</p>
		<ul class="rows">
			{#each artists as a (a.path)}
				<li class="row">
					<button type="button" class="row-main" onclick={() => moveAlbumTo(a)} disabled={busy}>
						<Cover src={a.has_picture ? pictureUrl(a.path) : ''} label={a.name} size={44} round />
						<span class="row-txt"><span class="row-t"><span>{a.name}</span></span><span class="row-s">{plural(a.albums.length, 'album')}</span></span>
					</button>
				</li>
			{/each}
		</ul>
	{:else if !chosen}
		<p class="why">Étape 1 sur 2 : choisis l'artiste.</p>
		<ul class="rows">
			{#each artists as a (a.path)}
				<li class="row">
					<button type="button" class="row-main" onclick={() => (artistPath = a.path)}>
						<Cover src={a.has_picture ? pictureUrl(a.path) : ''} label={a.name} size={44} round />
						<span class="row-txt"><span class="row-t"><span>{a.name}</span></span><span class="row-s">{plural(a.albums.length, 'album')}</span></span>
						<Icon name="next" size={16} />
					</button>
				</li>
			{/each}
		</ul>
	{:else}
		<button type="button" class="link-btn back" onclick={() => (artistPath = null)}>‹ Tous les artistes</button>
		<p class="why">Étape 2 sur 2 : choisis l'album de {chosen.name}.</p>
		{#if albums.length === 0}
			<p class="note">Aucun autre album chez {chosen.name}.</p>
		{:else}
			<ul class="rows">
				{#each albums as al (al.path)}
					<li class="row">
						<button type="button" class="row-main" onclick={() => moveTrackTo(al)} disabled={busy}>
							<Cover src={coverUrl(al.path)} label={al.name} size={44} />
							<span class="row-txt"><span class="row-t"><span>{al.name}</span></span><span class="row-s">{plural(al.songs?.length ?? 0, 'titre')}</span></span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	{/if}
</Sheet>

<style>
	.back { align-self: flex-start; }
</style>
