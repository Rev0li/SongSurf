async function request(url, options = {}) {
	const response = await fetch(url, {
		headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
		credentials: 'same-origin',
		...options,
	});
	const text = await response.text();
	let data;
	try {
		data = text ? JSON.parse(text) : {};
	} catch {
		data = { success: false, error: text || 'Réponse invalide' };
	}
	if (!response.ok) {
		throw new Error(data?.error ?? `HTTP ${response.status}`);
	}
	return data;
}

export const api = {
	me() {
		return request('/api/me');
	},
	getStatus() {
		return request('/api/status');
	},
	getLibrary() {
		return request('/api/library');
	},
	extract(url) {
		return request('/api/extract', { method: 'POST', body: JSON.stringify({ url }) });
	},
	download(payload) {
		return request('/api/download', { method: 'POST', body: JSON.stringify(payload) });
	},
	downloadPlaylist(payload) {
		return request('/api/download-playlist', { method: 'POST', body: JSON.stringify(payload) });
	},
	prepareZip() {
		return request('/api/prepare-zip', { method: 'POST' });
	},
	moveSong(source, targetFolder) {
		return request('/api/library/move', {
			method: 'POST',
			body: JSON.stringify({ source, target_folder: targetFolder }),
		});
	},
	moveFolder(folderPath, newParent) {
		return request('/api/library/move-folder', {
			method: 'POST',
			body: JSON.stringify({ folder_path: folderPath, new_parent: newParent }),
		});
	},
	cancelPrefetch(token) {
		return request('/api/prefetch/cancel', { method: 'POST', body: JSON.stringify({ token }) });
	},
	getPrefetchCoverUrl(token) {
		return `/api/prefetch/cover?token=${encodeURIComponent(token)}&t=${Date.now()}`;
	},
	getFolderCoverUrl(folderPath, ts = Date.now()) {
		return `/api/library/folder-cover?folder_path=${encodeURIComponent(folderPath)}&t=${ts}`;
	},
	songMeta(path) {
		return request(`/api/library/song-meta?path=${encodeURIComponent(path)}`);
	},
	saveSongMeta(path, tags) {
		return request('/api/library/song-meta/save', { method: 'POST', body: JSON.stringify({ path, tags }) });
	},
	consumeExtensionQueue() {
		return request('/api/extension-queue/consume', { method: 'POST' });
	},
	getArtistPictureUrl(folderPath, ts = Date.now()) {
		return `/api/library/artist-picture?folder_path=${encodeURIComponent(folderPath)}&t=${ts}`;
	},
	uploadSongCover(path, file) {
		const form = new FormData();
		form.append('path', path);
		form.append('image', file);
		return fetch('/api/library/song-cover/upload', { method: 'POST', credentials: 'same-origin', body: form })
			.then(async (r) => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error ?? `HTTP ${r.status}`); return d; });
	},
	uploadAlbumCover(folderPath, file) {
		const form = new FormData();
		form.append('folder_path', folderPath);
		form.append('image', file);
		return fetch('/api/library/album-cover/upload', { method: 'POST', credentials: 'same-origin', body: form })
			.then(async (r) => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error ?? `HTTP ${r.status}`); return d; });
	},
	uploadArtistCover(folderPath, file) {
		const form = new FormData();
		form.append('folder_path', folderPath);
		form.append('image', file);
		return fetch('/api/library/artist-cover/upload', { method: 'POST', credentials: 'same-origin', body: form })
			.then(async (r) => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.error ?? `HTTP ${r.status}`); return d; });
	},
};
