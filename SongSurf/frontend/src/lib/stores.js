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
});

export const workerBusy = derived(
	downloadStatus,
	($s) => !!$s.in_progress || ($s.queue_size ?? 0) > 0 || !!$s.batch_active
);

export const recentDownloads = writable([]); // [{ artist, title, filePath }]

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
