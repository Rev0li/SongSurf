<script module>
	// Album de face par artiste : au retour d'une page album, on reprend au même endroit.
	const lastIndex = new Map();
</script>

<script>
	// Cover Flow vertical (page artiste) : les pochettes s'empilent en 3D au-dessus
	// et en dessous de celle de face. Le défilement est natif (doigt, molette,
	// élan, aimantation par album) ; la position de défilement pilote la 3D.
	// Toucher la pochette de face ouvre l'album, une autre la ramène au centre.
	import { albumUrl, coverUrl, plural } from '$lib/library/data.js';
	import Cover from '../ui/Cover.svelte';
	import Icon from '../ui/Icon.svelte';

	import { onMount } from 'svelte';

	let { artistPath, albums, todoSet } = $props();

	const SLOT = 84; // défilement (px) pour passer d'un album au suivant

	let scroller = $state();
	let items = $state([]);
	let pos = $state(0);
	let raf = 0;

	let current = $derived(Math.min(albums.length - 1, Math.max(0, Math.round(pos))));
	let shown = $derived(albums[current]);

	function onScroll() {
		if (raf) return;
		raf = requestAnimationFrame(() => {
			raf = 0;
			pos = scroller.scrollTop / SLOT;
			lastIndex.set(artistPath, Math.round(pos));
		});
	}

	onMount(() => {
		const i = lastIndex.get(artistPath) ?? 0;
		if (i > 0) { scroller.scrollTop = i * SLOT; pos = i; }
		return () => cancelAnimationFrame(raf);
	});

	function go(i) {
		const n = Math.min(albums.length - 1, Math.max(0, i));
		const smooth = !matchMedia('(prefers-reduced-motion: reduce)').matches;
		scroller.scrollTo({ top: n * SLOT, behavior: smooth ? 'smooth' : 'auto' });
		items[n]?.focus({ preventScroll: true });
	}

	// d = écart au centre en albums (négatif = au-dessus). Pochette de face pour
	// d = 0 ; les autres forment deux piles : toutes au même angle et à la même
	// profondeur, serrées à pas constant (pas de courbe « roue »). En défilant,
	// une pochette quitte sa pile, se redresse au centre puis rejoint l'autre pile.
	const GAP = 72;   // décalage de la 1re pochette de chaque pile (% de sa hauteur)
	const STEP = 11;  // pas entre deux pochettes d'une même pile (%)
	const TILT = 68;  // inclinaison des piles (degrés)
	const DEPTH = 170; // recul des piles (px)
	function place(i, p) {
		const d = i - p, a = Math.abs(d), s = Math.sign(d);
		if (a > 8.5) return 'visibility:hidden';
		const t = Math.min(a, 1), far = Math.max(0, a - 1);
		const y = s * (t * GAP + far * STEP);
		const z = -t * DEPTH;
		const r = -s * Math.min(1, a / 0.6) * TILT; // bascule franche : seule celle du centre est de face
		const dim = 1 - t * 0.12 - Math.min(far, 5) * 0.03;
		return `transform:translateY(${y}%) translateZ(${z}px) rotateX(${r}deg);z-index:${100 - Math.round(a * 10)};filter:brightness(${dim})`;
	}

	function onClick(e, i) {
		if (i !== current) { e.preventDefault(); go(i); }
	}
	function onKey(e) {
		if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); go(current + 1); }
		else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); go(current - 1); }
	}
</script>

<div class="cf">
	<div class="flow" bind:this={scroller} onscroll={onScroll}>
		<div class="stage">
			{#each albums as album, i (album.path)}
				<a class="item" href={albumUrl(album.path)} style={place(i, pos)} bind:this={items[i]}
					tabindex={i === current ? 0 : -1} aria-label="{album.name}, {plural(album.songs?.length ?? 0, 'titre')}"
					onclick={(e) => onClick(e, i)} onkeydown={onKey}>
					<Cover src={coverUrl(album.path)} label={album.name} radius={12} />
				</a>
			{/each}
		</div>
		<div aria-hidden="true">
			{#each albums as album (album.path)}<div class="snap"></div>{/each}
			<div class="tail"></div>
		</div>
	</div>

	{#if shown}
		<div class="caption" aria-live="polite">
			<span class="name">
				{#if todoSet.has(shown.path)}<span class="badge" title="Infos à compléter"><Icon name="warn" size={12} /></span>{/if}
				{shown.name}
			</span>
			<span class="meta">{plural(shown.songs?.length ?? 0, 'titre')} · {current + 1} / {albums.length}</span>
		</div>
	{/if}
</div>

<style>
	.cf { --w: min(220px, 56vw); --h: calc(var(--w) * 2.2); display: flex; flex-direction: column; gap: var(--s3); }
	.flow {
		position: relative; height: var(--h); overflow-y: auto; overscroll-behavior-y: auto;
		scroll-snap-type: y mandatory; scrollbar-width: none;
		mask-image: linear-gradient(transparent, #000 12%, #000 88%, transparent);
	}
	.flow::-webkit-scrollbar { display: none; }
	.stage { position: sticky; top: 0; height: var(--h); margin-bottom: calc(var(--h) * -1); perspective: 1000px; }
	.item {
		position: absolute; left: 50%; top: 50%; width: var(--w);
		margin: calc(var(--w) / -2) 0 0 calc(var(--w) / -2);
		border-radius: 12px; text-decoration: none; box-shadow: 0 12px 28px rgba(0, 0, 0, .28); will-change: transform;
		-webkit-tap-highlight-color: transparent;
	}
	.item:focus-visible { outline: 3px solid var(--primary); outline-offset: 3px; }
	.snap { height: 84px; scroll-snap-align: start; }
	.tail { height: calc(var(--h) - 84px); }
	.caption { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 2px; min-height: 42px; }
	.name { font-weight: 700; font-size: 16px; display: inline-flex; align-items: center; gap: 6px; overflow-wrap: anywhere; }
	.meta { font-size: 13px; color: var(--text-2); }
	.badge { width: 20px; height: 20px; border-radius: 50%; display: inline-grid; place-items: center; background: var(--orange); color: #111; flex: none; }
</style>
