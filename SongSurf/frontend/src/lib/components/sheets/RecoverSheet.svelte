<script>
	// « Récupérer ma musique » (membres, SSF-13) : 3 étapes expliquées. Le ZIP est
	// construit sur le serveur, puis téléchargé ; la bibliothèque n'est vidée que
	// si le fichier est allé jusqu'au bout (SSF-14).
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { closeSheet } from '$lib/ui/sheets.js';
	import { tree, allSongs, refreshLibrary, plural } from '$lib/library/data.js';
	import Sheet from '../ui/Sheet.svelte';
	import Icon from '../ui/Icon.svelte';

	let { onClose } = $props();

	let zip = $state({ status: 'loading' }); // loading | idle | building | ready | error
	let sent = $state(false);                // téléchargement lancé
	let poll = null;

	let nSongs = $derived(allSongs($tree).length);
	let stage = $derived(sent ? 2 : zip.status === 'ready' ? 1 : zip.status === 'building' ? 0 : -1);
	let pct = $derived(zip.total ? Math.round(((zip.done ?? 0) / zip.total) * 100) : 0);

	onMount(async () => {
		try {
			zip = await api.zipStatus();
			if (zip.status === 'building') startPolling();
		} catch { zip = { status: 'idle' }; }
	});
	onDestroy(stopPolling);

	function startPolling() {
		stopPolling();
		poll = setInterval(async () => {
			try { zip = await api.zipStatus(); } catch { return; }
			if (zip.status !== 'building') stopPolling();
		}, 1000);
	}
	function stopPolling() { if (poll) clearInterval(poll); poll = null; }

	async function prepare() {
		try {
			zip = await api.prepareZip();
			startPolling();
		} catch (e) {
			zip = { status: 'idle' };
			addToast(e.message || 'Impossible de préparer le ZIP.', 'error');
		}
	}

	function download() {
		window.location.href = (zip.download_url || '/api/download-zip') + '?t=' + Date.now();
		sent = true;
	}

	// Le ZIP n'est plus prêt si le téléchargement est allé au bout (bibliothèque vidée)
	async function recheck() {
		try { zip = await api.zipStatus(); } catch { /* garde l'état */ }
		sent = false;
	}

	function finished() {
		refreshLibrary();
		closeSheet();
	}

	const cls = (k) => (stage > k ? 'done' : stage === k ? 'now' : '');
</script>

<Sheet title="Récupérer ma musique" sub="Export ZIP" tall {onClose}>
	{#if zip.status === 'idle' && !sent}
		<p>Tu récupères <b>{plural(nSongs, 'titre')}</b> dans un seul fichier ZIP, rangés par artiste et par album.</p>
	{/if}

	<ol class="steps">
		<li class={cls(0)}><span class="n">{stage > 0 ? '✓' : 1}</span><span><strong>On prépare un fichier ZIP</strong>Ça prend un moment ; tu peux fermer ce panneau en attendant.</span></li>
		<li class={cls(1)}><span class="n">{stage > 1 ? '✓' : 2}</span><span><strong>Tu le télécharges</strong>Garde l'écran allumé jusqu'à la fin.</span></li>
		<li class={cls(2)}><span class="n">3</span><span><strong>Ta bibliothèque SongSurf est vidée</strong>Seulement si le téléchargement est allé jusqu'au bout.</span></li>
	</ol>

	{#if zip.status === 'loading'}
		<div class="spinner" aria-label="Chargement"></div>
	{:else if zip.status === 'idle' && !sent}
		<p class="note">SongSurf garde ta musique seulement en attendant que tu la récupères. Après le téléchargement, elle n'est plus ici : pense à la ranger sur ton appareil.</p>
	{:else if zip.status === 'building'}
		<div>
			<p class="why">Préparation… {zip.done ?? 0} / {zip.total ?? '…'} titres</p>
			<div class="bar"><i style="width:{pct}%"></i></div>
		</div>
	{:else if zip.status === 'ready' && !sent}
		<p><b>Ton ZIP est prêt</b>{zip.size_mb ? ` · ${zip.size_mb} Mo` : ''}.</p>
	{:else if sent}
		<div class="empty compact">
			<Icon name="down" size={28} />
			<h2>Téléchargement lancé</h2>
			<p>Ton navigateur enregistre le fichier dans Téléchargements. Ta bibliothèque sera vidée une fois le fichier complet.</p>
		</div>
		<p class="note">Si le téléchargement est coupé (réseau, téléphone verrouillé), rien n'est effacé : reviens ici et appuie sur « Récupérer le ZIP ».</p>
	{:else if zip.status === 'error'}
		<p class="err-title" role="alert">{zip.error || 'La préparation du ZIP a échoué.'}</p>
	{/if}

	{#snippet foot()}
		{#if zip.status === 'idle' && !sent}
			<div class="sheet-foot">
				<button type="button" class="btn btn-soft" onclick={onClose}>Plus tard</button>
				<button type="button" class="btn btn-dark" onclick={prepare} disabled={nSongs === 0}>Préparer le ZIP</button>
			</div>
		{:else if zip.status === 'building'}
			<div class="sheet-foot one"><button type="button" class="btn btn-soft" onclick={onClose}>Fermer</button></div>
		{:else if zip.status === 'ready' && !sent}
			<div class="sheet-foot one"><button type="button" class="btn btn-dark btn-big with-ico" onclick={download}><Icon name="down" />Récupérer le ZIP</button></div>
		{:else if sent}
			<div class="sheet-foot">
				<button type="button" class="btn btn-soft" onclick={recheck}>Pas reçu ? Revoir</button>
				<button type="button" class="btn btn-primary" onclick={finished}>Terminé</button>
			</div>
		{:else if zip.status === 'error'}
			<div class="sheet-foot one"><button type="button" class="btn btn-dark" onclick={prepare}>Réessayer</button></div>
		{/if}
	{/snippet}
</Sheet>

<style>
	p { margin: 0; }
	.compact { padding: 10px 0; }
	.with-ico { display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
</style>
