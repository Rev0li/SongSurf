<script>
	// Pochette d'album / photo d'artiste. Sans image (204, erreur, pas d'URL) :
	// dégradé + initiales, teinte stable dérivée du nom.
	let { src = '', label = '', size = 0, round = false, radius = 10 } = $props();

	let failed = $state(false);
	let lastSrc = '';
	$effect.pre(() => {
		if (src !== lastSrc) { lastSrc = src; failed = false; }
	});

	function hue(s) {
		let h = 0;
		for (const ch of String(s)) h = (h * 31 + ch.codePointAt(0)) % 360;
		return h;
	}
	function initials(s) {
		const words = String(s).replace(/[^\p{L}\p{N} ]/gu, ' ').split(' ').filter(Boolean);
		return (words.slice(0, 2).map((w) => w[0]).join('') || '♪').toUpperCase();
	}

	let h = $derived(hue(label));
	let box = $derived(size ? `width:${size}px;height:${size}px;font-size:${Math.max(11, Math.round(size * 0.32))}px;` : '');
</script>

<div class="cover" class:round style="{box}--h:{h};border-radius:{round ? '50%' : radius + 'px'}">
	{#if src && !failed}
		<img {src} alt="" loading="lazy" decoding="async" onerror={() => (failed = true)} />
	{:else}
		<span aria-hidden="true">{initials(label)}</span>
	{/if}
</div>

<style>
	.cover {
		position: relative; flex: none; overflow: hidden; aspect-ratio: 1; width: 100%;
		display: grid; place-items: center; container-type: inline-size;
		background: linear-gradient(140deg, hsl(var(--h) 60% 72%), hsl(calc(var(--h) + 45) 50% 46%));
		color: rgba(255, 255, 255, .95); font-weight: 700; text-shadow: 0 1px 2px rgba(0, 0, 0, .2);
	}
	.cover:not([style*="width:"]) span { font-size: 30cqw; }
	img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
</style>
