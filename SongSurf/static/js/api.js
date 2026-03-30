async function jsonRequest(url, options = {}) {
	const response = await fetch(url, {
		headers: {
			'Content-Type': 'application/json',
			...(options.headers || {}),
		},
		credentials: 'same-origin',
		...options,
	});

	const text = await response.text();
	let data;
	try {
		data = text ? JSON.parse(text) : {};
	} catch (_) {
		data = { success: false, error: text || 'Réponse invalide' };
	}

	if (!response.ok) {
		const message = data && data.error ? data.error : ('HTTP ' + response.status);
		throw new Error(message);
	}

	return data;
}

window.api = {
	getStatus() {
		return jsonRequest('/api/status');
	},
	getLibrary() {
		return jsonRequest('/api/library');
	},
	moveSong(source, targetFolder) {
		return jsonRequest('/api/library/move', {
			method: 'POST',
			body: JSON.stringify({ source: source, target_folder: targetFolder }),
		});
	},
	renameFolder(folderPath, newName) {
		return jsonRequest('/api/library/rename-folder', {
			method: 'POST',
			body: JSON.stringify({ folder_path: folderPath, new_name: newName }),
		});
	},
	prepareAdminZip() {
		return jsonRequest('/api/admin/prepare-zip', { method: 'POST' });
	},
	uploadLibraryImage(file, targetFolder) {
		const form = new FormData();
		form.append('image', file);
		form.append('target_folder', targetFolder);
		return fetch('/api/library/upload-image', {
			method: 'POST',
			credentials: 'same-origin',
			body: form,
		}).then(async function (response) {
			const text = await response.text();
			let data;
			try {
				data = text ? JSON.parse(text) : {};
			} catch (_) {
				data = { success: false, error: text || 'Réponse invalide' };
			}
			if (!response.ok) {
				throw new Error(data.error || ('HTTP ' + response.status));
			}
			return data;
		});
	},
	getFolderCoverUrl(folderPath) {
		return '/api/library/folder-cover?folder_path=' + encodeURIComponent(folderPath || '') + '&t=' + Date.now();
	},
	getPrefetchCoverUrl(token) {
		return '/api/prefetch/cover?token=' + encodeURIComponent(token || '') + '&t=' + Date.now();
	},
	cancelPrefetch(token) {
		return jsonRequest('/api/prefetch/cancel', {
			method: 'POST',
			body: JSON.stringify({ token: token || '' }),
		});
	},
	extract(url) {
		return jsonRequest('/api/extract', {
			method: 'POST',
			body: JSON.stringify({ url }),
		});
	},
	download(payload) {
		return jsonRequest('/api/download', {
			method: 'POST',
			body: JSON.stringify(payload),
		});
	},
	downloadPlaylist(payload) {
		return jsonRequest('/api/download-playlist', {
			method: 'POST',
			body: JSON.stringify(payload),
		});
	},
	cleanup() {
		return jsonRequest('/api/cleanup', { method: 'POST' });
	},
};