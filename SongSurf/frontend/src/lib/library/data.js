// Données de « Ma musique » (SSF-13) : arbre de la bibliothèque, albums à
// compléter (« À remplir »), versions d'images, petits utilitaires d'affichage.
import { writable, get } from 'svelte/store';
import { api } from '$lib/api.js';

// ── localStorage (préfixe ssf.*) ────────────────────────────────────────────
const LS_TREE = 'ssf.lib.tree';
const LS_IMGV = 'ssf.meta.imgv'; // clé historique gardée : les images déjà en cache restent valides

function lsGet(key) {
	try { return localStorage.getItem(key); } catch { return null; }
}
function lsSet(key, value) {
	try { localStorage.setItem(key, value); } catch { /* quota, navigation privée */ }
}
function lsJson(key, fallback) {
	try { return JSON.parse(lsGet(key) ?? 'null') ?? fallback; } catch { return fallback; }
}

// ── Arbre { artists: [{name, path, has_picture, albums: [{name, path, songs: [{name, path}]}]}] } ──
// Affiché tout de suite depuis le cache, puis rafraîchi (stale-while-revalidate).
export const tree = writable(lsJson(LS_TREE, null));
export const treeLoaded = writable(false);

export async function refreshTree() {
	try {
		const data = await api.getLibrary();
		const t = { artists: data.artists ?? [] };
		tree.set(t);
		lsSet(LS_TREE, JSON.stringify(t));
	} catch { /* hors ligne : on garde le cache */ }
	finally { treeLoaded.set(true); }
}

// ── À remplir : [{path, name, artist, artist_path, tracks, missing{genre,year,track_number}, genres}] ──
export const todo = writable(null);

export async function refreshTodo() {
	try {
		const data = await api.todo();
		todo.set(data.albums ?? []);
	} catch { /* ignore */ }
}

export function refreshLibrary() {
	return Promise.all([refreshTree(), refreshTodo()]);
}

// ── Recherche dans l'arbre ───────────────────────────────────────────────────
export function findArtist(t, path) {
	return (t?.artists ?? []).find((a) => a.path === path) ?? null;
}

/** { artist, album } — artist = null pour un ancien dossier « playlist » à plat. */
export function findAlbum(t, path) {
	for (const a of t?.artists ?? []) {
		const al = (a.albums ?? []).find((x) => x.path === path);
		if (al) return { artist: a, album: al };
	}
	return null;
}

export function allAlbums(t) {
	return (t?.artists ?? []).flatMap((a) => (a.albums ?? []).map((al) => ({ artist: a, album: al })));
}

export function allSongs(t) {
	return allAlbums(t).flatMap(({ artist, album }) => (album.songs ?? []).map((s) => ({ artist, album, song: s })));
}

export const parentPath = (path) => path.split('/').slice(0, -1).join('/');

// ── Adresses des vues ────────────────────────────────────────────────────────
export const LIBRARY_URL = '/library';
export const artistUrl = (path) => `/library?artist=${encodeURIComponent(path)}`;
export const albumUrl = (path) => `/library?album=${encodeURIComponent(path)}`;

// ── Numéros de piste (TRCK « n/total ») ──────────────────────────────────────
export function trackNum(t) {
	return parseInt(String(t?.track_number ?? '').split('/')[0], 10);
}

/** Pistes numérotées d'abord (par TRCK), puis les autres (ordre reçu). */
export function sortByTrck(tracks) {
	const numbered = tracks.filter((t) => !isNaN(trackNum(t))).sort((a, b) => trackNum(a) - trackNum(b));
	return [...numbered, ...tracks.filter((t) => isNaN(trackNum(t)))];
}

/** Infos manquantes signalées sur une ligne de titre (le genre est demandé par « À remplir »). */
export function trackMissing(t) {
	return [!t.year && 'Année', isNaN(trackNum(t)) && 'N° de piste'].filter(Boolean);
}

// ── Images (cache navigateur) ────────────────────────────────────────────────
// URL d'image ?t=<version> stable entre les montages, incrémentée uniquement
// à l'upload d'une pochette ou d'une photo, pour ce chemin-là.
export const imgVersions = writable(lsJson(LS_IMGV, {}));

export function bumpImgVersion(path) {
	imgVersions.update((v) => {
		const next = { ...v, [path]: (v[path] ?? 0) + 1 };
		lsSet(LS_IMGV, JSON.stringify(next));
		return next;
	});
}

export const coverUrl = (albumPath) => api.getFolderCoverUrl(albumPath, get(imgVersions)[albumPath] ?? 0);
export const pictureUrl = (artistPath) => api.getArtistPictureUrl(artistPath, get(imgVersions)[artistPath] ?? 0);

/** Première image du presse-papiers (Ctrl+V), sinon null. */
export function pastedImage(e) {
	for (const item of e.clipboardData?.items ?? []) {
		if (item.kind !== 'file') continue;
		const file = item.getAsFile();
		if (!file?.type.startsWith('image/')) continue;
		e.preventDefault();
		return file;
	}
	return null;
}

// ── Textes ────────────────────────────────────────────────────────────────────
export const songTitle = (name) => String(name ?? '').replace(/\.mp3$/i, '');
export const plural = (n, word, pluralWord = word + 's') => `${n} ${n > 1 ? pluralWord : word}`;
export const countSongs = (albums) => (albums ?? []).reduce((n, al) => n + (al.songs?.length ?? 0), 0);
