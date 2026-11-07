<script>
	import { toasts, removeToast } from '$lib/stores.js';
</script>

<div class="toast-zone">
	{#each $toasts as toast (toast.id)}
		<!-- role=alert : annoncé par les lecteurs d'écran ; le bouton ferme le message (clic ou clavier) -->
		<div role="alert">
			<button
				type="button"
				class="alert {toast.type === 'error' ? 'alert-error' : 'alert-info'}"
				title="Fermer"
				onclick={() => removeToast(toast.id)}
			>
				{toast.message}
			</button>
		</div>
	{/each}
</div>

<style>
	.toast-zone {
		position: fixed;
		top: calc(var(--topbar-h, 56px) + 8px);
		left: 50%;
		transform: translateX(-50%);
		width: min(540px, 90vw);
		z-index: 9999;
		display: flex;
		flex-direction: column;
		gap: 8px;
		pointer-events: none;
	}
	.toast-zone .alert {
		/* bouton affiché comme l'ancien bloc */
		display: block;
		width: 100%;
		text-align: left;
		line-height: inherit;
		letter-spacing: inherit;
		pointer-events: all;
		cursor: pointer;
		animation: slideIn 0.2s ease;
		box-shadow: var(--shadow-soft);
	}
	/* Fond opaque : le toast passe au-dessus du contenu (SSF-13) */
	.toast-zone .alert-info { background: color-mix(in srgb, var(--accent) 16%, var(--bg-2)); }
	.toast-zone .alert-error { background: color-mix(in srgb, var(--red) 14%, var(--bg-2)); }
	@keyframes slideIn {
		from { opacity: 0; transform: translateY(-8px); }
		to   { opacity: 1; transform: translateY(0); }
	}
</style>
