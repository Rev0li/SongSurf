(function () {
	async function jsonRequest(url, options) {
		const response = await fetch(url, {
			headers: {
				'Content-Type': 'application/json',
				...((options && options.headers) || {}),
			},
			credentials: 'same-origin',
			...(options || {}),
		});

		const text = await response.text();
		let data;
		try {
			data = text ? JSON.parse(text) : {};
		} catch (_) {
			data = { success: false, error: text || 'Reponse invalide' };
		}

		if (!response.ok) {
			const message = data && data.error ? data.error : ('HTTP ' + response.status);
			throw new Error(message);
		}
		return data;
	}

	function adaptGuestStatus(st) {
		const inProgress = !!st.in_progress;
		const queueSize = Number(st.queue_size || 0);
		const done = Number(st.songs_downloaded || 0);
		const currentPct = Number((st.progress && st.progress.percent) || 0);
		const total = Math.max(done + queueSize + (inProgress ? 1 : 0), done, 1);
		const composed = ((done + (inProgress ? (currentPct / 100.0) : 0.0)) / total) * 100.0;

		return {
			...st,
			batch_active: inProgress || queueSize > 0,
			batch_total: total,
			batch_done: done,
			batch_percent: Math.max(0, Math.min(100, Number(composed.toFixed(1)))),
		};
	}

	window.api = {
		async getStatus() {
			const st = await jsonRequest('/api/guest/status');
			return adaptGuestStatus(st);
		},
		getLibrary() {
			return jsonRequest('/api/guest/library');
		},
		moveSong(source, targetFolder) {
			return jsonRequest('/api/guest/library/move', {
				method: 'POST',
				body: JSON.stringify({ source: source, target_folder: targetFolder }),
			});
		},
		renameFolder(folderPath, newName) {
			return jsonRequest('/api/guest/library/rename-folder', {
				method: 'POST',
				body: JSON.stringify({ folder_path: folderPath, new_name: newName }),
			});
		},
		prepareAdminZip() {
			return jsonRequest('/api/guest/prepare-zip', { method: 'POST' }).then(function (res) {
				return {
					success: !!res.success,
					count: Number(res.file_count || 0),
					size_mb: Number(res.size_mb || 0),
					download_url: res.download_url || '/api/guest/download-zip',
				};
			});
		},
		uploadLibraryImage(file, targetFolder) {
			const form = new FormData();
			form.append('image', file);
			form.append('target_folder', targetFolder);
			return fetch('/api/guest/library/upload-image', {
				method: 'POST',
				credentials: 'same-origin',
				body: form,
			}).then(async function (response) {
				const text = await response.text();
				let data;
				try {
					data = text ? JSON.parse(text) : {};
				} catch (_) {
					data = { success: false, error: text || 'Reponse invalide' };
				}
				if (!response.ok) {
					throw new Error(data.error || ('HTTP ' + response.status));
				}
				return data;
			});
		},
		getFolderCoverUrl(folderPath) {
			return '/api/guest/library/folder-cover?folder_path=' + encodeURIComponent(folderPath || '') + '&t=' + Date.now();
		},
		getPrefetchCoverUrl() {
			return '';
		},
		cancelPrefetch() {
			return Promise.resolve({ success: true });
		},
		extract(url) {
			return jsonRequest('/api/guest/extract', {
				method: 'POST',
				body: JSON.stringify({ url: url }),
			});
		},
		download(payload) {
			return jsonRequest('/api/guest/download', {
				method: 'POST',
				body: JSON.stringify(payload),
			});
		},
		downloadPlaylist(payload) {
			return jsonRequest('/api/guest/download-playlist', {
				method: 'POST',
				body: JSON.stringify(payload),
			});
		},
		cleanup() {
			return jsonRequest('/api/guest/cleanup', { method: 'POST' });
		},
	};
})();
