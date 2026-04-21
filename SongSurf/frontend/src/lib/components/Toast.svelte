<script>
	import { toasts, removeToast } from '$lib/stores.js';
</script>

<div class="toast-zone">
	{#each $toasts as toast (toast.id)}
		<div
			class="alert {toast.type === 'error' ? 'alert-error' : 'alert-info'}"
			role="alert"
			on:click={() => removeToast(toast.id)}
		>
			{toast.message}
		</div>
	{/each}
</div>

<style>
	.toast-zone {
		position: fixed;
		top: 72px;
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
		pointer-events: all;
		cursor: pointer;
		animation: slideIn 0.2s ease;
	}
	@keyframes slideIn {
		from { opacity: 0; transform: translateY(-8px); }
		to   { opacity: 1; transform: translateY(0); }
	}
</style>
