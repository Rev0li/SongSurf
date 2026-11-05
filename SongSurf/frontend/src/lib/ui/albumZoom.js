// Ouverture d'un album : la pochette touchée (Cover Flow ou grille) s'envole
// et se pose à sa place en haut de la page album, en grossissant ; le reste de
// la page album arrive en fondu, de haut en bas.
//
// 1. zoomFrom(coverEl, path) au clic, avant la navigation : une copie de la
//    pochette est posée tout de suite au même endroit, dans un calque fixe
//    (elle masque le changement de page).
// 2. zoomInto(heroEl, path, pageEl) quand la page album affiche sa pochette :
//    la copie vole jusqu'à elle, puis la vraie prend le relais.

let pending = null; // { path, layer, wrap, rect, radius, at }

const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function drop() {
	pending?.layer.remove();
	pending = null;
}

/** Au clic sur une pochette d'album (laisser la navigation se faire ensuite). */
export function zoomFrom(coverEl, path, event) {
	if (!coverEl || reduced()) return;
	if (event && (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button > 0)) return; // nouvel onglet…
	drop();
	const rect = coverEl.getBoundingClientRect();
	if (!rect.width) return;
	const radius = parseFloat(getComputedStyle(coverEl).borderTopLeftRadius) || 0;
	const layer = document.createElement('div');
	layer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:95;';
	const wrap = document.createElement('div');
	wrap.style.cssText = `position:fixed;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;overflow:hidden;border-radius:${radius}px;transform-origin:0 0;will-change:transform;box-shadow:0 10px 30px rgba(0,0,0,.25);`;
	const clone = coverEl.cloneNode(true);
	Object.assign(clone.style, { borderRadius: '0', opacity: '' }); // pas de width inline : Cover.svelte en dépend pour la taille des initiales
	wrap.appendChild(clone);
	layer.appendChild(wrap);
	document.body.appendChild(layer);
	pending = { path, layer, wrap, rect, radius, at: performance.now() };
	// Navigation annulée / trop lente : la copie ne reste pas en plan.
	const mine = pending;
	setTimeout(() => { if (pending === mine) drop(); }, 2000);
}

/**
 * Sur la page album : fait atterrir la copie sur `heroEl` (la pochette de la
 * page) et fait entrer `pageEls` en cascade. Sans clic préalable, ne fait rien.
 */
export function zoomInto(heroEl, path, pageEls = []) {
	if (!pending || pending.path !== path || !heroEl) return;
	const p = pending;
	pending = null;
	heroEl.style.opacity = '0';
	for (const el of pageEls) el.style.opacity = '0';

	// Deux images plus tard : la page est en place et remise en haut.
	requestAnimationFrame(() => requestAnimationFrame(() => {
		const to = heroEl.getBoundingClientRect();
		const toRadius = parseFloat(getComputedStyle(heroEl.querySelector('.cover') ?? heroEl).borderTopLeftRadius) || 16;
		const from = p.rect;
		const sx = to.width / from.width, sy = to.height / from.height;
		const dx = to.left - from.left, dy = to.top - from.top;

		const fly = p.wrap.animate([
			{ transform: 'translate(0, 0) scale(1)', borderRadius: `${p.radius}px`, boxShadow: '0 10px 30px rgba(0,0,0,.25)' },
			{ offset: 0.7, transform: `translate(${dx}px, ${dy}px) scale(${sx * 1.04}, ${sy * 1.04})`, borderRadius: `${toRadius / (sx * 1.04)}px`, boxShadow: '0 30px 60px rgba(0,0,0,.35)' },
			{ transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`, borderRadius: `${toRadius / sx}px`, boxShadow: '0 12px 30px rgba(0,0,0,.18)' },
		], { duration: 560, easing: 'cubic-bezier(.2,.75,.25,1)', fill: 'forwards' });

		// La page arrive en cascade pendant le vol.
		pageEls.forEach((el, i) => {
			el.style.opacity = '';
			el.animate([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }],
				{ duration: 380, delay: 180 + i * 45, easing: 'cubic-bezier(.2,.8,.3,1)', fill: 'backwards' });
		});

		fly.finished.catch(() => {}).then(() => {
			heroEl.style.opacity = '';
			p.layer.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120 }).finished.catch(() => {}).then(() => p.layer.remove());
		});
	}));
}
