(function () {
	const els = {
		url: document.getElementById('url-input'),
		extractBtn: document.getElementById('btn-extract'),
		dlBtn: document.getElementById('btn-dl'),
		resetPreviewBtn: document.getElementById('btn-reset-preview'),
		alertZone: document.getElementById('alert-zone'),
		metadataPreview: document.getElementById('metadata-preview'),
		progZone: document.getElementById('progress-zone'),
		progFill: document.getElementById('prog-fill'),
		progStatus: document.getElementById('prog-status'),
		progPct: document.getElementById('prog-pct'),
		progSubtext: document.getElementById('prog-subtext'),
		dlList: document.getElementById('dl-list'),
		dlEmpty: document.getElementById('dl-empty'),
		libraryTree: document.getElementById('library-tree'),
		librarySearch: document.getElementById('library-search'),
		libExpandAll: document.getElementById('lib-expand-all'),
		libCollapseAll: document.getElementById('lib-collapse-all'),
		librarySelectedFolder: document.getElementById('library-selected-folder'),
		libraryImageFile: document.getElementById('library-image-file'),
		btnUploadFolderImage: document.getElementById('btn-upload-folder-image'),
		libraryFolderCover: document.getElementById('library-folder-cover'),
		libraryFolderCoverPlaceholder: document.getElementById('library-folder-cover-placeholder'),
		editTitle: document.getElementById('edit-title'),
		editArtist: document.getElementById('edit-artist'),
		editAlbum: document.getElementById('edit-album'),
		editPlaylistArtist: document.getElementById('edit-playlist-artist'),
		editPlaylistAlbum: document.getElementById('edit-playlist-album'),
		editPlaylistYear: document.getElementById('edit-playlist-year'),
		playlistMetaSummary: document.getElementById('playlist-meta-summary'),
		playlistSongList: document.getElementById('playlist-song-list'),
		playlistMode: document.getElementById('toggle-playlist-mode'),
		mp4Mode: document.getElementById('toggle-mp4-mode'),
		singleFields: document.getElementById('meta-fields-single'),
		playlistFields: document.getElementById('meta-fields-playlist'),
		playlistTitle: document.getElementById('playlist-title-display'),
		metaThumb: document.getElementById('meta-thumb'),
		metaThumbPlaceholder: document.getElementById('meta-thumb-placeholder'),
	};

	let currentUrl = '';
	let currentExtract = null;
	let currentPrefetchToken = '';
	let prefetchCoverTimer = null;
	let analysisPanelActive = false;
	let workerBusy = false;
	let lastCompletedTimestamp = '';
	let isDraggingLibrary = false;
	let libraryFilter = '';
	let selectedFolderPath = '';
	let selectedFolderName = '';

	function syncDownloadButtonState() {
		if (!els.dlBtn) return;
		if (!analysisPanelActive) {
			els.dlBtn.disabled = true;
			els.dlBtn.textContent = '⬇️ Télécharger';
			return;
		}
		if (workerBusy) {
			els.dlBtn.disabled = true;
			els.dlBtn.textContent = '⏳ En attente de Worker';
			return;
		}
		els.dlBtn.disabled = false;
		els.dlBtn.textContent = '⬇️ Télécharger';
	}

	function stopPrefetchCoverPolling() {
		if (prefetchCoverTimer) {
			clearInterval(prefetchCoverTimer);
			prefetchCoverTimer = null;
		}
	}

	function startPrefetchCoverPolling(prefetchToken, fallbackCandidates) {
		stopPrefetchCoverPolling();
		if (!prefetchToken || !window.api || !window.api.getPrefetchCoverUrl) return;

		const localCoverUrl = window.api.getPrefetchCoverUrl(prefetchToken);
		let tries = 0;
		const maxTries = 25;

		const probe = function () {
			tries += 1;
			const img = new Image();
			img.onload = function () {
				stopPrefetchCoverPolling();
				updateCoverPreview([localCoverUrl].concat(fallbackCandidates || []));
			};
			img.onerror = function () {
				if (tries >= maxTries) {
					stopPrefetchCoverPolling();
				}
			};
			img.src = localCoverUrl + '&probe=' + Date.now() + '_' + tries;
		};

		probe();
		prefetchCoverTimer = setInterval(probe, 1200);
	}

	async function cancelCurrentPrefetch() {
		if (!currentPrefetchToken || !window.api || !window.api.cancelPrefetch) return;
		const token = currentPrefetchToken;
		currentPrefetchToken = '';
		stopPrefetchCoverPolling();
		try {
			await window.api.cancelPrefetch(token);
		} catch (_) {
			// Ignorer un éventuel conflit de token périmé.
		}
	}

	function showAlert(message, type) {
		if (!els.alertZone) return;
		const cls = type === 'error' ? 'alert alert-error' : 'alert alert-info';
		els.alertZone.innerHTML = '<div class="' + cls + '">' + message + '</div>';
	}

	function clearAlert() {
		if (els.alertZone) els.alertZone.innerHTML = '';
	}

	function asText(value, fallback) {
		const v = (value || '').toString().trim();
		return v || fallback;
	}

	function primaryArtist(value) {
		const str = asText(value, 'Unknown Artist');
		const parts = str.split(/\s*(?:,|;|\||&|\band\b|\bet\b|\/)\s*/i).filter(Boolean);
		return parts[0] || str;
	}

	function artistFromSongTitle(title) {
		const raw = asText(title, '');
		if (!raw.includes(' - ')) return '';
		const maybeArtist = raw.split(' - ')[0].trim();
		if (!maybeArtist || maybeArtist.toLowerCase().includes('unknown')) return '';
		return primaryArtist(maybeArtist);
	}

	function inferPlaylistArtist(data) {
		const fromApi = primaryArtist(data && data.artist || 'Unknown Artist');
		if (fromApi && fromApi.toLowerCase() !== 'unknown artist') {
			return fromApi;
		}
		const songs = (data && data.songs) || [];
		for (let i = 0; i < songs.length; i += 1) {
			const s = songs[i] || {};
			const a = primaryArtist(s.artist || 'Unknown Artist');
			if (a && a.toLowerCase() !== 'unknown artist') return a;
			const parsed = artistFromSongTitle(s.title || '');
			if (parsed) return parsed;
		}
		return 'Unknown Artist';
	}

	function extractYouTubeVideoId(url) {
		const raw = asText(url, '');
		if (!raw) return '';

		const vMatch = raw.match(/[?&]v=([^&]+)/i);
		if (vMatch && vMatch[1]) return vMatch[1];

		const shortMatch = raw.match(/youtu\.be\/([^?&/]+)/i);
		if (shortMatch && shortMatch[1]) return shortMatch[1];

		return '';
	}

	function normalizeThumbUrl(url) {
		const raw = asText(url, '');
		if (!raw) return '';
		return raw.replace(/^https?:\/\/i\d+\.ytimg\.com\//i, 'https://i.ytimg.com/');
	}

	function pushUnique(arr, value) {
		const v = asText(value, '');
		if (!v) return;
		if (!arr.includes(v)) arr.push(v);
	}

	function candidatesFromVideoId(videoId) {
		const id = asText(videoId, '');
		if (!id) return [];
		return [
			'https://i.ytimg.com/vi/' + id + '/hqdefault.jpg',
			'https://i.ytimg.com/vi/' + id + '/mqdefault.jpg',
			'https://i.ytimg.com/vi/' + id + '/default.jpg',
		];
	}

	function shouldCacheBust(url) {
		const raw = asText(url, '');
		if (!raw) return false;
		if (/\/s_p\//i.test(raw)) return false;
		if (/[?&](?:rs|sqp)=/i.test(raw)) return false;
		return true;
	}

	function resolveCoverCandidates(data) {
		const out = [];

		const apiCandidates = (data && data.thumbnail_candidates) || [];
		if (Array.isArray(apiCandidates)) {
			apiCandidates.forEach(function (u) {
				pushUnique(out, normalizeThumbUrl(u));
			});
		}

		const direct = normalizeThumbUrl(data && data.thumbnail_url);
		pushUnique(out, direct);

		const songs = (data && data.songs) || [];
		if (songs.length > 0) {
			const first = songs[0] || {};
			const id = asText(first.id, '') || extractYouTubeVideoId(first.url);
			candidatesFromVideoId(id).forEach(function (u) { pushUnique(out, u); });
		}

		const fallbackId = extractYouTubeVideoId(currentUrl);
		candidatesFromVideoId(fallbackId).forEach(function (u) { pushUnique(out, u); });

		return out;
	}

	function htmlEscape(text) {
		return (text || '').toString()
			.replaceAll('&', '&amp;')
			.replaceAll('<', '&lt;')
			.replaceAll('>', '&gt;')
			.replaceAll('"', '&quot;')
			.replaceAll("'", '&#39;');
	}

	function nrm(text) {
		return (text || '').toString().toLowerCase().trim();
	}

	function matchesFilter(text, query) {
		if (!query) return true;
		return nrm(text).includes(query);
	}

	function setProgress(percent) {
		const safe = Math.max(0, Math.min(100, Number(percent || 0)));
		if (els.progFill) els.progFill.style.width = safe + '%';
		if (els.progPct) els.progPct.textContent = safe.toFixed(1) + '%';
	}

	function clearAnalysisFields() {
		if (els.editTitle) els.editTitle.value = '';
		if (els.editArtist) els.editArtist.value = '';
		if (els.editAlbum) els.editAlbum.value = '';
		if (els.editPlaylistArtist) els.editPlaylistArtist.value = '';
		if (els.editPlaylistAlbum) els.editPlaylistAlbum.value = '';
		if (els.editPlaylistYear) els.editPlaylistYear.value = '';
		if (els.playlistMode) els.playlistMode.checked = false;
		if (els.mp4Mode) els.mp4Mode.checked = false;
		if (els.playlistTitle) els.playlistTitle.textContent = '';
		renderPlaylistSongs([]);
		updateCoverPreview('');
		if (els.singleFields) els.singleFields.style.display = 'block';
		if (els.playlistFields) els.playlistFields.style.display = 'none';
	}

	function setAnalysisPanelActive(active) {
		if (!els.metadataPreview) return;
		analysisPanelActive = !!active;
		els.metadataPreview.classList.toggle('analysis-disabled', !active);

		const toggle = function (el, disabled) {
			if (!el) return;
			el.disabled = disabled;
		};

		toggle(els.editTitle, !active);
		toggle(els.editArtist, !active);
		toggle(els.editAlbum, !active);
		toggle(els.editPlaylistArtist, !active);
		toggle(els.editPlaylistAlbum, !active);
		toggle(els.editPlaylistYear, !active);
		toggle(els.playlistMode, !active);
		toggle(els.mp4Mode, !active);
		toggle(els.resetPreviewBtn, !active);
		syncDownloadButtonState();
	}

	function renderPlaylistSongs(songs) {
		if (!els.playlistSongList) return;
		if (!songs || songs.length === 0) {
			els.playlistSongList.innerHTML = '<div class="song-row">Aucun titre détecté.</div>';
			return;
		}
		els.playlistSongList.innerHTML = songs.map(function (song, idx) {
			const a = primaryArtist(song.artist || 'Unknown Artist');
			const t = asText(song.title, 'Unknown Title');
			return '<div class="song-row">' + (idx + 1) + '. ' + htmlEscape(a) + ' - ' + htmlEscape(t) + '</div>';
		}).join('');
	}

	function updateCoverPreview(urlOrCandidates) {
		if (!els.metaThumb || !els.metaThumbPlaceholder) return;

		const candidates = Array.isArray(urlOrCandidates)
			? urlOrCandidates.filter(Boolean)
			: (asText(urlOrCandidates, '') ? [asText(urlOrCandidates, '')] : []);

		if (!candidates.length) {
			els.metaThumb.onerror = null;
			els.metaThumb.onload = null;
			els.metaThumb.removeAttribute('src');
			els.metaThumb.style.display = 'none';
			els.metaThumbPlaceholder.style.display = 'block';
			return;
		}

		let idx = 0;
		const bust = Date.now();

		const tryNext = function () {
			if (idx >= candidates.length) {
				els.metaThumb.removeAttribute('src');
				els.metaThumb.style.display = 'none';
				els.metaThumbPlaceholder.style.display = 'block';
				return;
			}

			const base = candidates[idx];
			idx += 1;
			if (shouldCacheBust(base)) {
				const sep = base.includes('?') ? '&' : '?';
				els.metaThumb.src = base + sep + 't=' + bust + '_' + idx;
			} else {
				els.metaThumb.src = base;
			}
		};

		els.metaThumb.onload = function () {
			els.metaThumb.style.display = 'block';
			els.metaThumbPlaceholder.style.display = 'none';
		};

		els.metaThumb.onerror = function () {
			tryNext();
		};

		tryNext();
	}

	function appendRecent(itemMeta, finalPath) {
		if (!els.dlList) return;
		if (els.dlEmpty) els.dlEmpty.style.display = 'none';

		const artist = primaryArtist(itemMeta && itemMeta.artist || 'Unknown Artist');
		const title = asText(itemMeta && itemMeta.title, 'Unknown Title');
		const pathInfo = asText(finalPath, '');

		const node = document.createElement('div');
		node.className = 'dl-item';
		node.innerHTML = '<strong>' + htmlEscape(artist) + ' - ' + htmlEscape(title) + '</strong>' +
			(pathInfo ? '<div class="progress-subtext">' + htmlEscape(pathInfo) + '</div>' : '');
		els.dlList.prepend(node);
	}

	function bindDnDAndRename() {
		if (!els.libraryTree) return;

		els.libraryTree.querySelectorAll('details[data-folder-path] > summary').forEach(function (summaryEl) {
			summaryEl.addEventListener('click', function (ev) {
				if (ev.target && ev.target.closest && ev.target.closest('.folder-actions')) return;
				const details = summaryEl.parentElement;
				if (!details) return;
				selectedFolderPath = details.getAttribute('data-folder-path') || '';
				selectedFolderName = details.getAttribute('data-folder-name') || selectedFolderPath;
				updateSelectedFolderUI();
				highlightSelectedFolder();
			});
		});

		els.libraryTree.querySelectorAll('[data-song-path]').forEach(function (songEl) {
			songEl.addEventListener('dragstart', function (ev) {
				isDraggingLibrary = true;
				ev.dataTransfer.setData('text/plain', songEl.getAttribute('data-song-path') || '');
			});
			songEl.addEventListener('dragend', function () {
				isDraggingLibrary = false;
			});
		});

		els.libraryTree.querySelectorAll('[data-drop-folder]').forEach(function (folderEl) {
			folderEl.addEventListener('dragover', function (ev) {
				ev.preventDefault();
				folderEl.classList.add('drop-target');
			});
			folderEl.addEventListener('dragleave', function () {
				folderEl.classList.remove('drop-target');
			});
			folderEl.addEventListener('drop', async function (ev) {
				ev.preventDefault();
				folderEl.classList.remove('drop-target');
				const source = ev.dataTransfer.getData('text/plain');
				const target = folderEl.getAttribute('data-drop-folder');
				if (!source || !target) return;
				try {
					await window.api.moveSong(source, target);
					showAlert('Titre déplacé avec succès.', 'info');
					await refreshLibrary();
				} catch (err) {
					showAlert(err.message || 'Déplacement impossible.', 'error');
				}
			});
		});

		els.libraryTree.querySelectorAll('[data-rename-folder]').forEach(function (btn) {
			btn.addEventListener('click', async function () {
				const folderPath = btn.getAttribute('data-rename-folder') || '';
				const currentName = btn.getAttribute('data-folder-name') || '';
				const newName = window.prompt('Nouveau nom du dossier :', currentName);
				if (!newName || newName.trim() === '' || newName.trim() === currentName) return;
				try {
					await window.api.renameFolder(folderPath, newName.trim());
					showAlert('Dossier renommé.', 'info');
					await refreshLibrary();
				} catch (err) {
					showAlert(err.message || 'Renommage impossible.', 'error');
				}
			});
		});
	}

	function updateSelectedFolderUI() {
		if (!els.librarySelectedFolder) return;
		if (!selectedFolderPath) {
			els.librarySelectedFolder.textContent = 'Dossier cible: aucun dossier sélectionné';
			updateLibraryFolderCover();
			return;
		}
		els.librarySelectedFolder.textContent = 'Dossier cible: ' + selectedFolderName;
		updateLibraryFolderCover();
	}

	function updateLibraryFolderCover() {
		if (!els.libraryFolderCover || !els.libraryFolderCoverPlaceholder) return;
		if (!selectedFolderPath) {
			els.libraryFolderCover.style.display = 'none';
			els.libraryFolderCover.removeAttribute('src');
			els.libraryFolderCoverPlaceholder.style.display = 'block';
			els.libraryFolderCoverPlaceholder.textContent = 'Aucune pochette détectée';
			return;
		}

		const url = window.api.getFolderCoverUrl(selectedFolderPath);
		els.libraryFolderCover.onload = function () {
			els.libraryFolderCover.style.display = 'block';
			els.libraryFolderCoverPlaceholder.style.display = 'none';
		};
		els.libraryFolderCover.onerror = function () {
			els.libraryFolderCover.style.display = 'none';
			els.libraryFolderCoverPlaceholder.style.display = 'block';
			els.libraryFolderCoverPlaceholder.textContent = 'Aucune pochette détectée';
		};
		els.libraryFolderCover.src = url;
	}

	function highlightSelectedFolder() {
		if (!els.libraryTree) return;
		els.libraryTree.querySelectorAll('details.selected-folder').forEach(function (d) {
			d.classList.remove('selected-folder');
		});
		if (!selectedFolderPath) return;
		const escaped = selectedFolderPath.replaceAll('"', '\\"');
		const el = els.libraryTree.querySelector('details[data-folder-path="' + escaped + '"]');
		if (el) el.classList.add('selected-folder');
	}

	async function uploadImageToSelectedFolder(file) {
		if (!selectedFolderPath) {
			showAlert('Sélectionne d\'abord un dossier dans la bibliothèque.', 'error');
			return;
		}
		if (!file) {
			showAlert('Aucun fichier image sélectionné.', 'error');
			return;
		}
		try {
			const res = await window.api.uploadLibraryImage(file, selectedFolderPath);
			showAlert('Image ajoutée dans ' + selectedFolderName + '.', 'info');
			return res;
		} catch (err) {
			showAlert(err.message || 'Upload image impossible.', 'error');
		}
	}

	function getExpandedFolders() {
		if (!els.libraryTree) return {};
		const map = {};
		els.libraryTree.querySelectorAll('details[data-node-path]').forEach(function (d) {
			map[d.getAttribute('data-node-path')] = !!d.open;
		});
		return map;
	}

	function restoreExpandedFolders(expanded) {
		if (!els.libraryTree || !expanded) return;
		els.libraryTree.querySelectorAll('details[data-node-path]').forEach(function (d) {
			const key = d.getAttribute('data-node-path');
			if (Object.prototype.hasOwnProperty.call(expanded, key)) {
				d.open = !!expanded[key];
			}
		});
	}

	function bindLibraryToolbar() {
		if (els.librarySearch) {
			els.librarySearch.addEventListener('input', function () {
				libraryFilter = nrm(els.librarySearch.value);
				refreshLibrary();
			});
		}

		if (els.libExpandAll) {
			els.libExpandAll.addEventListener('click', function () {
				if (!els.libraryTree) return;
				els.libraryTree.querySelectorAll('details').forEach(function (d) {
					d.open = true;
				});
			});
		}

		if (els.libCollapseAll) {
			els.libCollapseAll.addEventListener('click', function () {
				if (!els.libraryTree) return;
				els.libraryTree.querySelectorAll('details').forEach(function (d) {
					d.open = false;
				});
			});
		}
	}

	function renderLibrary(tree, expanded) {
		if (!els.libraryTree) return;
		const q = libraryFilter;
		const artists = (tree && tree.artists) || [];
		const playlists = (tree && tree.playlists) || [];
		if (artists.length === 0 && playlists.length === 0) {
			els.libraryTree.innerHTML = '<div class="empty-state-text">Aucune musique dans la bibliothèque.</div>';
			return;
		}

		const artistBlocks = [];
		artists.forEach(function (artist) {
			const albumBlocks = [];
			let artistSongCount = 0;
			(artist.albums || []).forEach(function (album) {
				const songs = (album.songs || []).filter(function (song) {
					const hay = [artist.name, album.name, song.name].join(' ');
					return matchesFilter(hay, q);
				});
				if (!songs.length && q && !matchesFilter(artist.name + ' ' + album.name, q)) return;
				artistSongCount += songs.length;
				const songHtml = songs.map(function (song) {
					return '<div class="song-item lib-song-row" draggable="true" data-song-path="' + htmlEscape(song.path) + '">' +
						'<span class="lib-song-name">' + htmlEscape(song.name) + '</span>' +
						'<span class="lib-drag-hint">drag</span>' +
					'</div>';
				}).join('');

				albumBlocks.push(
					'<details data-drop-folder="' + htmlEscape(album.path) + '" data-folder-path="' + htmlEscape(album.path) + '" data-folder-name="' + htmlEscape(album.name) + '" data-node-path="' + htmlEscape(album.path) + '">' +
						'<summary><div class="lib-summary-row"><span class="lib-summary-left"><span class="lib-caret">▾</span><span class="lib-icon">💿</span><span class="lib-name">' + htmlEscape(album.name) + '</span><span class="lib-count">' + songs.length + '</span></span><button type="button" class="folder-actions" data-rename-folder="' + htmlEscape(album.path) + '" data-folder-name="' + htmlEscape(album.name) + '">✏️</button></div></summary>' +
						songHtml +
					'</details>'
				);
			});

			if (!albumBlocks.length) return;
			artistBlocks.push(
				'<details data-folder-path="' + htmlEscape(artist.path) + '" data-folder-name="' + htmlEscape(artist.name) + '" data-node-path="' + htmlEscape(artist.path) + '">' +
					'<summary><div class="lib-summary-row"><span class="lib-summary-left"><span class="lib-caret">▾</span><span class="lib-icon">🎤</span><span class="lib-name">' + htmlEscape(artist.name) + '</span><span class="lib-count">' + artistSongCount + '</span></span><button type="button" class="folder-actions" data-rename-folder="' + htmlEscape(artist.path) + '" data-folder-name="' + htmlEscape(artist.name) + '">✏️</button></div></summary>' +
					albumBlocks.join('') +
				'</details>'
			);
		});

		const playlistBlocks = [];
		playlists.forEach(function (pl) {
			const songs = (pl.songs || []).filter(function (song) {
				const hay = [pl.name, song.name].join(' ');
				return matchesFilter(hay, q);
			});
			if (!songs.length && q && !matchesFilter(pl.name, q)) return;
			const songHtml = songs.map(function (song) {
				return '<div class="song-item lib-song-row" draggable="true" data-song-path="' + htmlEscape(song.path) + '">' +
					'<span class="lib-song-name">' + htmlEscape(song.name) + '</span>' +
					'<span class="lib-drag-hint">drag</span>' +
				'</div>';
			}).join('');

			playlistBlocks.push(
				'<details data-drop-folder="' + htmlEscape(pl.path) + '" data-folder-path="' + htmlEscape(pl.path) + '" data-folder-name="' + htmlEscape(pl.name) + '" data-node-path="' + htmlEscape(pl.path) + '">' +
					'<summary><div class="lib-summary-row"><span class="lib-summary-left"><span class="lib-caret">▾</span><span class="lib-icon">📁</span><span class="lib-name">' + htmlEscape(pl.name) + '</span><span class="lib-count">' + songs.length + '</span></span><button type="button" class="folder-actions" data-rename-folder="' + htmlEscape(pl.path) + '" data-folder-name="' + htmlEscape(pl.name) + '">✏️</button></div></summary>' +
					songHtml +
				'</details>'
			);
		});

		const artistHtml = artistBlocks.join('');
		const playlistHtml = playlistBlocks.join('');
		if (!artistHtml && !playlistHtml) {
			els.libraryTree.innerHTML = '<div class="empty-state-text">Aucun résultat pour cette recherche.</div>';
			return;
		}

		els.libraryTree.innerHTML = artistHtml + playlistHtml;
		restoreExpandedFolders(expanded);
		if (q) {
			els.libraryTree.querySelectorAll('details').forEach(function (d) { d.open = true; });
		}
		bindDnDAndRename();
		highlightSelectedFolder();
	}

	async function refreshLibrary() {
		if (isDraggingLibrary) {
			return;
		}
		try {
			const expanded = getExpandedFolders();
			const data = await window.api.getLibrary();
			renderLibrary(data, expanded);
		} catch (_) {
			if (els.libraryTree && !els.libraryTree.innerHTML) {
				els.libraryTree.innerHTML = '<div class="empty-state-text">Impossible de charger la bibliothèque.</div>';
			}
		}
	}

	async function extract() {
		clearAlert();
		const url = (els.url && els.url.value || '').trim();
		if (!url) {
			showAlert('Colle un lien YouTube Music.', 'error');
			return;
		}

		try {
			await cancelCurrentPrefetch();
			currentUrl = url;
			const data = await window.api.extract(url);
			currentExtract = data;
			if (!data.success) {
				showAlert(data.error || 'Extraction impossible.', 'error');
				return;
			}
			if (els.url) els.url.value = '';

			const isPlaylist = !!data.is_playlist;
			if (isPlaylist) {
				if (els.singleFields) els.singleFields.style.display = 'none';
				if (els.playlistFields) els.playlistFields.style.display = 'block';
				const detectedArtist = inferPlaylistArtist(data);
				if (els.playlistTitle) els.playlistTitle.textContent = '';
				if (els.playlistMetaSummary) {
					const songsCount = Number(data.total_songs || (data.songs || []).length || 0);
					els.playlistMetaSummary.textContent = 'Album: ' + asText(data.title, 'Playlist') + ' | Artiste: ' + detectedArtist + ' | Titres: ' + songsCount;
				}
				if (els.editPlaylistArtist) els.editPlaylistArtist.value = detectedArtist;
				if (els.editPlaylistAlbum) els.editPlaylistAlbum.value = asText(data.title, 'Unknown Album');
				if (els.editPlaylistYear) els.editPlaylistYear.value = asText(data.year, '');
				renderPlaylistSongs(data.songs || []);
				const coverCandidates = resolveCoverCandidates(data);
				updateCoverPreview(coverCandidates);
				currentPrefetchToken = asText(data.prefetch_token, '');
				if (currentPrefetchToken) {
					startPrefetchCoverPolling(currentPrefetchToken, coverCandidates);
				}
			} else {
				stopPrefetchCoverPolling();
				currentPrefetchToken = '';
				if (els.playlistFields) els.playlistFields.style.display = 'none';
				if (els.singleFields) els.singleFields.style.display = 'block';
				if (els.playlistMetaSummary) els.playlistMetaSummary.textContent = '—';
				if (els.editTitle) els.editTitle.value = asText(data.title, 'Unknown Title');
				if (els.editArtist) els.editArtist.value = primaryArtist(data.artist);
				if (els.editAlbum) els.editAlbum.value = asText(data.album, 'Unknown Album');
				renderPlaylistSongs([]);
				updateCoverPreview(resolveCoverCandidates(data));
			}

			setAnalysisPanelActive(true);
			showAlert('Metadonnees chargees. Tu peux ajuster puis telecharger.', 'info');
		} catch (err) {
			showAlert(err.message || 'Erreur extraction.', 'error');
		}
	}

	async function download() {
		if (!currentUrl) {
			showAlert('Commence par analyser un lien.', 'error');
			return;
		}

		try {
			const playlistMode = !!(els.playlistMode && els.playlistMode.checked);
			const mp4Mode = !!(els.mp4Mode && els.mp4Mode.checked);
			if (mp4Mode) {
				showAlert('Mode MP4 en préparation. Téléchargement lancé en MP3 pour le moment.', 'info');
			}
			let res;
			if (currentExtract && currentExtract.is_playlist) {
				res = await window.api.downloadPlaylist({
					url: currentUrl,
					playlist_mode: playlistMode,
					mp4_mode: mp4Mode,
					playlist_metadata: {
						title: asText(els.editPlaylistAlbum && els.editPlaylistAlbum.value, 'Unknown Album'),
						artist: asText(els.editPlaylistArtist && els.editPlaylistArtist.value, 'Unknown Artist'),
						year: asText(els.editPlaylistYear && els.editPlaylistYear.value, ''),
						songs: currentExtract.songs || [],
					},
				});
			} else {
				res = await window.api.download({
					url: currentUrl,
					playlist_mode: playlistMode,
					mp4_mode: mp4Mode,
					title: asText(els.editTitle && els.editTitle.value, 'Unknown Title'),
					artist: asText(els.editArtist && els.editArtist.value, 'Unknown Artist'),
					album: asText(els.editAlbum && els.editAlbum.value, 'Unknown Album'),
					year: '',
				});
			}

			if (!res.success) {
				showAlert(res.error || 'Echec du telechargement.', 'error');
				return;
			}
			stopPrefetchCoverPolling();
			currentPrefetchToken = '';
			showAlert('Ajouté à la file de téléchargement.', 'info');
			setAnalysisPanelActive(false);
			clearAnalysisFields();
			currentExtract = null;
			currentUrl = '';
			if (els.progZone) els.progZone.style.display = 'block';
			await refreshLibrary();
		} catch (err) {
			showAlert(err.message || 'Erreur telechargement.', 'error');
		}
	}

	async function pollStatus() {
		try {
			const st = await window.api.getStatus();
			if (!els.progStatus || !els.progPct) return;

			const batchPercent = Number(st.batch_percent || 0);
			const active = !!st.in_progress || Number(st.queue_size || 0) > 0 || !!st.batch_active;
			workerBusy = active;
			syncDownloadButtonState();
			if (active && els.progZone) {
				els.progZone.style.display = 'block';
			}
			if (!active) {
				setProgress(0);
				if (els.progStatus) els.progStatus.textContent = 'En attente...';
				if (els.progSubtext) els.progSubtext.textContent = '0 / 0 titre';
				if (els.progZone) els.progZone.style.display = 'none';
			}
			setProgress(batchPercent);

			const current = (st.current_download && st.current_download.metadata) || {};
			const currArtist = primaryArtist(current.artist || 'Unknown Artist');
			const currTitle = asText(current.title, 'En attente...');
			if (active) {
				els.progStatus.textContent = currArtist ? (currArtist + ' - ' + currTitle) : currTitle;
			}

			const total = Number(st.batch_total || 0);
			const done = Number(st.batch_done || 0);
			if (els.progSubtext) {
				els.progSubtext.textContent = done + ' / ' + total + ' titre' + (total > 1 ? 's' : '');
			}

			if (st.last_completed && st.last_completed.timestamp && st.last_completed.timestamp !== lastCompletedTimestamp) {
				lastCompletedTimestamp = st.last_completed.timestamp;
				appendRecent(st.last_completed.metadata || {}, st.last_completed.file_path || '');
				refreshLibrary();
			}
		} catch (_) {
			// Ignore temporary polling errors.
		}
	}

	window.onPlaylistModeChange = function () {};
	window.resetPreview = async function () {
		await cancelCurrentPrefetch();
		currentExtract = null;
		currentUrl = '';
		clearAnalysisFields();
		setAnalysisPanelActive(false);
	};
	window.cleanupTemp = async function () {
		try {
			const res = await window.api.cleanup();
			showAlert('Nettoyage termine (' + (res.deleted || 0) + ' fichiers).', 'info');
		} catch (err) {
			showAlert(err.message || 'Erreur nettoyage.', 'error');
		}
	};
	window.downloadRecentFiles = function () {
		(async function () {
			try {
				const res = await window.api.prepareAdminZip();
				if (!res.success) {
					showAlert(res.error || 'Impossible de créer le ZIP.', 'error');
					return;
				}
				showAlert('ZIP prêt: ' + res.count + ' fichiers (' + res.size_mb + ' MB). Téléchargement en cours...', 'info');
				window.location.href = (res.download_url || '/api/admin/download-zip') + '?t=' + Date.now();
			} catch (err) {
				showAlert(err.message || 'Erreur ZIP admin.', 'error');
			}
		})();
	};
	window.keepOnNAS = function () {
		const modal = document.getElementById('download-complete-modal');
		if (modal) modal.style.display = 'none';
	};
	window.downloadAndDelete = function () {
		showAlert('Action non disponible pour le moment.', 'info');
	};

	if (els.btnUploadFolderImage) {
		els.btnUploadFolderImage.addEventListener('click', async function () {
			const file = els.libraryImageFile && els.libraryImageFile.files ? els.libraryImageFile.files[0] : null;
			await uploadImageToSelectedFolder(file);
			updateLibraryFolderCover();
			if (els.libraryImageFile) els.libraryImageFile.value = '';
		});
	}

	window.addEventListener('paste', async function (ev) {
		const cd = ev.clipboardData;
		if (!cd || !cd.items) return;
		for (let i = 0; i < cd.items.length; i += 1) {
			const item = cd.items[i];
			if (!item || item.kind !== 'file') continue;
			const file = item.getAsFile();
			if (!file || !(file.type || '').startsWith('image/')) continue;
			ev.preventDefault();
			await uploadImageToSelectedFolder(file);
			break;
		}
	});

	if (els.extractBtn) els.extractBtn.addEventListener('click', extract);
	if (els.dlBtn) els.dlBtn.addEventListener('click', download);
	bindLibraryToolbar();
	updateSelectedFolderUI();
	clearAnalysisFields();
	setAnalysisPanelActive(false);
	refreshLibrary();
	pollStatus();
	setInterval(pollStatus, 1500);
})();