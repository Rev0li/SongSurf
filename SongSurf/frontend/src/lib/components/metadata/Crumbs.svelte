<script>
	// Fil d'Ariane des panneaux artiste / album / titre.
	// items : [{ label, onClick? }] — sans onClick, le segment est affiché comme courant.
	import { goHome } from '$lib/metadata/library.js';

	let { items = [] } = $props();
</script>

<nav class="crumbs">
	<button class="crumb" onclick={goHome}>🏠 Bibliothèque</button>
	{#each items as item}
		<span class="crumb-sep">›</span>
		{#if item.onClick}
			<button class="crumb" onclick={item.onClick}>{item.label}</button>
		{:else}
			<span class="crumb-current">{item.label}</span>
		{/if}
	{/each}
</nav>

<style>
	.crumbs {
		display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
		margin-bottom: var(--s4);
		font-size: 13px;
	}
	.crumb {
		background: none; border: none; padding: 0;
		color: var(--blue); font-size: 13px; cursor: pointer;
		max-width: 220px;
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.crumb:hover { text-decoration: underline; text-underline-offset: 2px; }
	.crumb-sep { color: var(--text-3); flex-shrink: 0; }
	.crumb-current {
		color: var(--text); font-weight: 500;
		max-width: 280px;
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
</style>
