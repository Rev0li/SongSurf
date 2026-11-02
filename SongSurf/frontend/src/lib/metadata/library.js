// État partagé de la page /metadata : arbre de la bibliothèque, sélection
// courante, versions d'images, tracklist de l'album ouvert.
// Les composants de `lib/components/metadata/` lisent ces stores et appellent
// les fonctions de navigation exportées ici.
import { writable, get } from 'svelte/store';
import { api } from '$lib/api.js';

// ── Persistance (localStorage, préfixe ssf.meta.*) ───────────────────────────
export const LS = {
	expanded:   'ssf.meta.expanded',
	sidebar:    'ssf.meta.sidebar',
	sel:        'ssf.meta.sel',
	tree:       'ssf.meta.tree',
	homeScroll: 'ssf.meta.homeScroll',
	imgv:       'ssf.meta.imgv',
};

export function lsGet(key, fallback = null) {
	try {
		const raw = localStorage.getItem(key);
		return raw === null ? fallback : raw;
	} catch { return fallback; }
}

export function lsSet(key, value) {
	try {
		if (value === null) localStorage.removeItem(key);
		else localStorage.setItem(key, value);
	} catch { /* ignore */ }
}

function lsJson(key, fallback) {
	try { return JSON.parse(lsGet(key, 'null')) ?? fallback; } catch { return fallback; }
}

// ── Arbre ─────────────────────────────────────────────────────────────────────
export const tree = writable(null); // { artists: [], playlists: [] } | null

export function persistTree() {
	lsSet(LS.tree, JSON.stringify(get(tree)));
}

// ── Sélection ─────────────────────────────────────────────────────────────────
// type   : null | 'artist' | 'album' | 'song'
// artist : { path, name, albums } (vue artiste)
// album  : { path, name, songs[], artist: { path, name } } — gardé en vue titre
//          quand on vient du panneau album (flèches précédent/suivant)
// path   : chemin relatif du titre (vue titre)
// seq    : incrémenté à chaque sélection → les panneaux se remontent (état local remis à zéro)
export const selection = writable({ type: null, artist: null, album: null, path: '', seq: 0 });

function select(patch) {
	selection.update((s) => ({ ...s, ...patch, seq: s.seq + 1 }));
}

function persistSelection(sel) {
	lsSet(LS.sel, sel ? JSON.stringify(sel) : null);
}

// Tracklist réelle (TRCK) de l'album sélectionné, partagée avec la vue titre
// (ordre des flèches précédent/suivant). null = pas encore chargée ou échec.
export const albumTracks = writable(null);
export const albumTracksLoading = writable(false);

// Section « Champs supplémentaires » du panneau titre : reste ouverte d'un titre à l'autre.
export const secondaryOpen = writable(false);

export function selectArtist(artist) {
	select({ type: 'artist', artist, album: null, path: '' });
	persistSelection({ type: 'artist', path: artist.path });
}

export function selectAlbum(album, artist) {
	select({ type: 'album', album: { ...album, artist }, artist: null, path: '' });
	loadAlbumTracks(album.path);
	persistSelection({ type: 'album', path: album.path, artistPath: artist.path });
}

// keepAlbumCtx : true quand on vient du panneau album (les flèches restent actives)
export function selectSong(path, keepAlbumCtx = false) {
	const s = get(selection);
	if (s.path === path && s.type === 'song') return;
	select({ type: 'song', path, artist: null, ...(keepAlbumCtx ? {} : { album: null }) });
	persistSelection({ type: 'song', path });
}

export function goHome() {
	select({ type: null, path: '', album: null, artist: null });
	persistSelection(null);
}

// Retour à l'accueil sans toucher à la sélection mémorisée (titre/album déplacé ou disparu).
export function dropSelection(patch = {}) {
	select({ type: null, ...patch });
}

export function gotoArtistByPath(p) {
	const a = (get(tree)?.artists ?? []).find((x) => x.path === p);
	if (a) selectArtist(a);
}

export function gotoAlbumByPath(artistPath, albumPath) {
	const a  = (get(tree)?.artists ?? []).find((x) => x.path === artistPath);
	const al = a?.albums?.find((x) => x.path === albumPath);
	if (a && al) selectAlbum(al, a);
}

function songExistsInTree(path) {
	const t = get(tree);
	const all = [
		...(t?.artists ?? []).flatMap((a) => (a.albums ?? []).flatMap((al) => al.songs ?? [])),
		...(t?.playlists ?? []).flatMap((pl) => pl.songs ?? []),
	];
	return all.some((s) => s.path === path);
}

export function restoreSelection() {
	const sel = lsJson(LS.sel, null);
	if (!sel || !get(tree)) return;
	if (sel.type === 'artist') gotoArtistByPath(sel.path);
	else if (sel.type === 'album') gotoAlbumByPath(sel.artistPath, sel.path);
	else if (sel.type === 'song' && songExistsInTree(sel.path)) selectSong(sel.path);
}

// ── Tracklist de l'album (TRCK réels) ─────────────────────────────────────────
export function trackNum(t) {
	return parseInt(String(t.track_number).split('/')[0], 10);
}

// Pistes numérotées d'abord (par TRCK), puis les sans-numéro (ordre reçu)
export function sortByTrck(tracks) {
	const numbered   = tracks.filter((t) => !isNaN(trackNum(t))).sort((a, b) => trackNum(a) - trackNum(b));
	const unnumbered = tracks.filter((t) => isNaN(trackNum(t)));
	return [...numbered, ...unnumbered];
}

export async function loadAlbumTracks(albumPath) {
	albumTracks.set(null);
	albumTracksLoading.set(true);
	const stillSelected = () => get(selection).album?.path === albumPath;
	try {
		const data = await api.albumTracks(albumPath);
		if (!stillSelected()) return;
		albumTracks.set(sortByTrck(data.tracks ?? []));
	} catch { albumTracks.set(null); /* repli : ordre alphabétique si l'appel échoue */ }
	finally {
		if (stillSelected()) albumTracksLoading.set(false);
	}
}

// ── Rafraîchissement après une modification de la bibliothèque ────────────────
export async function refreshTree() {
	try {
		const data = await api.getLibrary();
		tree.set(data);
		persistTree();
		// Garde les titres de l'album sélectionné à jour s'il existe encore
		const { album } = get(selection);
		if (album) {
			const newArtist = (data.artists ?? []).find((a) => a.path === album.artist.path);
			const newAlbum  = newArtist?.albums?.find((a) => a.path === album.path);
			if (newAlbum) selection.update((s) => ({ ...s, album: { ...s.album, songs: newAlbum.songs } }));
			else dropSelection({ album: null });
		}
	} catch { /* ignore */ }
}

// ── Coller une image (Ctrl+V) ─────────────────────────────────────────────────
// Renvoie la première image du presse-papiers (et bloque le collage par défaut), sinon null.
// Chaque panneau (artiste / album / titre) branche son propre upload sur <svelte:window on:paste>.
export function pastedImage(e) {
	for (const item of (e.clipboardData?.items ?? [])) {
		if (item.kind !== 'file') continue;
		const file = item.getAsFile();
		if (!file?.type.startsWith('image/')) continue;
		e.preventDefault();
		return file;
	}
	return null;
}

// ── Versions d'images (cache navigateur) ──────────────────────────────────────
// Les URLs d'images portent ?t=<version> : stable entre les montages de la page
// (le navigateur garde les images en cache au lieu de tout re-télécharger),
// incrémentée uniquement à l'upload d'une pochette/photo, pour ce chemin-là.
export const imgVersions = writable(lsJson(LS.imgv, {}));

export function bumpImgVersion(path) {
	imgVersions.update((v) => {
		const next = { ...v, [path]: (v[path] ?? 0) + 1 };
		lsSet(LS.imgv, JSON.stringify(next));
		return next;
	});
}
