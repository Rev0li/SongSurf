// Transition Cover Flow ⇄ grille (page artiste).
//
// Principe : on photographie chaque pochette avant le changement (snapshot), on
// bascule l'affichage, on photographie le nouvel état, puis des copies volantes
// (calque fixe au-dessus de la page) passent de l'un à l'autre. En chemin elles
// se dispersent (éclat vers l'extérieur, rotation), puis se posent. Le fond noir
// du Cover Flow s'évapore vers la grille, ou se condense au retour.
//
// Les copies volent dans une « scène » qui reproduit la perspective du Cover
// Flow : côté Cover Flow, elles partent / se posent avec la vraie transformation
// 3D de chaque pochette (inclinaison des piles comprise), donc sans saut.
//
// Repères dans le DOM : [data-morph="<chemin album>"] sur chaque pochette (son
// .cover à l'intérieur), [data-morph-panel] sur le fond noir, data-side (-1/1)
// sur les pochettes du Cover Flow (côté de la pile).

const DURATION = 820;  // vol d'une pochette (ms)
const STAGGER = 30;    // décalage entre deux pochettes (ms)
const MAX_DELAY = 420;
const BURST_AT = 0.42; // moment de l'éclat dans le vol

/** État à l'écran des pochettes et du fond noir sous `root`. */
export function snapshot(root) {
	const panelEl = root?.querySelector('[data-morph-panel]');
	let panel = null;
	if (panelEl) {
		const flowEl = panelEl.querySelector('[data-morph]')?.offsetParent;
		const fcs = flowEl && getComputedStyle(flowEl);
		panel = {
			rect: panelEl.getBoundingClientRect(),
			bg: getComputedStyle(panelEl).backgroundImage,
			stage: flowEl && { rect: flowEl.getBoundingClientRect(), perspective: fcs.perspective, origin: fcs.perspectiveOrigin },
		};
	}
	const items = new Map();
	for (const el of root?.querySelectorAll('[data-morph]') ?? []) {
		const cover = el.querySelector('.cover');
		if (!cover) continue;
		const rect = cover.getBoundingClientRect();
		let hidden = getComputedStyle(el).visibility === 'hidden' || rect.width === 0;
		if (panel && (rect.right < panel.rect.left || rect.left > panel.rect.right)) hidden = true;
		items.set(el.dataset.morph, {
			cover, rect, hidden,
			side: Number(el.dataset.side) || 0,
			radius: parseFloat(getComputedStyle(cover).borderTopLeftRadius) || 0,
			// Cover Flow : boîte avant transformation + transformation 3D
			layout: panel ? { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight } : null,
			tf: el.style.transform, filter: el.style.filter || 'none', z: Number(el.style.zIndex) || 0,
		});
	}
	return { root, panel, items };
}

// Pseudo-hasard stable par album (même dispersion à chaque fois).
function rand(key, salt) {
	let h = 2166136261 ^ salt;
	for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619);
	return ((h >>> 0) % 10000) / 10000;
}

// Carré au bord du fond noir, du côté de la pile (pochettes hors champ).
function edgeRect(panelRect, side, size) {
	const s = Math.min(size, panelRect.height * 0.6);
	const left = side < 0 ? panelRect.left - s * 0.3 : panelRect.right - s * 0.7;
	const top = panelRect.top + (panelRect.height - s) / 2 - panelRect.height * 0.1;
	return { left, top, width: s, height: s };
}

const center = (r) => [r.left + r.width / 2, r.top + r.height / 2];

/**
 * Anime le passage de `before` à `after` (deux snapshots, l'un en Cover Flow,
 * l'autre en grille). toFlow : true si on arrive sur le Cover Flow. Résout
 * quand tout est posé.
 */
export async function morph(before, after, { toFlow }) {
	const flow = toFlow ? after : before;
	const grid = toFlow ? before : after;
	if (!flow.panel?.stage) return;

	const layer = document.createElement('div');
	layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:90;';
	document.body.appendChild(layer);
	const anims = [];

	// ── Fond noir : s'évapore (vers la grille) ou se condense (vers le Cover Flow)
	const pr = flow.panel.rect;
	const ghost = document.createElement('div');
	ghost.style.cssText = `position:fixed;left:${pr.left}px;top:${pr.top}px;width:${pr.width}px;height:${pr.height}px;border-radius:20px;background-image:${flow.panel.bg};`;
	layer.appendChild(ghost);
	anims.push(ghost.animate(toFlow
		? [{ opacity: 0, transform: 'scale(.92)', filter: 'blur(10px)' }, { opacity: 1, transform: 'scale(1)', filter: 'blur(0)' }]
		: [{ opacity: 1, transform: 'scale(1)', filter: 'blur(0)' }, { opacity: 0, transform: 'scale(1.06)', filter: 'blur(12px)' }],
	{ duration: toFlow ? 560 : 720, easing: 'cubic-bezier(.3,.7,.2,1)', fill: 'forwards' }).finished);

	// ── Scène : même perspective que le Cover Flow
	const st = flow.panel.stage;
	const stage = document.createElement('div');
	stage.style.cssText = `position:fixed;left:${st.rect.left}px;top:${st.rect.top}px;width:${st.rect.width}px;height:${st.rect.height}px;perspective:${st.perspective};perspective-origin:${st.origin};`;
	layer.appendChild(stage);

	// Départ du centre du Cover Flow vers les bords ; hors champ en dernier.
	const [hx, hy] = center(pr);
	const keys = [...flow.items.keys()].filter((k) => grid.items.has(k));
	const dist = (k) => { const f = flow.items.get(k); return (f.hidden ? 1e6 : 0) + Math.abs(center(f.rect)[0] - hx); };
	keys.sort((a, b) => dist(a) - dist(b));

	// Cibles cachées pendant le vol.
	if (toFlow) after.root.querySelector('[data-morph-panel]')?.style.setProperty('opacity', '0');
	else for (const k of keys) grid.items.get(k).cover.style.opacity = '0';

	keys.forEach((k, rank) => {
		const f = flow.items.get(k), g = grid.items.get(k);
		const L = f.layout;
		if (!L?.w || !g.rect.width) { g.cover.style.opacity = ''; return; }
		const Lv = { left: st.rect.left + L.x, top: st.rect.top + L.y, width: L.w, height: L.h };
		const [lx, ly] = center(Lv);
		const box = (r) => `translate(${center(r)[0] - lx}px, ${center(r)[1] - ly}px) scale(${r.width / L.w}, ${r.height / L.h})`;

		// État côté Cover Flow (vraie 3D) et côté grille (2D).
		const edge = f.hidden ? edgeRect(pr, f.side, g.rect.width) : null;
		const flowKf = f.hidden
			? { transform: box(edge), opacity: 0, filter: 'brightness(1)', borderRadius: `${f.radius}px` }
			: { transform: f.tf, opacity: 1, filter: f.filter, borderRadius: `${f.radius}px` };
		const gridKf = { transform: box(g.rect), opacity: 1, filter: 'brightness(1)', borderRadius: `${g.radius / (g.rect.width / L.w)}px` };
		const from = toFlow ? gridKf : flowKf, to = toFlow ? flowKf : gridKf;

		// Éclat : à mi-vol, chaque pochette part vers l'extérieur et tourne.
		const [sx, sy] = center(toFlow ? g.rect : (edge ?? f.rect));
		const [ex, ey] = center(toFlow ? (edge ?? f.rect) : g.rect);
		const mx = sx + (ex - sx) * BURST_AT, my = sy + (ey - sy) * BURST_AT;
		const away = Math.hypot(mx - hx, my - hy) > 8 ? Math.atan2(my - hy, mx - hx) : rand(k, 1) * Math.PI * 2;
		const ang = away + (rand(k, 1) - 0.5) * 1.1;
		const burst = Math.min(innerWidth, 600) * (0.09 + rand(k, 2) * 0.11); // proportionné à l'écran
		const spin = (rand(k, 3) - 0.5) * 50;
		const scale = ((g.rect.width / L.w) * (toFlow ? 1 - BURST_AT : BURST_AT) + (toFlow ? BURST_AT : 1 - BURST_AT)) * 1.08;
		const midKf = {
			transform: `translate(${mx - lx + Math.cos(ang) * burst}px, ${my - ly + Math.sin(ang) * burst}px) rotate(${spin}deg) scale(${scale})`,
			opacity: 1, filter: 'brightness(1)', borderRadius: '10px',
		};

		const wrap = document.createElement('div');
		wrap.style.cssText = `position:absolute;left:${L.x}px;top:${L.y}px;width:${L.w}px;height:${L.h}px;overflow:hidden;will-change:transform,opacity;box-shadow:0 14px 34px rgba(0,0,0,.35);z-index:${f.hidden ? 0 : f.z};`;
		const clone = (f.hidden ? g.cover : (toFlow ? g.cover : f.cover)).cloneNode(true);
		Object.assign(clone.style, { borderRadius: 'inherit', opacity: '' }); // arrondi suivi par la copie elle-même (Safari) ; pas de width inline (taille des initiales)
		wrap.appendChild(clone);
		stage.appendChild(wrap);

		const anim = wrap.animate([
			{ ...from, offset: 0, easing: 'cubic-bezier(.2,.8,.3,1)' },
			{ ...midKf, offset: BURST_AT, easing: 'cubic-bezier(.5,0,.15,1)' },
			{ ...to, offset: 1 },
		], { duration: DURATION, delay: Math.min(MAX_DELAY, rank * STAGGER), fill: 'both' }); // 'both' : attend au départ pendant son délai
		anims.push(anim.finished.then(() => {
			if (!toFlow) { g.cover.style.opacity = ''; wrap.remove(); } // grille : la vraie pochette prend le relais
		}));
	});

	// Grille : les titres apparaissent pendant que les pochettes se posent.
	if (!toFlow) {
		grid.root.querySelectorAll('.tile-name, .tile-meta').forEach((el) =>
			el.animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 400, delay: 450, easing: 'ease-out', fill: 'backwards' }));
	}

	await Promise.all(anims.map((p) => p.catch(() => {})));

	if (toFlow) {
		// Le vrai Cover Flow réapparaît d'un coup, SOUS le calque (même fond, mêmes
		// places) ; seules les copies s'effacent ensuite. Un fondu croisé des deux
		// fonds ferait pâlir le noir à mi-chemin.
		after.root.querySelector('[data-morph-panel]')?.style.removeProperty('opacity');
		ghost.remove();
		await layer.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 180, easing: 'ease-out', fill: 'forwards' }).finished.catch(() => {});
	}
	layer.remove();
}
