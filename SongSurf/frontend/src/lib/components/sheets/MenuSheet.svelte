<script>
	// Menu « ⋯ » d'un titre, d'un album ou d'un artiste.
	import { closeSheet } from '$lib/ui/sheets.js';
	import Sheet from '../ui/Sheet.svelte';
	import Icon from '../ui/Icon.svelte';
	import Cover from '../ui/Cover.svelte';

	let { title, sub = '', coverSrc = '', coverLabel = '', round = false, items = [], onClose } = $props();

	function choose(item) {
		if (item.sheet) item.run(); // ouvre un autre panneau à la place du menu
		else { closeSheet(); item.run(); }
	}
</script>

<Sheet {title} {sub} {onClose}>
	{#snippet lead()}<Cover src={coverSrc} label={coverLabel || title} size={44} {round} />{/snippet}
	<ul class="menu">
		{#each items as item, i (i)}
			{#if item.divider}
				<li class="menu-divider">{item.divider}</li>
			{:else}
				<li>
					<button type="button" class="menu-item" class:danger={item.danger} onclick={() => choose(item)}>
						<Icon name={item.icon} />{item.label}
						{#if item.expert}<span class="tag-expert">Expert</span>{/if}
					</button>
				</li>
			{/if}
		{/each}
	</ul>
</Sheet>

<style>
	:global(.sheet-body):has(> .menu) { padding: 0; }
</style>
