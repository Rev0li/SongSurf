<script>
	// « Ajouter » (SSF-13) : coller un lien, vérifier la fiche, suivre les téléchargements.
	import AddForm from '$lib/components/add/AddForm.svelte';
	import DownloadList from '$lib/components/add/DownloadList.svelte';
	import { dailyLeft, myDownloads, dlHistory } from '$lib/downloads.js';

	let idle = $derived(!$myDownloads.active && $dlHistory.length === 0);
</script>

<svelte:head>
	<title>Ajouter — SongSurf</title>
</svelte:head>

<section class="page">
	<div>
		<h1 class="ptitle">Ajouter</h1>
		<p class="psub-top why">Colle un lien YouTube Music : titre, album ou playlist.</p>
	</div>

	<AddForm />

	{#if $dailyLeft !== null}
		<p class="why center">
			{$dailyLeft > 0
				? `Encore ${$dailyLeft} ajout${$dailyLeft > 1 ? 's' : ''} possible${$dailyLeft > 1 ? 's' : ''} aujourd'hui`
				: "Limite du jour atteinte : tu pourras ajouter d'autres titres demain."}
		</p>
	{/if}

	<DownloadList />

	{#if idle}
		<div class="ss-card help">
			<h2>Comment faire ?</h2>
			<ol>
				<li>Ouvre YouTube Music et choisis un titre, un album ou une playlist.</li>
				<li>Appuie sur <b>Partager</b> puis <b>Copier le lien</b>.</li>
				<li>Reviens ici et appuie sur <b>Coller le lien copié</b>.</li>
			</ol>
			<p class="why">Sur ordinateur, l'extension Chrome ajoute directement depuis YouTube Music.</p>
		</div>
	{/if}
</section>

<style>
	.psub-top { margin-top: 4px; font-size: 14px; }
	.center { text-align: center; }
	.help h2 { margin: 0; font-size: 15px; }
	.help ol { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 4px; color: var(--text-2); font-size: 14px; }
</style>
