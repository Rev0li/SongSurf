// Téléchargements vus par l'utilisateur (SSF-13) : le titre en cours, la file,
// et l'historique de la session (terminés / échecs) reconstruit à partir de
// last_completed / last_error de /api/status.
import { writable, derived } from 'svelte/store';
import { downloadStatus } from '$lib/stores.js';
import { asText } from '$lib/utils.js';

const SS_HISTORY = 'ssf.dl.history';
const MAX_HISTORY = 40;

function ssLoad() {
	try { return JSON.parse(sessionStorage.getItem(SS_HISTORY) ?? '[]'); } catch { return []; }
}

/** [{ key, status: 'done'|'error', title, artist, album, filePath?, skipped?, error?, url?, metadata? }] (récent d'abord) */
export const dlHistory = writable(typeof sessionStorage === 'undefined' ? [] : ssLoad());
dlHistory.subscribe((list) => {
	try { sessionStorage.setItem(SS_HISTORY, JSON.stringify(list)); } catch { /* ignore */ }
});

let lastDone = null;
let lastError = null;
let baseline = false;

/**
 * À appeler après chaque /api/status. Renvoie { completed, failed } (nouveaux
 * événements depuis l'appel précédent) ; le 1er appel fixe seulement la base
 * (pas de faux « terminé » pour un résultat d'une session précédente).
 */
export function ingestStatus(st) {
	const doneTs = st.last_completed?.timestamp ?? null;
	const errTs = st.last_error?.timestamp ?? null;
	const out = { completed: null, failed: null };
	if (!baseline) {
		baseline = true;
		lastDone = doneTs;
		lastError = errTs;
		return out;
	}
	if (doneTs && doneTs !== lastDone) {
		lastDone = doneTs;
		const m = st.last_completed.metadata ?? {};
		const item = {
			key: `d-${doneTs}`, status: 'done',
			title: asText(m.title, '…'), artist: asText(m.artist), album: asText(m.album),
			filePath: st.last_completed.file_path ?? '', skipped: !!st.last_completed.skipped,
		};
		pushHistory(item);
		out.completed = item;
	}
	if (errTs && errTs !== lastError) {
		lastError = errTs;
		const m = st.last_error.metadata ?? {};
		const item = {
			key: `e-${errTs}`, status: 'error',
			title: asText(m.title, '…'), artist: asText(m.artist), album: asText(m.album),
			error: asText(st.last_error.error, 'Téléchargement échoué.'),
			url: st.last_error.url ?? '', metadata: m,
		};
		pushHistory(item);
		out.failed = item;
	}
	return out;
}

function pushHistory(item) {
	dlHistory.update((list) => [item, ...list.filter((x) => x.key !== item.key)].slice(0, MAX_HISTORY));
}

export function removeHistory(key) {
	dlHistory.update((list) => list.filter((x) => x.key !== key));
}

export function clearDoneHistory() {
	dlHistory.update((list) => list.filter((x) => x.status !== 'done'));
}

// Avancement : le serveur estime celui du titre en cours au temps écoulé
// (current_percent, qui ne recule pas). Un album = un job = une seule ligne
// « 3 / 12 titres » dont la barre avance titre après titre.
// La barre d'un job ne recule jamais (petit creux possible entre deux titres).
const maxSeen = new Map();
function keepMax(key, pct) {
	const v = Math.max(maxSeen.get(key) ?? 0, pct);
	maxSeen.set(key, v);
	return v;
}

/**
 * Vue « En cours » : { jobs, running, current, pending, waitingOther, songsBefore, active, count }
 * jobs : [{ key, isAlbum, album, artist, title, total, done, active, percent, currentTitle }]
 * running : le job dont un titre est en cours (mini-barre), sinon null.
 */
export const myDownloads = derived(downloadStatus, ($s) => {
	const mine = !!$s.is_mine && !!$s.in_progress && !!$s.current_download;
	const current = mine ? $s.current_download.metadata ?? {} : null;
	const curPct = mine ? Math.max(0, Math.min(100, Number($s.current_percent ?? 0))) : 0;
	const pending = $s.pending ?? [];
	const busyOther = !$s.is_mine && (!!$s.in_progress || ($s.queue_size ?? 0) > 0);

	const live = new Set();
	const jobs = ($s.jobs ?? []).map((j) => {
		const total = Math.max(1, Number(j.total ?? 1));
		const done = Math.max(0, total - Number(j.remaining ?? total));
		const running = !!j.active && mine;
		const key = `${j.job_id}:${total}:${j.album}`; // pas le titre : il change à chaque piste
		live.add(key);
		return {
			key, total, done, isAlbum: total > 1,
			album: asText(j.album), artist: asText(j.artist), title: asText(j.title, '…'),
			active: running,
			currentTitle: running ? asText(current?.title, '') : '',
			percent: keepMax(key, ((done + (running ? curPct / 100 : 0)) / total) * 100),
		};
	});
	for (const k of maxSeen.keys()) if (!live.has(k)) maxSeen.delete(k);

	const count = jobs.reduce((n, j) => n + j.total - j.done, 0) || (current ? 1 : 0) + pending.length;
	return {
		jobs,
		current,
		running: jobs.find((j) => j.active) ?? null,
		pending,
		waitingOther: busyOther && pending.length > 0,
		songsBefore: Number($s.worker?.songs_before_mine ?? 0),
		active: !!current || pending.length > 0 || jobs.length > 0,
		count,
	};
});

/** Ajouts restants aujourd'hui (membres) ; null = illimité (admin) ou inconnu. */
export const dailyLeft = derived(downloadStatus, ($s) =>
	$s.daily_limit ? Math.max(0, $s.daily_limit - ($s.daily_count ?? 0)) : null);
