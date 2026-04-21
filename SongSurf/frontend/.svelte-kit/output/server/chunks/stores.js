import { d as derived, w as writable } from "./index.js";
const user = writable(null);
const downloadStatus = writable({
  in_progress: false,
  current_download: null,
  last_completed: null,
  last_error: null,
  progress: null,
  queue_size: 0,
  batch_active: false,
  batch_total: 0,
  batch_done: 0,
  batch_percent: 0
});
const workerBusy = derived(
  downloadStatus,
  ($s) => !!$s.in_progress || ($s.queue_size ?? 0) > 0 || !!$s.batch_active
);
const recentDownloads = writable([]);
const toasts = writable([]);
export {
  downloadStatus as d,
  recentDownloads as r,
  toasts as t,
  user as u,
  workerBusy as w
};
