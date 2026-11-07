// Vol de pochette entre une liste d'albums et la page album, dans les deux sens.
//
//  - Ouverture : la pochette touchée (Cover Flow, grille artiste, grille Albums)
//    grossit et se pose à sa place en haut de la page album ; le reste de la
//    page entre en cascade.
//  - Retour : la pochette de la page album revient se poser à sa place dans le
//    Cover Flow ou la grille.
//
// 1. zoomFrom(coverEl, path, event, dir) avant la navigation : une copie de la
//    pochette est posée tout de suite au même endroit, dans un calque fixe
//    (elle masque le changement de page).
// 2. land() après la navigation (routes/library/+page.svelte, afterNavigate) :
//    la copie vole jusqu'à la cible. La cible est relue à CHAQUE image :
//    remise en haut de page, restauration du défilement, barre d'adresse de
//    Safari qui se replie… la copie suit et se pose pile dessus.
//
// Cibles : [data-zoom-hero="<chemin>"] (pochette de la page album) à
// l'ouverture, [data-morph="<chemin>"] .cover (Cover Flow / grilles) au retour.

const DURATION = 580;
let pending = null; // { path, dir, layer, wrap, rect, radius }

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const ease = (t) => 1 - Math.pow(1 - t, 3);
const lerp = (a, b, t) => a + (b - a) * t;

function drop(p = pending) {
	if (!p) return;
	if (pending === p) pending = null;
	p.layer.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 150, fill: 'forwards' })
		.finished.catch(() => {}).then(() => p.layer.remove());
}

/** Avant la navigation : pose la copie de `coverEl` (un élément .cover). */
export function zoomFrom(coverEl, path, event, dir = 'open') {
	if (!coverEl || reduced()) return;
	if (event && (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button > 0)) return; // nouvel onglet…
	if (pending) { pending.layer.remove(); pending = null; }
	const rect = coverEl.getBoundingClientRect();
	if (!rect.width) return;
	const radius = parseFloat(getComputedStyle(coverEl).borderTopLeftRadius) || 0;
	const layer = document.createElement('div');
	layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:95;';
	const wrap = document.createElement('div');
	wrap.style.cssText = `position:fixed;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;overflow:hidden;border-radius:${radius}px;box-shadow:0 10px 30px rgba(0,0,0,.25);`;
	const clone = coverEl.cloneNode(true);
	// Arrondi hérité du cadre volant : la copie découpe elle-même son image (Safari ne
	// découpe pas toujours un enfant avec l'arrondi du parent). Pas de width inline :
	// Cover.svelte en dépend pour la taille des initiales.
	Object.assign(clone.style, { borderRadius: 'inherit', opacity: '' });
	// La pochette de la page album contient une 2e .cover (arrondi 16 px) : toutes
	// les couches suivent l'arrondi du cadre, sinon l'image garde ses coins d'origine.
	clone.querySelectorAll('.cover').forEach((c) => { c.style.borderRadius = 'inherit'; });
	clone.style.webkitMaskImage = '-webkit-radial-gradient(white, black)'; // Safari : force la découpe arrondie (sur la copie, pas le cadre : l'ombre resterait masquée)
	wrap.appendChild(clone);
	layer.appendChild(wrap);
	document.body.appendChild(layer);
	const p = { path, dir, layer, wrap, rect, radius };
	pending = p;
	setTimeout(() => { if (pending === p) drop(p); }, 2000); // navigation annulée / trop lente
}

function findTarget(p) {
	const attr = p.dir === 'open' ? 'zoomHero' : 'morph';
	for (const el of document.querySelectorAll(p.dir === 'open' ? '[data-zoom-hero]' : '[data-morph]')) {
		if (el.dataset[attr] !== p.path) continue;
		const cover = el.matches('.cover') ? el : el.querySelector('.cover');
		const r = cover?.getBoundingClientRect();
		if (r?.width && getComputedStyle(el).visibility !== 'hidden') return cover;
	}
	return null;
}

/** Après la navigation : fait voler la copie en attente jusqu'à sa cible. */
export function land() {
	const p = pending;
	if (!p) return;
	pending = null;
	const target = findTarget(p);
	if (!target) { drop(p); return; } // cible absente (autre onglet de « Ma musique »…) : la copie s'efface
	target.style.opacity = '0';

	// Ouverture : la page album entre en cascade pendant le vol.
	if (p.dir === 'open') {
		document.querySelectorAll('.hero > :not([data-zoom-hero]), .rows > li:nth-child(-n+12), .tip').forEach((el, i) =>
			el.animate([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }],
				{ duration: 380, delay: 160 + i * 45, easing: 'cubic-bezier(.2,.8,.3,1)', fill: 'backwards' }));
	}

	const toRadius = parseFloat(getComputedStyle(target).borderTopLeftRadius) || 0;
	const from = p.rect;
	const [fx, fy] = [from.left + from.width / 2, from.top + from.height / 2];
	const t0 = performance.now();
	const step = (now) => {
		const t = Math.min(1, (now - t0) / DURATION), e = ease(t);
		const to = target.getBoundingClientRect(); // relue à chaque image
		const bump = 1 + 0.06 * Math.sin(Math.PI * e); // léger gonflement en vol
		const w = lerp(from.width, to.width, e) * bump, h = lerp(from.height, to.height, e) * bump;
		const cx = lerp(fx, to.left + to.width / 2, e), cy = lerp(fy, to.top + to.height / 2, e);
		Object.assign(p.wrap.style, {
			left: `${cx - w / 2}px`, top: `${cy - h / 2}px`, width: `${w}px`, height: `${h}px`,
			borderRadius: `${lerp(p.radius, toRadius, e)}px`,
			boxShadow: `0 ${10 + 22 * Math.sin(Math.PI * e)}px ${30 + 30 * Math.sin(Math.PI * e)}px rgba(0,0,0,${0.25 + 0.1 * Math.sin(Math.PI * e)})`,
		});
		if (t < 1) { requestAnimationFrame(step); return; }
		target.style.opacity = '';
		p.layer.remove();
	};
	requestAnimationFrame(step);
}
