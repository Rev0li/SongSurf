<script>
	// Panneau du bas : fond cliquable, poignée, en-tête (titre, sous-titre, illustration),
	// corps qui défile, pied (boutons). Échap ou fond → onClose.
	import { onMount } from 'svelte';
	import Icon from './Icon.svelte';

	let {
		title = '',
		sub = '',
		tall = false,
		onClose = () => {},
		lead,      // snippet : illustration à gauche du titre
		children,  // snippet : corps
		foot,      // snippet : pied
		bodyEl = $bindable(null),
	} = $props();

	let panel;
	let previousFocus = null;

	onMount(() => {
		previousFocus = document.activeElement;
		// Focus sur le panneau (pas sur un champ : le clavier mobile ne doit pas s'ouvrir tout seul)
		panel?.focus({ preventScroll: true });
		const prevOverflow = document.body.style.overflow;
		document.body.style.overflow = 'hidden';
		return () => {
			document.body.style.overflow = prevOverflow;
			if (previousFocus?.isConnected) previousFocus.focus?.({ preventScroll: true });
		};
	});

	function onKeydown(e) {
		if (e.key === 'Escape') { e.stopPropagation(); onClose(); }
	}
</script>

<div class="sheet-backdrop" onclick={onClose} aria-hidden="true"></div>
<div class="sheet" class:tall role="dialog" aria-modal="true" aria-label={title} tabindex="-1" bind:this={panel} onkeydown={onKeydown}>
	<div class="sheet-grab" aria-hidden="true"></div>
	{#if title}
		<div class="sheet-head">
			{@render lead?.()}
			<div class="sheet-head-txt">
				<h2>{title}</h2>
				{#if sub}<div class="sub">{sub}</div>{/if}
			</div>
			<button class="icon-btn" type="button" onclick={onClose} aria-label="Fermer"><Icon name="close" /></button>
		</div>
	{/if}
	<div class="sheet-body" bind:this={bodyEl}>
		{@render children?.()}
	</div>
	{#if foot}
		{@render foot()}
	{/if}
</div>

<style>
	.sheet:focus { outline: none; }
</style>
