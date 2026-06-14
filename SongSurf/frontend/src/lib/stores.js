import { writable, derived } from 'svelte/store';

export const user = writable(null); // { sub, role, email }

export const downloadStatus = writable({
	in_progress: false,
	current_download: null,
	last_completed: null,
	last_error: null,
	progress: null,
	queue_size: 0,
	batch_active: false,
	batch_total: 0,
	batch_done: 0,
	batch_percent: 0,
	is_mine: true,
});

export const workerBusy = derived(
	downloadStatus,
	($s) => !!$s.in_progress || ($s.queue_size ?? 0) > 0 || !!$s.batch_active
);

export const workerBusyByOther = derived(
	downloadStatus,
	($s) => (!!$s.in_progress || ($s.queue_size ?? 0) > 0 || !!$s.batch_active) && !$s.is_mine
);

export const lastCompleted = writable(null); // { artist, title, timestamp } | null

// Items submitted by the Chrome extension, waiting for UrlQueue to pick up
export const extensionQueue = writable([]);

// Theme: 'light' | 'dark' — initialized in +layout.svelte onMount from localStorage
export const theme = writable('light');

// Persists the UrlQueue across navigation
export const urlQueue = writable([]);

// Help/tutorial modal open state (toggled by the "?" button in the header).
// Auto-opened once on first visit — see +layout.svelte (localStorage 'ssf.help.seen').
export const helpOpen = writable(false);

// ── Toasts ────────────────────────────────────────────────────────────────────

export const toasts = writable([]); // [{ id, message, type }]

let _toastId = 0;

export function addToast(message, type = 'info', duration = 4000) {
	const id = ++_toastId;
	toasts.update((list) => [...list, { id, message, type }]);
	if (duration > 0) setTimeout(() => removeToast(id), duration);
	return id;
}

export function removeToast(id) {
	toasts.update((list) => list.filter((t) => t.id !== id));
}

// ── Confirmation modal ──────────────────────────────────────────────────────────
// Remplace le confirm() natif par une modal SongSurf. Drop-in : await confirmAction(...).

export const confirmState = writable(null); // { title, message, confirmLabel, cancelLabel, danger, resolve } | null

/**
 * Affiche une modal de confirmation et résout à true (confirmé) / false (annulé).
 * @param {{ title?: string, message: string, confirmLabel?: string, cancelLabel?: string, danger?: boolean }} opts
 * @returns {Promise<boolean>}
 */
export function confirmAction(opts) {
	return new Promise((resolve) => {
		confirmState.set({
			title: opts.title ?? 'Confirmer',
			message: opts.message ?? '',
			confirmLabel: opts.confirmLabel ?? 'OK',
			cancelLabel: opts.cancelLabel ?? 'Annuler',
			danger: opts.danger ?? false,
			resolve,
		});
	});
}
