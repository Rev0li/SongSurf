// Panneaux du bas (SSF-13) : un seul ouvert à la fois, rendu par SheetHost.
// Chaque ouverture ajoute une entrée d'historique « peu profonde » (shallow
// routing) : le bouton Retour du téléphone ferme le panneau au lieu de quitter la page.
import { writable, get } from 'svelte/store';
import { goto, pushState, replaceState } from '$app/navigation';
import { page } from '$app/state';

/** { id, kind, props } | null — kind : nom du panneau dans SheetHost */
export const sheet = writable(null);

let seq = 0;

export function openSheet(kind, props = {}) {
	const id = ++seq;
	const replacing = !!get(sheet) && page.state?.sheetId != null;
	sheet.set({ id, kind, props });
	(replacing ? replaceState : pushState)('', { sheetId: id });
}

export function closeSheet() {
	const s = get(sheet);
	if (!s) return;
	if (page.state?.sheetId === s.id) history.back(); // l'effet de SheetHost vide le panneau
	else sheet.set(null);
}

/** Ferme le panneau et va ailleurs, sans laisser d'entrée « panneau » dans l'historique. */
export function closeSheetAndGo(url) {
	const hadState = page.state?.sheetId != null;
	sheet.set(null);
	return goto(url, { replaceState: hadState });
}
