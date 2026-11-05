<script module>
	// Album de face par artiste : au retour d'une page album, on reprend au même endroit.
	const lastIndex = new Map();
</script>

<script>
	// Cover Flow (page artiste), façon iPod : pochette de face au centre, les
	// autres en deux piles inclinées à gauche et à droite, reflets sur fond noir.
	//
	// Mouvement « surf » : pas de défilement natif aimanté (trop sec). On glisse
	// librement (doigt, souris, pavé tactile, molette), l'élan continue puis
	// s'arrête où il veut ; seulement après 2,5 s sans geste, la pochette la plus
	// visible revient doucement au centre. Toucher la pochette de face ouvre l'album, une autre
	// la ramène doucement au centre. Glisser verticalement fait défiler la page.
	import { onMount, untrack } from 'svelte';
	import { albumUrl, coverUrl, plural } from '$lib/library/data.js';
	import Cover from '../ui/Cover.svelte';
	import Icon from '../ui/Icon.svelte';
	import { zoomFrom } from '$lib/ui/albumZoom.js';

	let { artistPath, albums, todoSet } = $props();

	// Réglages du mouvement
	const DRAG_PX = 90;      // glisser de 90 px = un album
	const WHEEL_PX = 140;    // molette / pavé tactile : 140 px = un album
	const GLIDE_TAU = 0.8;   // élan : la vitesse est divisée par e toutes les 0,8 s…
	const GLIDE_DECEL = 1.2; // …plus un léger freinage (album/s²) pour finir par s'arrêter
	const RECENTER_MS = 2500; // immobile depuis 2,5 s → recentre la pochette la plus visible
	const SPRING_W = 4;      // recentrage doux (amorti critique, ~1,2 s)
	const RUBBER = 0.35;     // résistance au-delà du premier / dernier album

	// Disposition des piles
	const GAP = 70;    // décalage de la 1re pochette de chaque pile (% de sa largeur)
	const STEP = 12;   // pas entre deux pochettes d'une même pile (%)
	const TILT = 55;   // inclinaison des piles (degrés) : vue de trois quarts
	const DEPTH = 230; // recul des piles (px) : le bord avant reste plus petit que la pochette de face

	let pos = $state(untrack(() => lastIndex.get(artistPath) ?? 0)); // composant recréé à chaque artiste ({#key})
	let items = $state([]);
	let last = $derived(albums.length - 1);
	let current = $derived(Math.min(last, Math.max(0, Math.round(pos))));
	let shown = $derived(albums[current]);

	// ── Moteur ───────────────────────────────────────────────────────────────
	// 'idle' (immobile) | 'drag' (au doigt) | 'glide' (élan libre) | 'wheel'
	// (molette) | 'settle' (recentrage). Aucun aimant pendant le mouvement : le
	// flot s'arrête où l'élan le mène, et ce n'est qu'après RECENTER_MS sans
	// geste que la pochette la plus visible revient doucement au centre.
	let mode = 'idle', v = 0, target = 0, raf = 0, tPrev = 0, recenter = 0;
	let wheelGoal = 0, wheelAt = 0;

	const clamp = (x) => Math.min(last, Math.max(0, x));

	function kick() {
		if (!raf) { tPrev = performance.now(); raf = requestAnimationFrame(frame); }
	}

	function settle(to) {
		clearTimeout(recenter);
		target = clamp(to);
		mode = 'settle';
		kick();
	}

	function rest() {
		mode = 'idle'; v = 0;
		lastIndex.set(artistPath, clamp(Math.round(pos)));
		clearTimeout(recenter);
		if (Math.abs(pos - Math.round(pos)) > 0.002) {
			recenter = setTimeout(() => { if (mode === 'idle') settle(Math.round(pos)); }, RECENTER_MS);
		}
	}

	function interrupt() {
		clearTimeout(recenter);
	}

	// Avance la physique par petits pas (1/120 s) : même mouvement quel que soit
	// le nombre d'images par seconde de l'appareil.
	function frame(now) {
		let left = Math.min(0.25, (now - tPrev) / 1000);
		tPrev = now;
		raf = 0;
		while (left > 0 && mode !== 'idle' && mode !== 'drag') {
			const dt = Math.min(left, 1 / 120);
			left -= dt;
			step(dt, now);
		}
		if (mode !== 'idle' && mode !== 'drag') raf = requestAnimationFrame(frame);
	}

	function step(dt, now) {
		if (mode === 'glide') {
			pos += v * dt;
			v *= Math.exp(-dt / GLIDE_TAU);
			const brake = GLIDE_DECEL * dt;
			v = Math.abs(v) <= brake ? 0 : v - Math.sign(v) * brake;
			if (pos < 0 || pos > last) settle(pos < 0 ? 0 : last); // bord : on revient dans la liste
			else if (v === 0) rest();
		} else if (mode === 'wheel') {
			pos += (wheelGoal - pos) * (1 - Math.exp(-dt / 0.12));
			if (now - wheelAt > 200 && Math.abs(wheelGoal - pos) < 0.002) { pos = wheelGoal; rest(); }
		} else if (mode === 'settle') {
			const acc = -SPRING_W * SPRING_W * (pos - target) - 2 * SPRING_W * v;
			v += acc * dt;
			pos += v * dt;
			if (Math.abs(pos - target) < 0.002 && Math.abs(v) < 0.02) { pos = target; rest(); }
		}
	}

	// ── Glisser (doigt ou souris) ────────────────────────────────────────────
	let flow = $state();
	let drag = null; // { id, x0, p0, moved, samples }
	let dragEnd = 0; // fin du dernier glisser : le « clic » qui suit n'ouvre rien

	function rubber(p) {
		if (p < 0) return p * RUBBER;
		if (p > last) return last + (p - last) * RUBBER;
		return p;
	}

	function onDown(e) {
		if (e.pointerType === 'mouse' && e.button !== 0) return;
		interrupt();
		drag = { id: e.pointerId, x0: e.clientX, p0: pos, moved: false, samples: [[e.timeStamp, pos]], caught: mode !== 'idle' };
		if (mode !== 'idle') { mode = 'drag'; v = 0; } // on attrape le flot en vol
	}

	function onMove(e) {
		if (!drag || e.pointerId !== drag.id) return;
		const dx = e.clientX - drag.x0;
		if (!drag.moved) {
			if (Math.abs(dx) < 6) return;
			drag.moved = true;
			mode = 'drag';
			flow.setPointerCapture(e.pointerId);
		}
		pos = rubber(drag.p0 - dx / DRAG_PX);
		drag.samples.push([e.timeStamp, pos]);
		if (drag.samples.length > 6) drag.samples.shift();
	}

	function onUp(e) {
		if (!drag || e.pointerId !== drag.id) return;
		const { samples: s, moved, caught } = drag;
		drag = null;
		if (moved) dragEnd = performance.now();
		if (!moved) {
			if (caught) { dragEnd = performance.now(); pos < 0 || pos > last ? settle(pos < 0 ? 0 : last) : rest(); } // attrapé en vol : il reste là
			return;
		}
		// vitesse au lâcher, sur les ~80 dernières ms
		const [t1, p1] = s[s.length - 1];
		let k = s.length - 1;
		while (k > 0 && t1 - s[k - 1][0] < 80) k--;
		const [t0, p0] = s[k];
		v = t1 > t0 ? ((p1 - p0) / (t1 - t0)) * 1000 : 0;
		v = Math.max(-18, Math.min(18, v));
		mode = 'glide';
		kick();
	}

	// ── Molette / pavé tactile ───────────────────────────────────────────────
	function onWheel(e) {
		const horiz = Math.abs(e.deltaX) > Math.abs(e.deltaY);
		const delta = horiz ? e.deltaX : e.deltaY;
		const scale = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? 400 : 1;
		// Molette verticale aux extrémités : la page reprend la main.
		if (!horiz && mode === 'idle' && ((delta < 0 && pos <= 0) || (delta > 0 && pos >= last))) return;
		e.preventDefault();
		interrupt();
		if (mode !== 'wheel') { wheelGoal = pos; v = 0; mode = 'wheel'; }
		wheelGoal = clamp(wheelGoal + (delta * scale) / WHEEL_PX);
		wheelAt = performance.now();
		kick();
	}

	onMount(() => {
		flow.addEventListener('wheel', onWheel, { passive: false });
		return () => { cancelAnimationFrame(raf); clearTimeout(recenter); flow.removeEventListener('wheel', onWheel); };
	});

	// ── Disposition 3D ───────────────────────────────────────────────────────
	// d = écart au centre en albums (négatif = à gauche). De face pour d = 0 ;
	// au-delà de 1, deux piles parallèles à pas constant. Entre 0 et 1, la
	// pochette se décale, recule et pivote ensemble (pas de collision au centre).
	function place(i, p) {
		const d = i - p, a = Math.abs(d), s = Math.sign(d);
		if (a > 9.5) return 'visibility:hidden';
		const t = Math.min(a, 1), far = Math.max(0, a - 1);
		const ease = t * t * (3 - 2 * t);  // pivot et recul : départ et arrivée en douceur
		const slide = 1 - (1 - t) * (1 - t); // glissement en avance sur le pivot : le centre se libère
		const x = s * (slide * GAP + far * STEP);
		const z = -ease * DEPTH;
		// Chaque pile regarde le centre : bord extérieur en avant, bord intérieur
		// en retrait derrière la pochette de face (gauche : rotateY +, droite : −).
		const r = -s * ease * TILT;
		const dim = 1 - ease * 0.15 - Math.min(far, 5) * 0.04;
		return `transform:translateX(${x}%) translateZ(${z}px) rotateY(${r}deg);z-index:${1000 - Math.round(a * 100)};filter:brightness(${dim})`;
	}

	function onClick(e, i) {
		if (performance.now() - dragEnd < 300) { e.preventDefault(); return; }
		if (i !== current || mode !== 'idle') { e.preventDefault(); settle(i); return; } // une autre pochette : elle vient au centre
		zoomFrom(items[i]?.querySelector('.cover'), albums[i].path, e); // pochette de face : elle s'envole vers la page album
	}
	function onKey(e) {
		const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
		if (!step) return;
		e.preventDefault();
		interrupt();
		const to = clamp((mode === 'settle' ? target : current) + step);
		settle(to);
		items[to]?.focus({ preventScroll: true });
	}
</script>

<div class="cf" data-morph-panel>
	<!-- Glisser à la souris / au doigt ; le clavier est géré sur chaque pochette. -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="flow" bind:this={flow}
		onpointerdown={onDown} onpointermove={onMove} onpointerup={onUp} onpointercancel={onUp}
		ondragstart={(e) => e.preventDefault()}>
		{#each albums as album, i (album.path)}
			<a class="item" href={albumUrl(album.path)} style={place(i, pos)} data-morph={album.path} data-side={i < current ? -1 : 1} bind:this={items[i]} draggable="false"
				tabindex={i === current ? 0 : -1} aria-label="{album.name}, {plural(album.songs?.length ?? 0, 'titre')}"
				onclick={(e) => onClick(e, i)} onkeydown={onKey}>
				<Cover src={coverUrl(album.path)} label={album.name} radius={4} />
			</a>
		{/each}
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
		--w: min(240px, 36vw);
		display: flex; flex-direction: column; gap: 4px; padding-bottom: 14px;
		border-radius: 20px; overflow: hidden; color: #fff;
		background: radial-gradient(120% 90% at 50% 35%, #2a2a2a 0%, #0b0b0b 60%, #000 100%);
	}
	.flow {
		position: relative; height: calc(var(--w) * 1.42); overflow: hidden;
		perspective: 900px; perspective-origin: 50% 40%;
		touch-action: pan-y; user-select: none; -webkit-user-select: none; cursor: grab;
		mask-image: linear-gradient(to right, transparent, #000 8%, #000 92%, transparent);
	}
	.flow:active { cursor: grabbing; }
	.item {
		position: absolute; left: 50%; top: calc(var(--w) * 0.12); width: var(--w);
		margin-left: calc(var(--w) / -2); border-radius: 4px; text-decoration: none; will-change: transform;
		-webkit-box-reflect: below 2px linear-gradient(transparent, transparent 62%, rgba(255, 255, 255, .32));
		-webkit-tap-highlight-color: transparent; -webkit-user-drag: none;
		/* Bords nets quand la pochette est inclinée (anticrénelage des plans 3D). */
		backface-visibility: hidden; -webkit-backface-visibility: hidden; outline: 1px solid transparent;
	}
	/* Safari : pendant le mouvement (calque composité), l'arrondi + overflow:hidden
	   ne découpe plus l'image et les coins clignotent carrés. Le masque force la
	   découpe sur la pochette elle-même, en mouvement comme à l'arrêt. */
	.item :global(.cover) {
		-webkit-mask-image: -webkit-radial-gradient(white, black);
		mask-image: radial-gradient(white, black);
		isolation: isolate;
	}
	.item :global(img) { -webkit-user-drag: none; pointer-events: none; }
	.item:focus-visible { outline: 3px solid var(--primary); outline-offset: 3px; }
	.caption { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 2px; padding: 0 var(--s4); min-height: 40px; }
	.name { font-weight: 700; font-size: 15px; display: inline-flex; align-items: center; gap: 6px; overflow-wrap: anywhere; }
	.meta { font-size: 12.5px; color: rgba(255, 255, 255, .6); }
	.badge { width: 20px; height: 20px; border-radius: 50%; display: inline-grid; place-items: center; background: var(--orange); color: #111; flex: none; }
	@media (min-width: 900px) { .cf { --w: 240px; } }
</style>
