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
	cancel() {
		return request('/api/cancel', { method: 'POST' });
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
	renameFolder(folderPath, newName) {
		return request('/api/library/rename-folder', {
			method: 'POST',
			body: JSON.stringify({ folder_path: folderPath, new_name: newName }),
		});
	},
	moveFolder(folderPath, newParent) {
		return request('/api/library/move-folder', {
			method: 'POST',
			body: JSON.stringify({ folder_path: folderPath, new_parent: newParent }),
		});
	},
	deleteFolder(folderPath) {
		return request('/api/library/delete-folder', {
			method: 'POST',
			body: JSON.stringify({ folder_path: folderPath }),
		});
	},
	uploadLibraryImage(file, targetFolder) {
		const form = new FormData();
		form.append('image', file);
		form.append('target_folder', targetFolder);
		return fetch('/api/library/upload-image', {
			method: 'POST',
			credentials: 'same-origin',
			body: form,
		}).then(async (res) => {
			const text = await res.text();
			let data;
			try { data = text ? JSON.parse(text) : {}; } catch { data = { success: false, error: text }; }
			if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
			return data;
		});
	},
	cancelPrefetch(token) {
		return request('/api/prefetch/cancel', { method: 'POST', body: JSON.stringify({ token }) });
	},
	getPrefetchCoverUrl(token) {
		return `/api/prefetch/cover?token=${encodeURIComponent(token)}&t=${Date.now()}`;
	},
	getFolderCoverUrl(folderPath) {
		return `/api/library/folder-cover?folder_path=${encodeURIComponent(folderPath)}&t=${Date.now()}`;
	},
	songMeta(path) {
		return request(`/api/library/song-meta?path=${encodeURIComponent(path)}`);
	},
	saveSongMeta(path, tags) {
		return request('/api/library/song-meta/save', { method: 'POST', body: JSON.stringify({ path, tags }) });
	},
	libraryIssues() {
		return request('/api/library/issues');
	},
	consumeExtensionQueue() {
		return request('/api/extension-queue/consume', { method: 'POST' });
	},
	getArtistPictureUrl(folderPath) {
		return `/api/library/artist-picture?folder_path=${encodeURIComponent(folderPath)}&t=${Date.now()}`;
	},
	uploadSongCover(path, file) {
		const form = new FormData();
		form.append('path', path);
		form.append('image', file);
		return fetch('/api/library/song-cover/upload', { method: 'POST', credentials: 'same-origin', body: form })
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
