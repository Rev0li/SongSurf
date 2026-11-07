<script>
	import { untrack } from 'svelte';
	// Sélecteur de genre en cascade (SSF-13) : 1. un style générique, 2. une
	// précision facultative, ou « Autre… » en saisie libre. Valeur : « Style » ou
	// « Style; Précision » (TCON multi-valeurs). Noms en anglais (Jellyfin).
	import { GENRES } from '$lib/library/genres.js';

	let {
		value = $bindable(''),
		suggestion = '',      // genre des autres albums de l'artiste
		startOpen = false,
		id = 'genre',
	} = $props();

	let open = $state(untrack(() => startOpen)); // état initial seulement
	let main = $state(null);   // style choisi au 1er niveau
	let other = $state(false); // saisie libre
	let otherText = $state('');

	function pick(v) {
		value = v;
		open = false; main = null; other = false;
	}
	function validateOther() {
		const v = otherText.trim();
		if (v) pick(v);
	}
</script>

<div class="gp">
	<div class="gp-row">
		{#if value}
			<span class="pill">{value}</span>
		{:else}
			<span class="why">Aucun genre choisi</span>
		{/if}
		{#if !open}
			<button type="button" class="btn btn-soft btn-sm" onclick={() => (open = true)}>{value ? 'Changer' : 'Choisir un genre'}</button>
		{:else if value}
			<button type="button" class="link-btn" onclick={() => { open = false; main = null; other = false; }}>Garder</button>
		{/if}
	</div>

	{#if open}
		{#if other}
			<button type="button" class="link-btn gp-back" onclick={() => (other = false)}>‹ Tous les genres</button>
			<div class="gp-row">
				<input id="{id}-other" class="inp" placeholder="Écris le genre" bind:value={otherText}
					onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); validateOther(); } }} />
				<button type="button" class="btn btn-primary btn-sm" onclick={validateOther} disabled={!otherText.trim()}>OK</button>
			</div>
		{:else if !main}
			{#if suggestion && suggestion !== value}
				<p class="why">Comme ses autres albums :</p>
				<div class="chips"><button type="button" class="chip sugg" onclick={() => pick(suggestion)}>{suggestion}</button></div>
			{/if}
			<p class="why">1. Choisis un style (noms en anglais, comme dans Jellyfin)</p>
			<div class="chips">
				{#each Object.keys(GENRES) as g (g)}
					<button type="button" class="chip" onclick={() => (main = g)}>{g}</button>
				{/each}
				<button type="button" class="chip" onclick={() => (other = true)}>Autre…</button>
			</div>
		{:else}
			<button type="button" class="link-btn gp-back" onclick={() => (main = null)}>‹ Tous les genres</button>
			<p class="why">2. Précise si tu veux (facultatif)</p>
			<div class="chips">
				<button type="button" class="chip on" onclick={() => pick(main)}>{main}, sans précision</button>
				{#each GENRES[main] as s (s)}
					<button type="button" class="chip" onclick={() => pick(`${main}; ${s}`)}>{s}</button>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<style>
	.gp { display: flex; flex-direction: column; gap: 10px; }
	.gp-row { display: flex; align-items: center; gap: 10px; justify-content: space-between; }
	.gp-back { align-self: flex-start; }
	.pill { display: inline-flex; padding: 6px 12px; border-radius: var(--r-full); background: var(--bg-4); font-weight: 600; font-size: 14px; overflow-wrap: anywhere; }
	.chips { display: flex; flex-wrap: wrap; gap: 8px; }
	.chip {
		padding: 8px 12px; border-radius: var(--r-full); border: 1px solid var(--sep); background: var(--bg-3);
		color: var(--text); font: inherit; font-size: 14px; font-weight: 500; cursor: pointer;
	}
	.chip:hover { border-color: var(--text-3); }
	.chip.on { background: var(--text); color: var(--bg); border-color: var(--text); }
	.chip.sugg { border-color: var(--accent); color: var(--accent-ink); font-weight: 600; }
</style>
