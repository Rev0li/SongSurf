<script>
	// Ligne de titre : toucher = « Modifier les infos », « ⋯ » = actions.
	import Icon from '../ui/Icon.svelte';
	import Cover from '../ui/Cover.svelte';

	let { title, sub = '', num = null, coverSrc = '', coverLabel = '', missing = [], onOpen, onMenu } = $props();
</script>

<li class="row">
	<button type="button" class="row-main" onclick={onOpen}>
		{#if num !== null}
			<span class="row-num">{num}</span>
		{:else}
			<Cover src={coverSrc} label={coverLabel || title} size={44} radius={8} />
		{/if}
		<span class="row-txt">
			<span class="row-t">
				<span>{title}</span>
				{#if missing.length}
					<span class="warnmark" title="À compléter : {missing.join(', ')}"><Icon name="warn" size={16} /></span>
				{/if}
			</span>
			{#if sub}<span class="row-s">{sub}</span>{/if}
		</span>
	</button>
	<button type="button" class="icon-btn" onclick={onMenu} aria-label="Actions pour {title}"><Icon name="more" /></button>
</li>
