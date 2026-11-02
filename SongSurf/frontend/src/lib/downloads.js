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

// Avancement du titre en cours (même pondération que le serveur pour le batch).
const PHASE_PCT = { converting: 55, organizing: 90, completed: 100 };
export function songPercent(progress) {
	if (!progress) return 0;
	if (progress.phase in PHASE_PCT) return PHASE_PCT[progress.phase];
	return Math.round(Math.max(0, Math.min(100, Number(progress.percent ?? 0))) * 0.5);
}

/** Vue « En cours » : { current, pending, waitingOther, songsBefore } */
export const myDownloads = derived(downloadStatus, ($s) => {
	const current = $s.is_mine && $s.in_progress && $s.current_download ? $s.current_download.metadata ?? {} : null;
	const pending = $s.pending ?? [];
	const busyOther = !$s.is_mine && (!!$s.in_progress || ($s.queue_size ?? 0) > 0);
	return {
		current,
		percent: current ? songPercent($s.progress) : 0,
		pending,
		waitingOther: busyOther && pending.length > 0,
		songsBefore: Number($s.worker?.songs_before_mine ?? 0),
		active: !!current || pending.length > 0,
		count: (current ? 1 : 0) + pending.length,
	};
});

/** Ajouts restants aujourd'hui (membres) ; null = illimité (admin) ou inconnu. */
export const dailyLeft = derived(downloadStatus, ($s) =>
	$s.daily_limit ? Math.max(0, $s.daily_limit - ($s.daily_count ?? 0)) : null);
