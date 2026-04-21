<script>
	import { onMount, onDestroy } from 'svelte';

	let warned = false;
	let graceRemaining = 0;
	let forceStopIn = 0;
	let interval;

	async function poll() {
		try {
			const res = await fetch('/watcher/inactivity-status', { credentials: 'same-origin' });
			if (!res.ok) return;
			const data = await res.json();
			warned = !!data.warned;
			graceRemaining = data.grace_remaining_seconds ?? 0;
			forceStopIn = data.force_stop_in_seconds ?? 0;
		} catch {
			// ignore
		}
	}

	async function keepalive() {
		try {
			await fetch('/watcher/keepalive', { method: 'POST', credentials: 'same-origin' });
			warned = false;
		} catch {
			// ignore
		}
	}

	onMount(() => {
		poll();
		interval = setInterval(poll, 30_000);
	});

	onDestroy(() => clearInterval(interval));
</script>

{#if warned}
	<div class="inactivity-banner">
		<span>
			⌛ Inactivité détectée — arrêt automatique dans
			<strong>{Math.ceil(graceRemaining / 60)} min</strong>
		</span>
		<button class="btn btn-sm btn-primary" on:click={keepalive}>
			Rester actif
		</button>
	</div>
{/if}

<style>
	.inactivity-banner {
		position: fixed;
		bottom: 16px;
		left: 50%;
		transform: translateX(-50%);
		background: var(--color-warning, #b45309);
		color: #fff;
		padding: 10px 20px;
		border-radius: var(--radius-lg, 8px);
		display: flex;
		align-items: center;
		gap: 16px;
		z-index: 8000;
		box-shadow: 0 4px 16px rgba(0,0,0,0.4);
		font-size: 14px;
	}
</style>
