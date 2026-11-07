// Menus « ⋯ » et actions de « Ma musique » (SSF-13). Les outils experts
// (numérotation, audit iTunes, genre de l'artiste, suppression) sont réservés à l'admin.
import { get } from 'svelte/store';
import { goto } from '$app/navigation';
import { api } from '$lib/api.js';
import { user, addToast, confirmAction } from '$lib/stores.js';
import { openSheet } from '$lib/ui/sheets.js';
import {
	tree, refreshLibrary, bumpImgVersion, findAlbum, findArtist, parentPath,
	artistUrl, LIBRARY_URL, coverUrl, pictureUrl, plural, countSongs,
} from './data.js';

export const isAdmin = () => get(user)?.role === 'admin';

/** Ouvre le sélecteur de fichiers (à appeler pendant un clic). */
export function pickImage() {
	return new Promise((resolve) => {
		const input = document.createElement('input');
		input.type = 'file';
		input.accept = 'image/*';
		input.onchange = () => resolve(input.files?.[0] ?? null);
		input.click();
	});
}

export async function changeAlbumCover(albumPath, file) {
	if (!file) return;
	try {
		await api.uploadAlbumCover(albumPath, file);
		bumpImgVersion(albumPath);
		addToast('Pochette mise à jour.', 'info');
	} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
}

export async function changeArtistPicture(artistPath, file) {
	if (!file) return;
	try {
		await api.uploadArtistCover(artistPath, file);
		bumpImgVersion(artistPath);
		await refreshLibrary(); // has_picture
		addToast('Photo mise à jour.', 'info');
	} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
}

// ── Menus ─────────────────────────────────────────────────────────────────────
// item : { icon, label, run, sheet?, danger?, expert? } ou { divider }
// sheet: true → run() ouvre un autre panneau (remplace le menu) ; sinon le menu se ferme avant.

export function trackMenu({ path, title, sub, albumPath, onChanged }) {
	openSheet('menu', {
		title, sub, coverSrc: albumPath ? coverUrl(albumPath) : '', coverLabel: title,
		items: [
			{ icon: 'edit', label: 'Modifier les infos', sheet: true, run: () => openSheet('editTrack', { path, onSaved: onChanged }) },
			{ icon: 'move', label: 'Déplacer vers…', sheet: true, run: () => openSheet('move', { what: 'track', path, onDone: onChanged }) },
			...(isAdmin() ? [
				{ divider: 'Admin' },
				{ icon: 'trash', label: 'Supprimer le titre', danger: true, run: () => deleteTrack(path, title, onChanged) },
			] : []),
		],
	});
}

export function albumMenu(albumPath) {
	const r = findAlbum(get(tree), albumPath);
	if (!r) return;
	const { artist, album } = r;
	openSheet('menu', {
		title: album.name, sub: artist?.name ?? '', coverSrc: coverUrl(albumPath), coverLabel: album.name,
		items: [
			{ icon: 'edit', label: "Modifier l'album", sheet: true, run: () => openSheet('editAlbum', { albumPath }) },
			{ icon: 'image', label: 'Changer la pochette', run: async () => changeAlbumCover(albumPath, await pickImage()) },
			...(artist ? [{ icon: 'move', label: 'Déplacer vers un autre artiste…', sheet: true, run: () => openSheet('move', { what: 'album', path: albumPath }) }] : []),
			...(isAdmin() ? [
				{ divider: 'Outils admin' },
				{ icon: 'hash', label: 'Numéroter les pistes', expert: true, sheet: true, run: () => openSheet('tool', { tool: 'renumber', albumPath }) },
				...(artist ? [{ icon: 'spark', label: 'Vérifier avec iTunes', expert: true, sheet: true, run: () => openSheet('tool', { tool: 'audit', artistPath: artist.path }) }] : []),
				{ icon: 'trash', label: "Supprimer l'album", danger: true, run: () => deleteAlbum(albumPath) },
			] : []),
		],
	});
}

export function artistMenu(artistPath) {
	const a = findArtist(get(tree), artistPath);
	if (!a) return;
	openSheet('menu', {
		title: a.name, sub: `${plural(a.albums.length, 'album')} · ${plural(countSongs(a.albums), 'titre')}`,
		coverSrc: a.has_picture ? pictureUrl(artistPath) : '', coverLabel: a.name, round: true,
		items: [
			{ icon: 'image', label: 'Changer la photo', run: async () => changeArtistPicture(artistPath, await pickImage()) },
			...(isAdmin() ? [
				{ divider: 'Outils admin' },
				{ icon: 'tag', label: "Genre de l'artiste", expert: true, sheet: true, run: () => openSheet('tool', { tool: 'genre', artistPath }) },
				{ icon: 'spark', label: 'Vérifier avec iTunes', expert: true, sheet: true, run: () => openSheet('tool', { tool: 'audit', artistPath }) },
				{ icon: 'trash', label: "Supprimer l'artiste", danger: true, run: () => deleteArtist(artistPath) },
			] : []),
		],
	});
}

// ── Suppressions (admin) : une fenêtre explique ce qui disparaît ────────────────

async function deleteTrack(path, title, onChanged) {
	const ok = await confirmAction({
		title: `Supprimer « ${title} » ?`,
		message: 'Le fichier MP3 est effacé de la bibliothèque Jellyfin.\nImpossible d\'annuler.',
		confirmLabel: 'Supprimer', danger: true,
	});
	if (!ok) return;
	try {
		const res = await api.deleteSong(path);
		addToast('Titre supprimé.', 'info');
		await refreshLibrary();
		if (res.removed_album) goto(artistOrLibrary(parentPath(parentPath(path))), { replaceState: true });
		else onChanged?.();
	} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
}

async function deleteAlbum(albumPath) {
	const r = findAlbum(get(tree), albumPath);
	const n = r?.album.songs?.length ?? 0;
	const ok = await confirmAction({
		title: `Supprimer l'album « ${r?.album.name ?? albumPath} » ?`,
		message: `Ses ${plural(n, 'titre')} et sa pochette sont effacés de la bibliothèque Jellyfin.\nImpossible d'annuler.`,
		confirmLabel: 'Supprimer', danger: true,
	});
	if (!ok) return;
	try {
		await api.deleteFolder(albumPath);
		addToast('Album supprimé.', 'info');
		await refreshLibrary();
		goto(artistOrLibrary(parentPath(albumPath)), { replaceState: true });
	} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
}

async function deleteArtist(artistPath) {
	const a = findArtist(get(tree), artistPath);
	const ok = await confirmAction({
		title: `Supprimer ${a?.name ?? artistPath} ?`,
		message: `Ses ${plural(a?.albums.length ?? 0, 'album')} (${plural(countSongs(a?.albums), 'titre')}) sont effacés de la bibliothèque Jellyfin.\nImpossible d'annuler.`,
		confirmLabel: 'Supprimer', danger: true,
	});
	if (!ok) return;
	try {
		await api.deleteFolder(artistPath);
		addToast('Artiste supprimé.', 'info');
		await refreshLibrary();
		goto(LIBRARY_URL, { replaceState: true });
	} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
}

function artistOrLibrary(artistPath) {
	return artistPath && findArtist(get(tree), artistPath) ? artistUrl(artistPath) : LIBRARY_URL;
}
