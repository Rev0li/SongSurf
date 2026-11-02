<script>
	import { confirmState } from '$lib/stores.js';

	function settle(result) {
		const s = $confirmState;
		confirmState.set(null);
		s?.resolve(result);
	}

	function onKeydown(e) {
		if (!$confirmState || (e.key !== 'Enter' && e.key !== 'Escape')) return;
		// La frappe qui a ouvert la modal (même événement, ex. Entrée dans un champ) et
		// la répétition d'une touche maintenue ne confirment ni n'annulent rien.
		if (e.repeat || e.timeStamp <= $confirmState.openedAt) { e.preventDefault(); return; }
		// Entrée sur un bouton de la modal : c'est le bouton qui décide (Annuler ou confirmer).
		if (e.key === 'Enter' && e.target?.closest?.('.cm-card button')) return;
		e.preventDefault();
		settle(e.key === 'Enter');
	}

	// Focus : à l'ouverture sur « Confirmer » — ou sur « Annuler » pour une action
	// destructive (danger), pour qu'un Entrée réflexe ne supprime rien. Le champ d'origine
	// ne reçoit plus les frappes ; il retrouve le focus à la fermeture.
	let confirmBtn = $state();
	let cancelBtn = $state();
	let returnFocus = null;
	$effect(() => {
		if ($confirmState) {
			if (!returnFocus) returnFocus = document.activeElement;
			// Après la fin de la frappe en cours : sinon la même touche Entrée
			// « cliquerait » le bouton qui vient de recevoir le focus.
			const btn = $confirmState.danger ? cancelBtn : confirmBtn;
			setTimeout(() => btn?.focus());
		} else if (returnFocus) {
			returnFocus.focus?.();
			returnFocus = null;
		}
	});

	// Le message peut contenir des sauts de ligne (\n) — on les conserve.
	let lines = $derived($confirmState ? $confirmState.message.split('\n') : []);
</script>

<svelte:window onkeydown={onKeydown} />

{#if $confirmState}
	<div class="cm-overlay" role="presentation" onclick={(e) => { if (e.target === e.currentTarget) settle(false); }}>
		<div class="cm-card" role="alertdialog" aria-modal="true" aria-label={$confirmState.title}>
			<h3 class="cm-title">{$confirmState.title}</h3>
			<div class="cm-message">
				{#each lines as line}
					<p>{line}</p>
				{/each}
			</div>
			<div class="cm-actions">
				<button bind:this={cancelBtn} class="btn btn-ghost btn-sm" onclick={() => settle(false)}>
					{$confirmState.cancelLabel}
				</button>
				<button
					bind:this={confirmBtn}
					class="btn btn-sm"
					class:btn-danger={$confirmState.danger}
					class:btn-primary={!$confirmState.danger}
					onclick={() => settle(true)}
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
