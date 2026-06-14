<script>
	import { confirmState } from '$lib/stores.js';

	function settle(result) {
		const s = $confirmState;
		confirmState.set(null);
		s?.resolve(result);
	}

	function onKeydown(e) {
		if (!$confirmState) return;
		if (e.key === 'Escape') settle(false);
		else if (e.key === 'Enter') settle(true);
	}

	// Le message peut contenir des sauts de ligne (\n) — on les conserve.
	$: lines = $confirmState ? $confirmState.message.split('\n') : [];
</script>

<svelte:window on:keydown={onKeydown} />

{#if $confirmState}
	<div class="cm-overlay" role="presentation" on:click|self={() => settle(false)}>
		<div class="cm-card" role="alertdialog" aria-modal="true" aria-label={$confirmState.title}>
			<h3 class="cm-title">{$confirmState.title}</h3>
			<div class="cm-message">
				{#each lines as line}
					<p>{line}</p>
				{/each}
			</div>
			<div class="cm-actions">
				<button class="btn btn-ghost btn-sm" on:click={() => settle(false)}>
					{$confirmState.cancelLabel}
				</button>
				<button
					class="btn btn-sm"
					class:btn-danger={$confirmState.danger}
					class:btn-primary={!$confirmState.danger}
					on:click={() => settle(true)}
				>
					{$confirmState.confirmLabel}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.cm-overlay {
		position: fixed; inset: 0; z-index: 9500;
		display: flex; align-items: center; justify-content: center;
		background: rgba(0, 0, 0, 0.6);
		padding: var(--s4);
		backdrop-filter: blur(2px);
	}
	.cm-card {
		width: 100%; max-width: 440px;
		background: var(--bg-2);
		border: 1px solid var(--sep);
		border-radius: var(--r-xl, 16px);
		box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
		padding: var(--s5) var(--s5) var(--s4);
	}
	.cm-title { margin: 0 0 var(--s3); font-size: 18px; color: var(--text); }
	.cm-message { margin: 0 0 var(--s5); color: var(--text-2); line-height: 1.5; }
	.cm-message p { margin: 0; }
	.cm-message p:empty { height: var(--s2); }
	.cm-actions {
		display: flex; justify-content: flex-end; gap: var(--s3);
	}
</style>
