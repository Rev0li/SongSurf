<script>
	import { onMount } from 'svelte';
	import { addToast } from '$lib/stores.js';

	let cryptos = [];
	let couponCode = '';
	let couponNote = '';
	let couponImage = null;
	let submitting = false;

	onMount(async () => {
		try {
			const res = await fetch('/api/donation-config', { credentials: 'same-origin' });
			const data = await res.json();
			cryptos = [
				{ symbol: 'BTC', label: '₿ Bitcoin',  address: data.btc },
				{ symbol: 'ETH', label: 'Ξ Ethereum', address: data.eth },
				{ symbol: 'SOL', label: '◎ Solana',   address: data.sol },
				{ symbol: 'XMR', label: 'ɱ Monero',   address: data.xmr },
			].filter((c) => c.address);
		} catch {
			// ignore
		}
	});

	function copyAddress(address, btn) {
		navigator.clipboard.writeText(address).then(() => {
			const orig = btn.textContent;
			btn.textContent = '✓ Copié';
			btn.classList.add('copied');
			setTimeout(() => { btn.textContent = orig; btn.classList.remove('copied'); }, 2000);
		}).catch(() => addToast('Impossible de copier.', 'error'));
	}

	async function submitCoupon(e) {
		e.preventDefault();
		if (!couponCode.trim()) { addToast('Le code coupon est requis.', 'error'); return; }
		submitting = true;
		const form = new FormData();
		form.append('coupon_code', couponCode.trim());
		if (couponNote) form.append('note', couponNote);
		if (couponImage) form.append('coupon_image', couponImage);
		try {
			const res = await fetch('/api/donation/upload-coupon', {
				method: 'POST', credentials: 'same-origin', body: form,
			});
			const data = await res.json().catch(() => ({}));
			if (res.ok && data.success) {
				addToast(data.message || 'Merci !', 'info');
				couponCode = ''; couponNote = ''; couponImage = null;
			} else {
				addToast(data.error || 'Erreur lors de l\'envoi.', 'error');
			}
		} catch {
			addToast('Impossible de contacter le serveur.', 'error');
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head><title>Donation — SongSurf</title></svelte:head>

<header class="header">
	<div class="header-brand">
		<span class="header-logo">🎵</span>
		<h1 class="header-title">SongSurf</h1>
	</div>
	<nav class="header-nav">
		<a href="/" class="btn btn-ghost btn-sm">← Dashboard</a>
	</nav>
</header>

<div class="donation-wrap">
	<div class="donation-header">
		<h1 class="donation-title">❤️ Soutenir SongSurf</h1>
		<p class="donation-subtitle">Si le service te rend service, un petit geste est toujours apprécié.</p>
	</div>

	{#if cryptos.length > 0}
		<div class="crypto-grid">
			{#each cryptos as c}
				<div class="crypto-card">
					<div class="crypto-icon">{c.symbol === 'BTC' ? '₿' : c.symbol === 'ETH' ? 'Ξ' : c.symbol === 'SOL' ? '◎' : 'ɱ'}</div>
					<div class="crypto-info">
						<div class="crypto-name">{c.label}</div>
						<div class="crypto-address">{c.address}</div>
					</div>
					<button class="crypto-copy" on:click={(e) => copyAddress(c.address, e.currentTarget)}>Copier</button>
				</div>
			{/each}
		</div>
	{/if}

	<div class="pcs-section">
		<h2 class="pcs-title">🎁 Coupon PCS / carte cadeau</h2>
		<p class="pcs-subtitle">Tu peux aussi envoyer un coupon PCS. Saisis le code et joins une photo si tu veux.</p>
		<form class="pcs-form" on:submit={submitCoupon}>
			<div class="form-group">
				<label class="form-label">Code coupon <span style="color:#ff3b6d">*</span></label>
				<input class="form-input" bind:value={couponCode} placeholder="Ex: XXXX-XXXX-XXXX-XXXX" required autocomplete="off" />
			</div>
			<div class="form-group">
				<label class="form-label">Note (optionnelle)</label>
				<input class="form-input" bind:value={couponNote} placeholder="Un mot sympa…" autocomplete="off" />
			</div>
			<div class="form-group">
				<label class="form-label">Photo du coupon (optionnelle)</label>
				<input type="file" class="form-input" accept="image/jpeg,image/png,image/webp"
					on:change={(e) => couponImage = e.currentTarget.files?.[0] ?? null} />
			</div>
			<button type="submit" class="btn btn-brand" disabled={submitting}>
				{submitting ? 'Envoi en cours…' : 'Envoyer le coupon'}
			</button>
		</form>
	</div>
</div>

<style>
	.donation-wrap { max-width: 680px; margin: 0 auto; padding: var(--space-8) var(--space-5); }
	.donation-header { text-align: center; margin-bottom: var(--space-8); }
	.donation-title { font-size: 28px; font-weight: 700; background: var(--gradient-brand); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: var(--space-2); }
	.donation-subtitle { color: var(--color-text-muted); font-size: var(--font-size-sm); }
	.crypto-grid { display: grid; gap: var(--space-4); margin-bottom: var(--space-6); }
	.crypto-card { background: var(--color-surface-1); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4) var(--space-5); display: flex; align-items: center; gap: var(--space-4); }
	.crypto-icon { font-size: 28px; flex-shrink: 0; }
	.crypto-info { flex: 1; min-width: 0; }
	.crypto-name { font-weight: 600; font-size: var(--font-size-sm); margin-bottom: 4px; }
	.crypto-address { font-family: monospace; font-size: 12px; color: var(--color-text-muted); word-break: break-all; line-height: 1.4; }
	.crypto-copy { background: none; border: 1px solid var(--color-border); color: var(--color-text-secondary); border-radius: var(--radius-md); padding: 6px 12px; cursor: pointer; font-size: 12px; white-space: nowrap; flex-shrink: 0; }
	.crypto-copy:hover { background: var(--color-surface-2); color: var(--color-text-primary); }
	.crypto-copy.copied { border-color: #4ade80; color: #4ade80; }
	.pcs-section { border-top: 1px solid var(--color-border); padding-top: var(--space-6); }
	.pcs-title { font-size: var(--font-size-lg); font-weight: 600; margin-bottom: var(--space-2); }
	.pcs-subtitle { font-size: var(--font-size-sm); color: var(--color-text-muted); margin-bottom: var(--space-4); }
	.pcs-form { display: flex; flex-direction: column; gap: var(--space-3); }
</style>
