<script module>
	// Album de face par artiste : au retour d'une page album, on reprend au même endroit.
	const lastIndex = new Map();
</script>

<script>
	// Cover Flow (page artiste), façon iPod : pochette de face au centre, les
	// autres en deux piles inclinées à gauche et à droite, reflets sur fond noir.
	// Défilement horizontal natif (doigt, pavé tactile, élan, aimantation par
	// album) ; la molette verticale avance d'un album ; flèches au clavier.
	// La position de défilement pilote la 3D. Toucher la pochette de face ouvre
	// l'album, une autre la ramène au centre.
	import { onMount } from 'svelte';
	import { albumUrl, coverUrl, plural } from '$lib/library/data.js';
	import Cover from '../ui/Cover.svelte';
	import Icon from '../ui/Icon.svelte';

	let { artistPath, albums, todoSet } = $props();

	const SLOT = 72; // défilement (px) pour passer d'un album au suivant

	let scroller = $state();
	let width = $state(0);
	let items = $state([]);
	let pos = $state(0);
	let raf = 0;

	let current = $derived(Math.min(albums.length - 1, Math.max(0, Math.round(pos))));
	let shown = $derived(albums[current]);

	function onScroll() {
		if (raf) return;
		raf = requestAnimationFrame(() => {
			raf = 0;
			pos = scroller.scrollLeft / SLOT;
			lastIndex.set(artistPath, Math.round(pos));
		});
	}

	function go(i, focus = false) {
		const n = Math.min(albums.length - 1, Math.max(0, i));
		const smooth = !matchMedia('(prefers-reduced-motion: reduce)').matches;
		scroller.scrollTo({ left: n * SLOT, behavior: smooth ? 'smooth' : 'auto' });
		if (focus) items[n]?.focus({ preventScroll: true }); // clavier seulement
		return n;
	}

	// Molette verticale (souris) : un cran = un album. Aux extrémités, la page
	// reprend la main pour ne pas bloquer le défilement.
	let wheelAt = 0, target = 0;
	function onWheel(e) {
		if (Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return; // pavé tactile horizontal : natif
		const dir = Math.sign(e.deltaY);
		const from = Date.now() - wheelAt < 400 ? target : current;
		if ((dir < 0 && from <= 0) || (dir > 0 && from >= albums.length - 1)) return;
		e.preventDefault();
		if (Date.now() - wheelAt < 140) return;
		wheelAt = Date.now();
		target = go(from + dir);
	}

	onMount(() => {
		const i = lastIndex.get(artistPath) ?? 0;
		if (i > 0) { scroller.scrollLeft = i * SLOT; pos = i; }
		scroller.addEventListener('wheel', onWheel, { passive: false });
		return () => { cancelAnimationFrame(raf); scroller.removeEventListener('wheel', onWheel); };
	});

	// d = écart au centre en albums (négatif = à gauche). Pochette de face pour
	// d = 0 ; les autres forment deux piles : même angle, même profondeur, pas
	// constant. En défilant, une pochette quitte sa pile, se redresse au centre
	// puis rejoint l'autre pile.
	const GAP = 66;    // décalage de la 1re pochette de chaque pile (% de sa largeur)
	const STEP = 13;   // pas entre deux pochettes d'une même pile (%)
	const TILT = 70;   // inclinaison des piles (degrés)
	const DEPTH = 150; // recul des piles (px)
	function place(i, p) {
		const d = i - p, a = Math.abs(d), s = Math.sign(d);
		if (a > 9.5) return 'visibility:hidden';
		const t = Math.min(a, 1), far = Math.max(0, a - 1);
		const x = s * (t * GAP + far * STEP);
		const z = -t * DEPTH;
		const r = s * Math.min(1, a / 0.6) * TILT; // bascule franche : seule celle du centre est de face
		const dim = 1 - t * 0.15 - Math.min(far, 5) * 0.04;
		return `transform:translateX(${x}%) translateZ(${z}px) rotateY(${r}deg);z-index:${100 - Math.round(a * 10)};filter:brightness(${dim})`;
	}

	function onClick(e, i) {
		if (i !== current) { e.preventDefault(); go(i); }
	}
	function onKey(e) {
		if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); go(current + 1, true); }
		else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); go(current - 1, true); }
	}
</script>

<div class="cf">
	<div class="flow" bind:this={scroller} bind:clientWidth={width} onscroll={onScroll}>
		<div class="rail" style="--sw:{width}px">
			<div class="stage">
				{#each albums as album, i (album.path)}
					<a class="item" href={albumUrl(album.path)} style={place(i, pos)} bind:this={items[i]}
						tabindex={i === current ? 0 : -1} aria-label="{album.name}, {plural(album.songs?.length ?? 0, 'titre')}"
						onclick={(e) => onClick(e, i)} onkeydown={onKey}>
						<Cover src={coverUrl(album.path)} label={album.name} radius={4} />
					</a>
				{/each}
			</div>
			{#each albums as album (album.path)}<div class="snap" aria-hidden="true"></div>{/each}
			<div class="tail" aria-hidden="true"></div>
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
	.cf {
		--w: min(240px, 44vw);
		display: flex; flex-direction: column; gap: 4px; padding-bottom: 14px;
		border-radius: 20px; overflow: hidden; color: #fff;
		background: radial-gradient(120% 90% at 50% 35%, #2a2a2a 0%, #0b0b0b 60%, #000 100%);
	}
	.flow {
		height: calc(var(--w) * 1.42); overflow-x: auto; overflow-y: hidden;
		scroll-snap-type: x mandatory; scrollbar-width: none; overscroll-behavior-x: contain;
		mask-image: linear-gradient(to right, transparent, #000 8%, #000 92%, transparent);
	}
	.flow::-webkit-scrollbar { display: none; }
	.rail { display: flex; height: 100%; width: max-content; }
	.stage {
		flex: none; width: var(--sw); height: 100%; margin-right: calc(var(--sw) * -1);
		position: sticky; left: 0; perspective: 900px; perspective-origin: 50% 40%;
	}
	.item {
		position: absolute; left: 50%; top: calc(var(--w) * 0.12); width: var(--w);
		margin-left: calc(var(--w) / -2); border-radius: 4px; text-decoration: none; will-change: transform;
		-webkit-box-reflect: below 2px linear-gradient(transparent, transparent 62%, rgba(255, 255, 255, .32));
		-webkit-tap-highlight-color: transparent;
	}
	.item:focus-visible { outline: 3px solid var(--primary); outline-offset: 3px; }
	.snap { flex: none; width: 72px; scroll-snap-align: start; }
	.tail { flex: none; width: calc(var(--sw) - 72px); }
	.caption { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 2px; padding: 0 var(--s4); min-height: 40px; }
	.name { font-weight: 700; font-size: 15px; display: inline-flex; align-items: center; gap: 6px; overflow-wrap: anywhere; }
	.meta { font-size: 12.5px; color: rgba(255, 255, 255, .6); }
	.badge { width: 20px; height: 20px; border-radius: 50%; display: inline-grid; place-items: center; background: var(--orange); color: #111; flex: none; }
	@media (min-width: 900px) { .cf { --w: 240px; } }
</style>
