<script>
	import { onMount, tick } from 'svelte';
	import { api } from '$lib/api.js';
	import { nrm } from '$lib/utils.js';
	import { addToast, user, confirmAction, helpOpen } from '$lib/stores.js';
	import Header from '$lib/components/Header.svelte';

	// ── Library tree ──────────────────────────────────────────────────────────────
	let tree = null;
	let filter = '';
	let expanded = new Set();

	// ── Persistance navigation (sidebar, arborescence, sélection) ────────────────
	const LS_EXPANDED = 'ssf.meta.expanded';
	const LS_SIDEBAR  = 'ssf.meta.sidebar';
	const LS_SEL      = 'ssf.meta.sel';
	const LS_TREE     = 'ssf.meta.tree';
	const LS_HOME_SCROLL = 'ssf.meta.homeScroll';

	// Position de scroll de la galerie d'artistes (page d'accueil de /metadata) :
	// restaurée après un remount (ex: aller sur Téléchargement puis revenir).
	let metaMainEl;
	let homeScrollSaveTimer = null;

	function saveHomeScroll() {
		if (selectedType !== null || !metaMainEl) return;
		clearTimeout(homeScrollSaveTimer);
		homeScrollSaveTimer = setTimeout(() => {
			try { localStorage.setItem(LS_HOME_SCROLL, String(metaMainEl.scrollTop)); } catch { /* ignore */ }
		}, 150);
	}

	async function restoreHomeScroll() {
		await tick();
		if (selectedType !== null || !metaMainEl) return;
		let y = 0;
		try { y = parseInt(localStorage.getItem(LS_HOME_SCROLL) || '0', 10) || 0; } catch { /* ignore */ }
		metaMainEl.scrollTop = y;
	}

	function persistTree() {
		try { localStorage.setItem(LS_TREE, JSON.stringify(tree)); } catch { /* ignore */ }
	}

	let sidebarCollapsed = false;

	function toggleSidebar() {
		sidebarCollapsed = !sidebarCollapsed;
		try { localStorage.setItem(LS_SIDEBAR, sidebarCollapsed ? '1' : '0'); } catch { /* ignore */ }
	}

	function persistExpanded() {
		try { localStorage.setItem(LS_EXPANDED, JSON.stringify([...expanded])); } catch { /* ignore */ }
	}

	function persistSelection(sel) {
		try {
			if (sel) localStorage.setItem(LS_SEL, JSON.stringify(sel));
			else localStorage.removeItem(LS_SEL);
		} catch { /* ignore */ }
	}

	// ── Selection ─────────────────────────────────────────────────────────────────
	// selectedType: null | 'artist' | 'album' | 'song'
	let selectedType   = null;
	let selectedArtist = null; // { path, name }
	let selectedAlbum  = null; // { path, name, songs[], artist: { path, name } }
	let selectedPath   = '';   // song relative path

	// ── Song panel state ──────────────────────────────────────────────────────────
	let meta          = null;
	let metaLoading   = false;
	let metaError     = '';
	let detailsOpen   = false;

	// ── Editing ───────────────────────────────────────────────────────────────────
	let editValues       = {};
	let dirty            = false;
	let saving           = false;
	let saveError        = '';
	let lastEditedField  = null;  // tracks the most-recently-modified field
	let applyingToAlbum  = false;

	// ── Cover upload ──────────────────────────────────────────────────────────────
	let uploadingCover      = false;
	let coverError          = '';
	let coverTs             = Date.now();

	// ── Album panel state ─────────────────────────────────────────────────────────
	let albumCoverTs        = Date.now();
	let uploadingAlbumCover = false;

	// ── Artist panel state ────────────────────────────────────────────────────────
	let artistPicTs     = Date.now();
	let artistTs        = Date.now(); // cache buster for album grid covers
	let artistPicMissing = false;     // true when artist picture fails to load
	let uploadingArtist = false;

	// ── Renumérotation album (mode « Numéroter les pistes ») ─────────────────────
	let reorderMode    = false;
	let reorderTracks  = [];   // [{path, name, title, track_number}]
	let reorderLoading = false;
	let reorderSaving  = false;
	let reorderDragIdx = -1;

	function resetReorder() {
		reorderMode = false; reorderTracks = []; reorderDragIdx = -1;
	}

	async function enterReorder() {
		if (!selectedAlbum || reorderLoading) return;
		reorderLoading = true;
		try {
			const data = await api.albumTracks(selectedAlbum.path);
			const tracks = data.tracks ?? [];
			// Pistes numérotées d'abord (par TRCK), puis les sans-numéro (alpha)
			const num   = (t) => parseInt(String(t.track_number).split('/')[0], 10);
			const numbered   = tracks.filter((t) => !isNaN(num(t))).sort((a, b) => num(a) - num(b));
			const unnumbered = tracks.filter((t) => isNaN(num(t)));
			reorderTracks = [...numbered, ...unnumbered];
			reorderMode = true;
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { reorderLoading = false; }
	}

	function moveTrack(i, delta) {
		const j = i + delta;
		if (j < 0 || j >= reorderTracks.length) return;
		const arr = [...reorderTracks];
		[arr[i], arr[j]] = [arr[j], arr[i]];
		reorderTracks = arr;
	}

	function reorderDragStart(e, i) {
		reorderDragIdx = i;
		e.dataTransfer.effectAllowed = 'move';
	}

	function reorderDragOver(e, i) {
		e.preventDefault();
		if (reorderDragIdx === -1 || i === reorderDragIdx) return;
		const arr = [...reorderTracks];
		const [moved] = arr.splice(reorderDragIdx, 1);
		arr.splice(i, 0, moved);
		reorderTracks = arr;
		reorderDragIdx = i;
	}

	function reorderDragEnd() { reorderDragIdx = -1; }

	async function saveReorder() {
		if (reorderSaving || reorderTracks.length === 0) return;
		reorderSaving = true;
		try {
			const res = await api.renumberAlbum(selectedAlbum.path, reorderTracks.map((t) => t.path));
			addToast(`Album numéroté 1 à ${res.total}.`, 'info');
			resetReorder();
			loadAlbumPanelTracks(selectedAlbum.path);
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { reorderSaving = false; }
	}

	// ── Audit métadonnées (admin) ─────────────────────────────────────────────────
	let audit         = null;       // rapport /api/admin/audit/artist
	let auditLoading  = false;
	let auditError    = '';
	let auditSelected = new Set();  // ids des recommandations cochées
	let auditApplying = false;

	$: isAdmin = $user?.role === 'admin';

	function resetAudit() {
		audit = null; auditError = ''; auditSelected = new Set();
	}

	async function runAudit() {
		if (!selectedArtist || auditLoading) return;
		auditLoading = true; auditError = ''; audit = null;
		try {
			const data = await api.auditArtist(selectedArtist.path);
			audit = data;
			auditSelected = new Set(
				(data.albums ?? []).flatMap((al) => (al.recommendations ?? []).map((r) => r.id))
			);
		} catch (e) { auditError = e.message ?? 'Erreur'; }
		finally { auditLoading = false; }
	}

	function toggleRec(id) {
		if (auditSelected.has(id)) auditSelected.delete(id);
		else auditSelected.add(id);
		auditSelected = new Set(auditSelected);
	}

	$: auditChanges = !audit ? [] : (audit.albums ?? []).flatMap((al) =>
		(al.recommendations ?? [])
			.filter((r) => auditSelected.has(r.id))
			.flatMap((r) => (r.changes ?? []).map((c) => ({ path: c.path, field: r.field, value: c.value })))
	);

	async function applyAudit() {
		if (auditChanges.length === 0 || auditApplying) return;
		auditApplying = true;
		try {
			const res = await api.auditApply(auditChanges);
			if ((res.errors ?? []).length === 0) {
				addToast(`${res.applied} tag${res.applied > 1 ? 's' : ''} appliqué${res.applied > 1 ? 's' : ''}.`, 'info');
			} else {
				addToast(`${res.applied} OK, ${res.errors.length} erreur${res.errors.length > 1 ? 's' : ''}.`, 'error');
			}
			await runAudit();
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { auditApplying = false; }
	}

	// ── Suppression de dossier (admin — la bibliothèque admin est permanente) ────
	let deletingFolder = false;

	async function deleteArtistFolder() {
		if (!selectedArtist || deletingFolder) return;
		const nSongs = artistAlbums.reduce((n, al) => n + al.songs.length, 0);
		const ok = await confirmAction({
			title: `Supprimer « ${selectedArtist.name} » ?`,
			message: `${artistAlbums.length} album${artistAlbums.length > 1 ? 's' : ''}, ${nSongs} titre${nSongs > 1 ? 's' : ''} seront supprimés.\n`
				+ 'Cette action est irréversible.',
			confirmLabel: 'Supprimer',
			danger: true,
		});
		if (!ok) return;
		deletingFolder = true;
		try {
			const res = await api.deleteFolder(selectedArtist.path);
			addToast(`Dossier supprimé (${res.deleted_songs} titre${res.deleted_songs > 1 ? 's' : ''}).`, 'info');
			goHome();
			await refreshTree();
		} catch (e) { addToast(e.message ?? 'Suppression impossible.', 'error'); }
		finally { deletingFolder = false; }
	}

	async function deleteAlbumFolder() {
		if (!selectedAlbum || deletingFolder) return;
		const artistPath = selectedAlbum.artist.path;
		const nSongs = selectedAlbum.songs.length;
		const ok = await confirmAction({
			title: `Supprimer l'album « ${selectedAlbum.name} » ?`,
			message: `${nSongs} titre${nSongs > 1 ? 's' : ''} seront supprimés.\nCette action est irréversible.`,
			confirmLabel: 'Supprimer',
			danger: true,
		});
		if (!ok) return;
		deletingFolder = true;
		try {
			const res = await api.deleteFolder(selectedAlbum.path);
			addToast(`Album supprimé (${res.deleted_songs} titre${res.deleted_songs > 1 ? 's' : ''}).`, 'info');
			await refreshTree();
			gotoArtistByPath(artistPath); // retombe sur l'accueil si l'artiste a disparu (dernier album)
		} catch (e) { addToast(e.message ?? 'Suppression impossible.', 'error'); }
		finally { deletingFolder = false; }
	}

	// ── Drag and drop ─────────────────────────────────────────────────────────────
	let dndType      = ''; // 'song' | 'album'
	let dndSongPath  = '';
	let dndAlbumPath = '';

	function dndStart(e, path, type) {
		dndType = type;
		if (type === 'song')  dndSongPath  = path;
		else                  dndAlbumPath = path;
		e.dataTransfer.effectAllowed = 'move';
		e.dataTransfer.setData('text/plain', path);
	}

	function dndEnd() { dndType = ''; dndSongPath = ''; dndAlbumPath = ''; }

	function dndOverAlbum(e) {
		if (dndType !== 'song') return;
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	function dndOverArtist(e) {
		if (dndType !== 'album') return;
		e.preventDefault();
		e.currentTarget.classList.add('drop-target');
	}

	function dndLeave(e) {
		if (e.relatedTarget && e.currentTarget.contains(e.relatedTarget)) return;
		e.currentTarget.classList.remove('drop-target');
	}

	async function dndDropOnAlbum(e, albumPath) {
		e.preventDefault();
		e.currentTarget.classList.remove('drop-target');
		if (dndType !== 'song') return;
		const source = e.dataTransfer.getData('text/plain') || dndSongPath;
		if (!source || !albumPath) return;
		try {
			await api.moveSong(source, albumPath);
			addToast('Titre déplacé.', 'info');
			if (source === selectedPath) { selectedType = null; selectedPath = ''; meta = null; }
			await refreshTree();
		} catch (err) { addToast(err.message || 'Déplacement impossible.', 'error'); }
	}

	async function dndDropOnArtist(e, artistPath) {
		e.preventDefault();
		e.currentTarget.classList.remove('drop-target');
		if (dndType !== 'album') return;
		const source = e.dataTransfer.getData('text/plain') || dndAlbumPath;
		if (!source || !artistPath) return;
		try {
			await api.moveFolder(source, artistPath);
			addToast('Album déplacé.', 'info');
			if (selectedAlbum?.path === source) { selectedType = null; selectedAlbum = null; }
			await refreshTree();
		} catch (err) { addToast(err.message || 'Déplacement impossible.', 'error'); }
	}

	async function refreshTree() {
		try {
			const data = await api.getLibrary();
			tree = data;
			persistTree();
			// Keep selectedAlbum songs in sync if the album still exists
			if (selectedAlbum) {
				const newArtist = (data.artists ?? []).find(a => a.path === selectedAlbum.artist.path);
				const newAlbum  = newArtist?.albums?.find(a => a.path === selectedAlbum.path);
				if (newAlbum) selectedAlbum = { ...selectedAlbum, songs: newAlbum.songs };
				else { selectedType = null; selectedAlbum = null; }
			}
		} catch { /* ignore */ }
	}

	// ── Lifecycle ─────────────────────────────────────────────────────────────────
	onMount(async () => {
		try { sidebarCollapsed = localStorage.getItem(LS_SIDEBAR) === '1'; } catch { /* ignore */ }
		try { expanded = new Set(JSON.parse(localStorage.getItem(LS_EXPANDED) || '[]')); } catch { /* ignore */ }

		// Stale-while-revalidate : affiche le dernier arbre connu pendant le fetch
		let cached = null;
		try { cached = JSON.parse(localStorage.getItem(LS_TREE) || 'null'); } catch { /* ignore */ }
		if (cached?.artists) {
			tree = cached;
			restoreSelection();
			restoreHomeScroll();
		}

		try {
			const fresh = await api.getLibrary();
			// Si rien n'a changé depuis le cache, on garde l'affichage tel quel
			if (!cached?.artists || JSON.stringify(fresh) !== JSON.stringify(cached)) {
				tree = fresh;
				persistTree();
				// Re-résout la sélection contre l'arbre frais (les objets du cache sont périmés)
				restoreSelection();
				restoreHomeScroll();
			}
		} catch {
			if (!tree) tree = { artists: [], playlists: [] };
		}
	});

	function restoreSelection() {
		let sel = null;
		try { sel = JSON.parse(localStorage.getItem(LS_SEL) || 'null'); } catch { /* ignore */ }
		if (!sel || !tree) return;
		if (sel.type === 'artist') {
			gotoArtistByPath(sel.path);
		} else if (sel.type === 'album') {
			gotoAlbumByPath(sel.artistPath, sel.path);
		} else if (sel.type === 'song' && songExistsInTree(sel.path)) {
			selectSong(sel.path);
		}
	}

	function songExistsInTree(path) {
		const all = [
			...(tree?.artists ?? []).flatMap((a) => (a.albums ?? []).flatMap((al) => al.songs ?? [])),
			...(tree?.playlists ?? []).flatMap((pl) => pl.songs ?? []),
		];
		return all.some((s) => s.path === path);
	}

	// ── Breadcrumb navigation ─────────────────────────────────────────────────────
	function gotoArtistByPath(p) {
		const a = (tree?.artists ?? []).find((x) => x.path === p);
		if (a) selectArtist(a);
	}

	function gotoAlbumByPath(artistPath, albumPath) {
		const a  = (tree?.artists ?? []).find((x) => x.path === artistPath);
		const al = a?.albums?.find((x) => x.path === albumPath);
		if (a && al) selectAlbum(al, a);
	}

	// Segments du fil d'Ariane pour la vue titre (déduits du chemin du fichier)
	$: songCrumbParts = selectedType === 'song' && selectedPath ? selectedPath.split('/') : [];

	// ── Selection helpers ─────────────────────────────────────────────────────────
	function toggleExpand(path) {
		if (expanded.has(path)) expanded.delete(path);
		else expanded.add(path);
		expanded = expanded;
		persistExpanded();
	}

	// ── Statut de complétude des albums (badges vue artiste) ─────────────────────
	let artistAlbumStatus = {};  // album path → {tracks, missing: {genre, year, track_number}, complete}

	async function loadArtistAlbumStatus(artistPath) {
		artistAlbumStatus = {};
		try {
			const data = await api.albumStatus(artistPath);
			if (selectedArtist?.path !== artistPath) return; // sélection changée entre-temps
			artistAlbumStatus = Object.fromEntries((data.albums ?? []).map((a) => [a.path, a]));
			prefillArtistGenre();
		} catch { /* badges absents, pas bloquant */ }
	}

	function statusTooltip(st) {
		const parts = [];
		if (st.missing.genre)        parts.push(`genre (${st.missing.genre})`);
		if (st.missing.year)         parts.push(`année (${st.missing.year})`);
		if (st.missing.track_number) parts.push(`n° de piste (${st.missing.track_number})`);
		return parts.length ? `Manque : ${parts.join(', ')}` : 'Tags complets';
	}

	// ── Genre artiste (TCON réécrit sur tous les albums) ──────────────────────────
	let artistGenre        = '';
	let artistGenreTouched = false; // saisie manuelle en cours → ne pas écraser par le pré-remplissage
	let artistGenreSaving  = false;

	// Pré-remplit avec la combinaison de genres la plus fréquente parmi les albums.
	function prefillArtistGenre() {
		if (artistGenreTouched) return;
		const counts = new Map();
		for (const st of Object.values(artistAlbumStatus)) {
			const g = (st.genres ?? []).join('; ');
			if (g) counts.set(g, (counts.get(g) ?? 0) + 1);
		}
		artistGenre = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '';
	}

	async function applyArtistGenre() {
		const genre = artistGenre.trim();
		if (!selectedArtist || !genre || artistGenreSaving) return;
		const nSongs = artistAlbums.reduce((n, al) => n + al.songs.length, 0);
		const ok = await confirmAction({
			title: `Appliquer « ${genre} » ?`,
			message: `Le genre (TCON) sera réécrit sur les ${nSongs} titre${nSongs > 1 ? 's' : ''} `
				+ `des ${artistAlbums.length} album${artistAlbums.length > 1 ? 's' : ''} de ${selectedArtist.name}.`,
			confirmLabel: 'Appliquer',
		});
		if (!ok) return;
		artistGenreSaving = true;
		try {
			const res = await api.setArtistGenre(selectedArtist.path, genre);
			if ((res.errors ?? []).length === 0) {
				addToast(`Genre appliqué à ${res.updated} titre${res.updated > 1 ? 's' : ''}.`, 'info');
			} else {
				addToast(`${res.updated} OK, ${res.errors.length} erreur${res.errors.length > 1 ? 's' : ''}.`, 'error');
			}
			artistGenreTouched = false;
			loadArtistAlbumStatus(selectedArtist.path); // rafraîchit badges + pré-remplissage
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { artistGenreSaving = false; }
	}

	// ── Vraie tracklist du panneau album (TRCK réels) ─────────────────────────────
	let albumPanelTracks  = null;   // [{path, name, title, track_number}] triés par TRCK
	let albumTracksLoading = false; // true pendant la lecture des tags réels (évite d'afficher l'ordre alpha puis de le remplacer)

	function sortByTrck(tracks) {
		const num = (t) => parseInt(String(t.track_number).split('/')[0], 10);
		const numbered   = tracks.filter((t) => !isNaN(num(t))).sort((a, b) => num(a) - num(b));
		const unnumbered = tracks.filter((t) => isNaN(num(t)));
		return [...numbered, ...unnumbered];
	}

	async function loadAlbumPanelTracks(albumPath) {
		albumPanelTracks   = null;
		albumTracksLoading = true;
		try {
			const data = await api.albumTracks(albumPath);
			if (selectedAlbum?.path !== albumPath) return;
			albumPanelTracks = sortByTrck(data.tracks ?? []);
		} catch { albumPanelTracks = null; /* repli : ordre alphabétique si l'appel échoue */ }
		finally {
			if (selectedAlbum?.path === albumPath) albumTracksLoading = false;
		}
	}

	function trackDisplayNum(t) {
		const n = parseInt(String(t.track_number).split('/')[0], 10);
		return isNaN(n) ? '—' : String(n);
	}

	function selectArtist(artist) {
		selectedType   = 'artist';
		selectedArtist = artist;
		selectedAlbum  = null;
		selectedPath   = '';
		meta           = null;
		coverError     = '';
		uploadingArtist  = false;
		artistTs         = Date.now();
		artistPicMissing = false;
		artistGenre        = '';
		artistGenreTouched = false;
		resetAudit();
		loadArtistAlbumStatus(artist.path);
		persistSelection({ type: 'artist', path: artist.path });
	}

	function selectAlbum(album, artist) {
		selectedType   = 'album';
		selectedAlbum  = { ...album, artist };
		selectedArtist = null;
		selectedPath   = '';
		meta           = null;
		metaError      = '';
		dirty          = false;
		detailsOpen    = false;
		albumCoverTs   = Date.now();
		resetReorder();
		loadAlbumPanelTracks(album.path);
		persistSelection({ type: 'album', path: album.path, artistPath: artist.path });
	}

	// keepAlbumCtx: true when navigating from album panel (back button works)
	async function selectSong(path, keepAlbumCtx = false) {
		if (selectedPath === path && selectedType === 'song') return;
		if (!keepAlbumCtx) selectedAlbum = null;
		selectedType    = 'song';
		selectedPath    = path;
		selectedArtist  = null;
		lastEditedField = null;
		meta = null; metaError = ''; metaLoading = true;
		detailsOpen = false; dirty = false; saveError = ''; coverError = '';
		persistSelection({ type: 'song', path });
		try {
			const data = await api.songMeta(path);
			if (data.success) {
				meta = data;
				initEdit(data);
			} else {
				metaError = data.error ?? 'Erreur inconnue';
			}
		} catch (e) { metaError = e.message ?? 'Erreur réseau'; }
		finally { metaLoading = false; }
	}

	// ── Navigation prev/next dans l'album (flèches du panneau titre) ─────────────
	$: albumOrderedTracks = selectedAlbum ? (albumPanelTracks ?? selectedAlbum.songs ?? []) : null;
	$: albumTrackIndex    = albumOrderedTracks ? albumOrderedTracks.findIndex((t) => t.path === selectedPath) : -1;
	$: prevTrack = albumOrderedTracks && albumTrackIndex > 0 ? albumOrderedTracks[albumTrackIndex - 1] : null;
	$: nextTrack = albumOrderedTracks && albumTrackIndex >= 0 && albumTrackIndex < albumOrderedTracks.length - 1
		? albumOrderedTracks[albumTrackIndex + 1] : null;

	function goPrevTrack() { if (prevTrack) selectSong(prevTrack.path, true); }
	function goNextTrack() { if (nextTrack) selectSong(nextTrack.path, true); }

	function onSongNavKeydown(e) {
		if (selectedType !== 'song' || $helpOpen) return;
		if (e.ctrlKey || e.metaKey || e.altKey) return;
		const tag = e.target?.tagName;
		if (tag === 'INPUT' || tag === 'TEXTAREA' || e.target?.isContentEditable) return;
		if (e.key === 'ArrowLeft' && prevTrack) { e.preventDefault(); goPrevTrack(); }
		else if (e.key === 'ArrowRight' && nextTrack) { e.preventDefault(); goNextTrack(); }
	}

	function goHome() {
		selectedType   = null;
		selectedPath   = '';
		meta           = null;
		selectedAlbum  = null;
		selectedArtist = null;
		dirty          = false;
		persistSelection(null);
	}

	// ── Edit helpers ──────────────────────────────────────────────────────────────
	const EDITABLE_KEYS = [
		'title', 'artist', 'album_artist', 'album', 'year',
		'track_number', 'disc_number', 'genre', 'composer', 'conductor',
		'bpm', 'key', 'language', 'isrc', 'publisher', 'copyright',
		'encoded_by', 'comment',
	];

	function initEdit(m) {
		const v = {};
		for (const k of EDITABLE_KEYS) v[k] = m.id3?.[k] ?? '';
		editValues = v;
		dirty = false;
	}

	function setField(k, v) {
		editValues = { ...editValues, [k]: v };
		dirty = true;
		lastEditedField = k;
	}

	async function saveTags() {
		if (!dirty || saving) return;
		saving = true; saveError = '';
		try {
			await api.saveSongMeta(selectedPath, editValues);
			addToast('Tags sauvegardés.', 'info');
			dirty = false;
			const data = await api.songMeta(selectedPath);
			if (data.success) { meta = data; initEdit(data); }
		} catch (e) { saveError = e.message ?? 'Erreur'; }
		finally { saving = false; }
	}

	// ── Apply field to whole album ────────────────────────────────────────────────
	// Songs to target: use selectedAlbum if we came from album panel, else derive from tree
	$: albumSongsForApply = (() => {
		if (selectedAlbum) return selectedAlbum.songs ?? [];
		if (!meta?.path || !tree) return [];
		const parts = meta.path.split('/');
		if (parts.length < 3) return [];
		const albumPath = parts.slice(0, 2).join('/');
		const artist = (tree.artists ?? []).find(a => a.path === parts[0]);
		return artist?.albums?.find(a => a.path === albumPath)?.songs ?? [];
	})();

	async function applyToAlbum() {
		if (!lastEditedField || applyingToAlbum) return;
		const songs = albumSongsForApply;
		if (songs.length === 0) return;
		applyingToAlbum = true;
		const fieldValue = editValues[lastEditedField] ?? '';
		let done = 0, errors = 0;
		for (const song of songs) {
			try {
				await api.saveSongMeta(song.path, { [lastEditedField]: fieldValue });
				if (song.path === selectedPath) dirty = false;
				done++;
			} catch { errors++; }
		}
		applyingToAlbum = false;
		const label = ID3_LABELS[lastEditedField] ?? lastEditedField;
		if (errors === 0) addToast(`« ${label} » appliqué à ${done} titre${done > 1 ? 's' : ''}.`, 'info');
		else addToast(`${done} OK, ${errors} erreur${errors > 1 ? 's' : ''}.`, 'error');
	}

	// ── Cover upload (song) ───────────────────────────────────────────────────────
	async function uploadSongCover(file) {
		if (!file || uploadingCover) return;
		uploadingCover = true; coverError = '';
		try {
			await api.uploadSongCover(selectedPath, file);
			coverTs = Date.now();
			const data = await api.songMeta(selectedPath);
			if (data.success) meta = data;
			addToast('Pochette mise à jour.', 'info');
		} catch (e) { coverError = e.message ?? 'Erreur'; }
		finally { uploadingCover = false; }
	}

	// ── Cover upload (album) ──────────────────────────────────────────────────────
	async function uploadAlbumCover(file) {
		if (!file || uploadingAlbumCover) return;
		uploadingAlbumCover = true;
		try {
			await api.uploadAlbumCover(selectedAlbum.path, file);
			albumCoverTs = Date.now();
			addToast('Pochette album mise à jour.', 'info');
		} catch (e) { addToast(e.message ?? 'Erreur upload', 'error'); }
		finally { uploadingAlbumCover = false; }
	}

	// ── Cover upload (artist) ─────────────────────────────────────────────────────
	async function uploadArtistPic(file) {
		if (!file || uploadingArtist) return;
		uploadingArtist = true;
		try {
			await api.uploadArtistCover(selectedArtist.path, file);
			artistPicTs = Date.now();
			addToast('Photo artiste mise à jour.', 'info');
		} catch (e) { addToast(e.message ?? 'Erreur upload', 'error'); }
		finally { uploadingArtist = false; }
	}

	function onCoverPaste(e) {
		for (const item of (e.clipboardData?.items ?? [])) {
			if (item.kind !== 'file') continue;
			const file = item.getAsFile();
			if (!file?.type.startsWith('image/')) continue;
			e.preventDefault();
			if (selectedType === 'song')   uploadSongCover(file);
			else if (selectedType === 'album')  uploadAlbumCover(file);
			else if (selectedType === 'artist') uploadArtistPic(file);
			break;
		}
	}

	// ── Derived / filters ─────────────────────────────────────────────────────────
	$: q = nrm(filter);

	$: filteredArtists = !tree ? [] : (tree.artists ?? []).map((a) => ({
		...a,
		albums: (a.albums ?? []).map((al) => ({
			...al,
			songs: (al.songs ?? []).filter((s) => !q || nrm([a.name, al.name, s.name].join(' ')).includes(q)),
		})).filter((al) => al.songs.length > 0),
	})).filter((a) => a.albums.length > 0);

	$: filteredPlaylists = !tree ? [] : (tree.playlists ?? []).map((pl) => ({
		...pl,
		songs: (pl.songs ?? []).filter((s) => !q || nrm([pl.name, s.name].join(' ')).includes(q)),
	})).filter((pl) => pl.songs.length > 0);

	$: isEmpty = filteredArtists.length === 0 && filteredPlaylists.length === 0;

	// Full (unfiltered) album list for the selected artist panel
	$: artistAlbums = selectedArtist
		? (tree?.artists ?? []).find(a => a.path === selectedArtist.path)?.albums ?? []
		: [];

	function songDisplayName(name) { return name.replace(/\.mp3$/i, ''); }
	function fmtBytes(n) {
		if (n < 1048576) return `${(n/1024).toFixed(1)} KB`;
		return `${(n/1048576).toFixed(2)} MB`;
	}

	// ── Derived for right panel ───────────────────────────────────────────────────
	$: albumFolderPath = meta?.path ? meta.path.split('/').slice(0, -1).join('/') : '';
	$: albumCoverUrl         = albumFolderPath ? api.getFolderCoverUrl(albumFolderPath, coverTs) : '';
	$: selectedAlbumCoverUrl = selectedAlbum   ? api.getFolderCoverUrl(selectedAlbum.path, albumCoverTs) : '';
	$: artistPicUrl          = selectedArtist  ? api.getArtistPictureUrl(selectedArtist.path, artistPicTs) : '';

	// ID3 layout
	const ID3_PRIMARY   = ['title','artist','album_artist','album','year','track_number','disc_number','genre'];
	const ID3_SECONDARY = ['composer','conductor','bpm','key','language','isrc','publisher','copyright','encoded_by','comment'];

	// Champs multi-valeurs : « A; B » écrit deux valeurs ID3 distinctes (TPE1 null-séparé)
	const MULTI_FIELDS = new Set(['artist', 'genre', 'composer']);
	const MULTI_HINT   = 'Plusieurs valeurs possibles — sépare par « ; »';

	const ID3_LABELS = {
		title:'Titre', artist:'Artiste(s) (TPE1)', album_artist:'Artiste album (TPE2)',
		conductor:'Chef d\'orchestre', album:'Album', year:'Année / Date',
		track_number:'N° piste (TRCK)', disc_number:'N° disque (TPOS)',
		genre:'Genre (TCON)', composer:'Compositeur (TCOM)',
		copyright:'Copyright', publisher:'Éditeur (TPUB)',
		bpm:'BPM', key:'Tonalité', language:'Langue',
		encoded_by:'Encodé par', isrc:'ISRC', comment:'Commentaire',
	};

	$: jellyfinMissing = !meta?.id3 ? [] : ['album_artist','track_number','genre','year'].filter((k) => {
		const v = editValues[k] ?? meta.id3[k];
		return !v || v === '' || String(v).toLowerCase().includes('unknown');
	});

	$: customTags = meta?.id3?.custom_tags ? Object.entries(meta.id3.custom_tags) : [];

	let secondaryOpen = false;
</script>

<svelte:window on:paste={onCoverPaste} on:keydown={onSongNavKeydown} />
<svelte:head><title>Métadonnées — SongSurf</title></svelte:head>

<Header />

<div class="meta-layout">

	<!-- ── Left: tree ──────────────────────────────────────────── -->
	{#if sidebarCollapsed}
		<button class="sidebar-rail" on:click={toggleSidebar} title="Afficher la bibliothèque">
			<span class="sidebar-rail-icon">»</span>
			<span class="sidebar-rail-label">Bibliothèque</span>
		</button>
	{:else}
	<aside class="meta-sidebar">
		<div class="sidebar-top">
			<div class="sidebar-search-row">
				<input class="form-input" placeholder="Rechercher…" bind:value={filter} />
				<button class="sidebar-collapse-btn" on:click={toggleSidebar} title="Masquer la bibliothèque">«</button>
			</div>
		</div>

		<div class="sidebar-scroll">
			{#if tree === null}
				<div class="sidebar-empty">Chargement…</div>
			{:else if isEmpty}
				<div class="sidebar-empty">{filter ? 'Aucun résultat.' : 'Bibliothèque vide.'}</div>
			{:else}
				{#each filteredArtists as artist (artist.path)}
					<!-- Artist = drop zone for albums -->
					<div class="tree-artist"
						on:dragover={dndOverArtist}
						on:dragleave={dndLeave}
						on:drop={(e) => dndDropOnArtist(e, artist.path)}
					>
						<div class="tree-node artist-node {selectedType === 'artist' && selectedArtist?.path === artist.path ? 'artist-selected' : ''}">
							<button class="caret-btn" on:click|stopPropagation={() => toggleExpand(artist.path)}>
								{expanded.has(artist.path) || q ? '▾' : '▸'}
							</button>
							<button class="artist-label-btn" on:click={() => selectArtist(artist)}>
								<span class="tree-artist-pic">
									{#if artist.has_picture}
										<img
											src={api.getArtistPictureUrl(artist.path, artistPicTs)}
											alt="" loading="lazy"
											on:error={(e) => e.currentTarget.style.display='none'}
										/>
									{/if}
									<span class="tree-artist-pic-fallback">🎤</span>
								</span>
								<span class="tree-label">{artist.name}</span>
								<span class="tree-count">{artist.albums.reduce((n,al)=>n+al.songs.length,0)}</span>
							</button>
						</div>

						{#if expanded.has(artist.path) || q}
							{#each artist.albums as album (album.path)}
								<!-- Album = drop zone for songs -->
								<div class="tree-album"
									on:dragover={dndOverAlbum}
									on:dragleave={dndLeave}
									on:drop={(e) => dndDropOnAlbum(e, album.path)}
								>
									<div class="tree-node album-node {selectedType === 'album' && selectedAlbum?.path === album.path ? 'album-selected' : ''}">
										<button class="caret-btn" on:click|stopPropagation={() => toggleExpand(album.path)}>
											{expanded.has(album.path) || q ? '▾' : '▸'}
										</button>
										<span
											class="lib-drag-handle"
											draggable="true"
											title="Glisser l'album vers un autre artiste"
											on:dragstart|stopPropagation={(e) => dndStart(e, album.path, 'album')}
											on:dragend|stopPropagation={dndEnd}
										>⠿</span>
										<button class="album-label-btn" on:click={() => selectAlbum(album, artist)}>
											<span class="tree-icon">💿</span>
											<span class="tree-label">{album.name}</span>
											<span class="tree-count">{album.songs.length}</span>
										</button>
									</div>
									{#if expanded.has(album.path) || q}
										{#each album.songs as song (song.path)}
											<button
												class="song-row {selectedPath === song.path ? 'selected' : ''}"
												draggable="true"
												on:dragstart={(e) => dndStart(e, song.path, 'song')}
												on:dragend={dndEnd}
												on:click={() => selectSong(song.path)}
											>
												<span class="song-name">{songDisplayName(song.name)}</span>
											</button>
										{/each}
									{/if}
								</div>
							{/each}
						{/if}
					</div>
				{/each}

				{#each filteredPlaylists as pl (pl.path)}
					<!-- Playlists = drop zone for songs -->
					<div class="tree-artist"
						on:dragover={dndOverAlbum}
						on:dragleave={dndLeave}
						on:drop={(e) => dndDropOnAlbum(e, pl.path)}
					>
						<button class="tree-node" on:click={() => toggleExpand(pl.path)}>
							<span class="tree-caret">{expanded.has(pl.path) || q ? '▾' : '▸'}</span>
							<span class="tree-icon">📁</span>
							<span class="tree-label">{pl.name}</span>
							<span class="tree-count">{pl.songs.length}</span>
						</button>
						{#if expanded.has(pl.path) || q}
							{#each pl.songs as song (song.path)}
								<button
									class="song-row {selectedPath === song.path ? 'selected' : ''}"
									draggable="true"
									on:dragstart={(e) => dndStart(e, song.path, 'song')}
									on:dragend={dndEnd}
									on:click={() => selectSong(song.path)}
								>
									<span class="song-name">{songDisplayName(song.name)}</span>
								</button>
							{/each}
						{/if}
					</div>
				{/each}
			{/if}
		</div>
	</aside>
	{/if}

	<!-- ── Right: panel ─────────────────────────────────────────── -->
	<main class="meta-main" bind:this={metaMainEl} on:scroll={saveHomeScroll}>

		<!-- ── Home / Artist gallery ── -->
		{#if selectedType === null}
			{#if tree === null}
				<div class="meta-empty">
					<span class="meta-empty-icon">⏳</span>
					<p>Chargement de la bibliothèque…</p>
				</div>
			{:else if (tree.artists?.length ?? 0) > 0}
				<div class="home-gallery">
					<div class="home-gallery-grid">
						{#each (tree.artists ?? []) as artist (artist.path)}
							<button class="home-artist-card" on:click={() => selectArtist(artist)}>
								<div class="home-artist-cover">
									<img
										src={api.getArtistPictureUrl(artist.path, artistPicTs)}
										alt="" loading="lazy"
										on:error={(e) => e.currentTarget.style.display='none'}
									/>
									<div class="home-artist-placeholder">🎤</div>
								</div>
								<div class="home-artist-name" title={artist.name}>{artist.name}</div>
								<div class="home-artist-meta">
									{artist.albums?.length ?? 0} album{(artist.albums?.length ?? 0) > 1 ? 's' : ''}
									· {artist.albums?.reduce((n, al) => n + al.songs.length, 0) ?? 0} titres
								</div>
							</button>
						{/each}
					</div>
				</div>
			{:else}
				<div class="meta-empty">
					<span class="meta-empty-icon">🎵</span>
					<p>Ta bibliothèque est vide — télécharge tes premiers titres pour la remplir.</p>
					<a href="/" class="btn btn-primary btn-sm">⬇️ Aller au Téléchargement</a>
				</div>
			{/if}

		<!-- ── Artist panel ── -->
		{:else if selectedType === 'artist'}
			<div class="meta-content">
				<nav class="crumbs">
					<button class="crumb" on:click={goHome}>🏠 Bibliothèque</button>
					<span class="crumb-sep">›</span>
					<span class="crumb-current">🎤 {selectedArtist.name}</span>
				</nav>
				<!-- Artist header: photo + name + upload -->
				<div class="artist-panel">
					<div class="artist-pic-zone">
						{#key `${selectedArtist?.path}:${artistPicTs}`}
							<img
								class="artist-pic"
								src={artistPicUrl}
								alt=""
								on:load={() => { artistPicMissing = false; }}
								on:error={(e) => { e.currentTarget.style.display='none'; artistPicMissing = true; }}
							/>
						{/key}
						<div class="artist-pic-placeholder">🎤</div>
					</div>

					<div class="artist-info">
						<div class="artist-folder-label">Dossier artiste</div>
						<div class="artist-name">{selectedArtist.name}</div>
						{#if artistPicMissing}
							<div class="artist-pic-warn">⚠️ Photo artiste manquante — Jellyfin ne pourra pas afficher l'image de l'artiste</div>
						{/if}
						<div class="artist-album-count-label">
							{artistAlbums.length} album{artistAlbums.length > 1 ? 's' : ''} ·
							{artistAlbums.reduce((n, al) => n + al.songs.length, 0)} titres
						</div>

						<div class="cover-upload-zone" style="border-top:none;padding-left:0;padding-right:0">
							<p class="cover-hint">Photo artiste — glisse, colle (Ctrl+V) ou clique</p>
							<div class="cover-drop-row">
								<input
									type="file" accept="image/*" id="artist-pic-file" class="hidden-file"
									on:change={(e) => uploadArtistPic(e.currentTarget.files?.[0])}
								/>
								<label for="artist-pic-file" class="btn btn-ghost btn-sm" class:loading={uploadingArtist}>
									{uploadingArtist ? '⏳…' : '📁 Choisir'}
								</label>
							</div>
						</div>

						<div class="artist-genre-zone">
							<label class="cover-hint" for="artist-genre-input">
								Genre (TCON) — réécrit sur tous les albums · plusieurs valeurs : « ; »
							</label>
							<div class="artist-genre-row">
								<input
									id="artist-genre-input"
									class="meta-input"
									placeholder="Rap français; Hip-hop"
									bind:value={artistGenre}
									on:input={() => { artistGenreTouched = true; }}
									on:keydown={(e) => e.key === 'Enter' && applyArtistGenre()}
								/>
								<button
									class="btn btn-primary btn-sm"
									on:click={applyArtistGenre}
									disabled={artistGenreSaving || !artistGenre.trim()}
								>
									{artistGenreSaving ? '⏳…' : '🎼 Appliquer'}
								</button>
							</div>
						</div>

						{#if isAdmin}
							<button
								class="btn btn-danger btn-sm folder-delete-btn"
								on:click={deleteArtistFolder}
								disabled={deletingFolder}
								title="Supprime le dossier artiste et tout son contenu (irréversible)"
							>
								{deletingFolder ? '⏳…' : '🗑️ Supprimer le dossier'}
							</button>
						{/if}
					</div>
				</div>

				<!-- Album grid -->
				{#if artistAlbums.length > 0}
					<div class="meta-sections">
						<section class="meta-section">
							<h3 class="section-title">💿 Albums — {artistAlbums.length}</h3>
							<div class="artist-album-grid">
								{#each artistAlbums as album (album.path)}
									<button class="artist-album-card" on:click={() => selectAlbum(album, selectedArtist)}>
										<div class="artist-album-cover">
											<img
												src={api.getFolderCoverUrl(album.path, artistTs)}
												alt=""
												loading="lazy"
												on:error={(e) => e.currentTarget.style.display='none'}
											/>
											<div class="artist-album-placeholder">💿</div>
											{#if artistAlbumStatus[album.path]}
												{#if artistAlbumStatus[album.path].complete}
													<span class="album-badge album-badge-ok" title="Genre, année et n° de piste complets">✓</span>
												{:else}
													<span class="album-badge album-badge-warn" title={statusTooltip(artistAlbumStatus[album.path])}>!</span>
												{/if}
											{/if}
										</div>
										<div class="artist-album-name" title={album.name}>{album.name}</div>
										<div class="artist-album-count">{album.songs.length} titre{album.songs.length > 1 ? 's' : ''}</div>
									</button>
								{/each}
							</div>
						</section>

						<!-- Audit métadonnées (tous les membres : scan iTunes de leur bibliothèque) -->
						<section class="meta-section">
								<h3 class="section-title">
									🔎 Audit métadonnées
									{#if audit}
										<span class="details-sub">{audit.total_recommendations} recommandation{audit.total_recommendations > 1 ? 's' : ''}</span>
									{/if}
								</h3>

								{#if !audit}
									<div class="audit-intro">
										<p class="cover-hint">
											Compare les tags de tous les albums avec iTunes (genre, année, artiste album,
											numéros de piste, cohérence TPE1/TPE2) et propose des corrections.
											Rien n'est modifié sans validation.
										</p>
										{#if auditError}<p class="save-error">{auditError}</p>{/if}
										<button class="btn btn-primary btn-sm" on:click={runAudit} disabled={auditLoading}>
											{auditLoading ? '⏳ Audit en cours…' : "🔎 Lancer l'audit"}
										</button>
									</div>
								{:else}
									{#each audit.albums as al (al.path)}
										<div class="audit-album">
											<div class="audit-album-head">
												<span class="audit-album-name">💿 {al.name}</span>
												<span class="audit-itunes {al.itunes?.found ? '' : 'audit-itunes-miss'}">
													{al.itunes?.found
														? `iTunes ✓${al.itunes.year ? ` · ${al.itunes.year}` : ''}${al.itunes.track_count ? ` · ${al.itunes.track_count} titres` : ''}`
														: 'introuvable sur iTunes'}
												</span>
											</div>
											{#each al.recommendations as rec (rec.id)}
												<label class="audit-rec">
													<input
														type="checkbox"
														checked={auditSelected.has(rec.id)}
														on:change={() => toggleRec(rec.id)}
													/>
													<div class="audit-rec-body">
														<div class="audit-rec-line">
															<strong>{ID3_LABELS[rec.field] ?? rec.field}</strong> :
															<span class="audit-current">{rec.current}</span>
															<span class="audit-arrow">→</span>
															<span class="audit-proposed">{rec.proposed}</span>
														</div>
														<div class="audit-rec-reason">
															{rec.reason} · {rec.changes.length} fichier{rec.changes.length > 1 ? 's' : ''}
														</div>
													</div>
												</label>
											{/each}
											{#each al.warnings as w}
												<div class="audit-warn">⚠️ {w}</div>
											{/each}
											{#if al.recommendations.length === 0 && al.warnings.length === 0}
												<div class="audit-ok">✅ Aucun problème détecté</div>
											{/if}
										</div>
									{/each}
									{#each audit.artist_warnings ?? [] as w}
										<div class="audit-warn">⚠️ {w}</div>
									{/each}

									<div class="save-bar">
										<button class="btn btn-ghost btn-sm" on:click={runAudit} disabled={auditLoading || auditApplying}>
											{auditLoading ? '⏳…' : '↻ Relancer'}
										</button>
										<button
											class="btn btn-primary btn-sm"
											on:click={applyAudit}
											disabled={auditChanges.length === 0 || auditApplying}
										>
											{auditApplying ? '⏳ Application…' : `✓ Appliquer la sélection (${auditChanges.length})`}
										</button>
									</div>
								{/if}
							</section>
					</div>
				{/if}
			</div>

		<!-- ── Album panel ── -->
		{:else if selectedType === 'album'}
			<div class="meta-content">
				<nav class="crumbs">
					<button class="crumb" on:click={goHome}>🏠 Bibliothèque</button>
					<span class="crumb-sep">›</span>
					<button class="crumb" on:click={() => selectArtist(selectedAlbum.artist)}>🎤 {selectedAlbum.artist.name}</button>
					<span class="crumb-sep">›</span>
					<span class="crumb-current">💿 {selectedAlbum.name}</span>
				</nav>

				<!-- Album header: cover + info -->
				<div class="album-header">
					<div class="album-cover-zone">
						{#key `${selectedAlbum?.path}:${albumCoverTs}`}
							<img
								class="album-cover-img"
								src={selectedAlbumCoverUrl}
								alt=""
								on:error={(e) => e.currentTarget.style.display='none'}
							/>
						{/key}
						<div class="album-cover-placeholder">💿</div>
						<label
							class="album-cover-overlay"
							for="album-cover-file"
							title="Remplacer la pochette"
							class:loading={uploadingAlbumCover}
						>
							{uploadingAlbumCover ? '⏳' : '📁'}
						</label>
						<input
							type="file" accept="image/*" id="album-cover-file" class="hidden-file"
							on:change={(e) => uploadAlbumCover(e.currentTarget.files?.[0])}
						/>
					</div>

					<div class="album-info">
						<div class="album-artist-chip">{selectedAlbum.artist.name}</div>
						<div class="album-title">{selectedAlbum.name}</div>
						<div class="album-track-count">
							{selectedAlbum.songs.length} titre{selectedAlbum.songs.length > 1 ? 's' : ''}
						</div>
						<p class="cover-hint" style="margin-top:var(--s4)">
							Pochette : glisse ou colle <kbd>Ctrl+V</kbd> pour remplacer
						</p>

						{#if isAdmin}
							<button
								class="btn btn-danger btn-sm folder-delete-btn"
								on:click={deleteAlbumFolder}
								disabled={deletingFolder}
								title="Supprime le dossier album et tous ses titres (irréversible)"
							>
								{deletingFolder ? '⏳…' : "🗑️ Supprimer l'album"}
							</button>
						{/if}
					</div>
				</div>

				<!-- Tracklist -->
				<div class="meta-sections">
					<section class="meta-section">
						<h3 class="section-title">
							🎵 Titres
							{#if !reorderMode}
								<button
									class="section-action"
									on:click={enterReorder}
									disabled={reorderLoading}
									title="Réordonner les titres puis écrire les numéros de piste 1..N (TRCK n/total)"
								>
									{reorderLoading ? '⏳…' : '🔢 Numéroter les pistes'}
								</button>
							{/if}
						</h3>

						{#if reorderMode}
							<div class="reorder-hint">
								Glisse les titres dans l'ordre de l'album (ou utilise ▲▼).
								Les titres <span class="reorder-badge-missing">sans n°</span> ont été placés à la fin.
								« Enregistrer » écrit <code>1/{reorderTracks.length}…{reorderTracks.length}/{reorderTracks.length}</code> sur tous les titres.
							</div>
							<div class="tracklist">
								{#each reorderTracks as track, i (track.path)}
									<div
										class="track-row reorder-row {reorderDragIdx === i ? 'reorder-dragging' : ''}"
										draggable="true"
										role="listitem"
										on:dragstart={(e) => reorderDragStart(e, i)}
										on:dragover={(e) => reorderDragOver(e, i)}
										on:dragend={reorderDragEnd}
										on:drop|preventDefault={reorderDragEnd}
									>
										<span class="reorder-grip">⠿</span>
										<span class="track-num">{i + 1}</span>
										<span class="track-name">{songDisplayName(track.name)}</span>
										{#if track.track_number}
											<span class="reorder-badge">{track.track_number}</span>
										{:else}
											<span class="reorder-badge reorder-badge-missing">sans n°</span>
										{/if}
										<span class="reorder-arrows">
											<button class="reorder-arrow" disabled={i === 0} on:click={() => moveTrack(i, -1)}>▲</button>
											<button class="reorder-arrow" disabled={i === reorderTracks.length - 1} on:click={() => moveTrack(i, 1)}>▼</button>
										</span>
									</div>
								{/each}
							</div>
							<div class="save-bar">
								<button class="btn btn-ghost btn-sm" on:click={resetReorder} disabled={reorderSaving}>
									Annuler
								</button>
								<button class="btn btn-primary btn-sm" on:click={saveReorder} disabled={reorderSaving}>
									{reorderSaving ? '⏳ Écriture…' : `💾 Enregistrer la numérotation (1..${reorderTracks.length})`}
								</button>
							</div>
						{:else if albumPanelTracks}
							<!-- TRCK réels (triés par numéro, sans-numéro à la fin) -->
							<div class="tracklist">
								{#each albumPanelTracks as track (track.path)}
									<button
										class="track-row {selectedPath === track.path ? 'track-selected' : ''}"
										on:click={() => selectSong(track.path, true)}
									>
										<span class="track-num {trackDisplayNum(track) === '—' ? 'track-num-missing' : ''}">{trackDisplayNum(track)}</span>
										<span class="track-name">{songDisplayName(track.name)}</span>
										{#if trackDisplayNum(track) === '—'}
											<span class="reorder-badge reorder-badge-missing">sans n°</span>
										{/if}
										<span class="track-chevron">›</span>
									</button>
								{/each}
							</div>
						{:else if albumTracksLoading}
							<!-- Chargement des TRCK réels : pas d'affichage intermédiaire pour éviter le clip visuel -->
							<div class="meta-empty"><span class="meta-empty-icon">⏳</span><p>Chargement des titres…</p></div>
						{:else}
							<!-- Repli : ordre alphabétique si la lecture des TRCK a échoué -->
							<div class="tracklist">
								{#each selectedAlbum.songs as song, i (song.path)}
									<button
										class="track-row {selectedPath === song.path ? 'track-selected' : ''}"
										on:click={() => selectSong(song.path, true)}
									>
										<span class="track-num">{i + 1}</span>
										<span class="track-name">{songDisplayName(song.name)}</span>
										<span class="track-chevron">›</span>
									</button>
								{/each}
							</div>
						{/if}
					</section>
				</div>
			</div>

		<!-- ── Song panel ── -->
		{:else if selectedType === 'song'}
			{#if metaLoading}
				<div class="meta-empty"><span class="meta-empty-icon">⏳</span><p>Chargement…</p></div>
			{:else if metaError}
				<div class="meta-empty"><span class="meta-empty-icon">❌</span><p>{metaError}</p></div>
			{:else if meta}
				<div class="song-nav-row">
					{#if selectedAlbum}
						<button
							class="song-nav-arrow song-nav-prev"
							disabled={!prevTrack}
							on:click={goPrevTrack}
							title={prevTrack ? `Titre précédent : ${songDisplayName(prevTrack.name)}` : 'Premier titre de l\'album'}
							aria-label="Titre précédent"
						>‹</button>
					{/if}
					<div class="meta-content">
					<nav class="crumbs">
						<button class="crumb" on:click={goHome}>🏠 Bibliothèque</button>
						{#if songCrumbParts.length === 3}
							<span class="crumb-sep">›</span>
							<button class="crumb" on:click={() => gotoArtistByPath(songCrumbParts[0])}>🎤 {songCrumbParts[0]}</button>
							<span class="crumb-sep">›</span>
							<button class="crumb" on:click={() => gotoAlbumByPath(songCrumbParts[0], songCrumbParts.slice(0, 2).join('/'))}>💿 {songCrumbParts[1]}</button>
						{:else if songCrumbParts.length === 2}
							<span class="crumb-sep">›</span>
							<span class="crumb-current">📁 {songCrumbParts[0]}</span>
						{/if}
						<span class="crumb-sep">›</span>
						<span class="crumb-current">{songDisplayName(songCrumbParts[songCrumbParts.length - 1] ?? '')}</span>
					</nav>

					<div class="meta-sections">

						<!-- Fichier (read-only) -->
						<section class="meta-section">
							<h3 class="section-title">📄 Fichier</h3>
							<div class="meta-grid">
								<div class="meta-row"><span class="meta-key">Nom</span><span class="meta-val">{meta.file_name}</span></div>
								<div class="meta-row"><span class="meta-key">Taille</span><span class="meta-val">{fmtBytes(meta.file_size)}</span></div>
							</div>
						</section>

						<!-- Tags ID3 (editable) -->
						{#if meta.id3}
							<section class="meta-section">
								<h3 class="section-title">
									🏷️ Tags ID3
									{#if jellyfinMissing.length > 0}
										<span class="jellyfin-warn">⚠️ Jellyfin manque : {jellyfinMissing.map(k=>ID3_LABELS[k]?.split(' ')[0]??k).join(', ')}</span>
									{/if}
								</h3>

								<div class="section-subtitle">Principaux (Jellyfin / Ampifin)</div>
								<div class="multi-hint">💡 Artiste(s), genre, compositeur : sépare plusieurs valeurs par « ; » — ex. <code>ArtisteA; ArtisteB</code></div>
								<div class="meta-grid">
									{#each ID3_PRIMARY as key}
										<div class="meta-row {jellyfinMissing.includes(key) ? 'row-warn' : ''}">
											<label class="meta-key" for="f-{key}">{ID3_LABELS[key]}</label>
											<input
												id="f-{key}"
												class="meta-input {jellyfinMissing.includes(key) ? 'input-warn' : ''}"
												value={editValues[key] ?? ''}
												placeholder={MULTI_FIELDS.has(key) ? 'A; B' : '—'}
												title={MULTI_FIELDS.has(key) ? MULTI_HINT : ''}
												on:input={(e) => setField(key, e.currentTarget.value)}
											/>
										</div>
									{/each}
								</div>

								<button class="details-toggle" on:click={() => secondaryOpen = !secondaryOpen}>
									{secondaryOpen ? '▾' : '▸'} Champs supplémentaires
								</button>
								{#if secondaryOpen}
									<div class="section-subtitle">Autres champs</div>
									<div class="meta-grid details-grid">
										{#each ID3_SECONDARY as key}
											<div class="meta-row">
												<label class="meta-key" for="f-{key}">{ID3_LABELS[key]}</label>
												<input
													id="f-{key}"
													class="meta-input {key === 'isrc' || key === 'encoded_by' ? 'mono' : ''}"
													value={editValues[key] ?? ''}
													placeholder={MULTI_FIELDS.has(key) ? 'A; B' : '—'}
													title={MULTI_FIELDS.has(key) ? MULTI_HINT : ''}
													on:input={(e) => setField(key, e.currentTarget.value)}
												/>
											</div>
										{/each}
									</div>
								{/if}

								<!-- Save bar -->
								<div class="save-bar">
									{#if saveError}<span class="save-error">{saveError}</span>{/if}
									{#if lastEditedField && albumSongsForApply.length > 1}
										<button
											class="btn btn-ghost btn-sm"
											on:click={applyToAlbum}
											disabled={applyingToAlbum}
											title="Appliquer « {ID3_LABELS[lastEditedField] ?? lastEditedField} » à tous les titres de l'album"
										>
											{applyingToAlbum ? '⏳…' : '📋 Appliquer à l\'album'}
										</button>
									{/if}
									<button
										class="btn btn-primary btn-sm"
										on:click={saveTags}
										disabled={!dirty || saving}
									>
										{saving ? '⏳ Sauvegarde…' : dirty ? '💾 Sauvegarder' : '✓ Sauvegardé'}
									</button>
								</div>
							</section>

							<!-- Custom TXXX (read-only) -->
							{#if customTags.length > 0}
								<section class="meta-section">
									<h3 class="section-title">🔧 Tags TXXX (MusicBrainz, ReplayGain…)</h3>
									<div class="meta-grid">
										{#each customTags as [k, v]}
											<div class="meta-row">
												<span class="meta-key mono small">{k}</span>
												<span class="meta-val mono small">{v}</span>
											</div>
										{/each}
									</div>
								</section>
							{/if}

							<!-- Plus de détails: Audio + Pochette -->
							<section class="meta-section">
								<button class="section-title-btn" on:click={() => detailsOpen = !detailsOpen}>
									<span>{detailsOpen ? '▾' : '▸'} Plus de détails</span>
									<span class="details-sub">Audio · Pochette</span>
								</button>

								{#if detailsOpen}
									<!-- Audio -->
									{#if meta.audio}
										<div class="section-subtitle">🔊 Audio</div>
										<div class="meta-grid">
											<div class="meta-row"><span class="meta-key">Durée</span><span class="meta-val">{meta.audio.duration_fmt} ({meta.audio.duration_s} s)</span></div>
											<div class="meta-row"><span class="meta-key">Débit</span><span class="meta-val">{meta.audio.bitrate_kbps} kbps</span></div>
											<div class="meta-row"><span class="meta-key">Fréquence</span><span class="meta-val">{meta.audio.sample_rate} Hz</span></div>
											<div class="meta-row"><span class="meta-key">Canaux</span><span class="meta-val">{meta.audio.channels}</span></div>
											{#if meta.audio.mode}
												<div class="meta-row"><span class="meta-key">Mode</span><span class="meta-val mono">{meta.audio.mode}</span></div>
											{/if}
											{#if meta.audio.encoder_settings}
												<div class="meta-row"><span class="meta-key">Paramètres encodeur</span><span class="meta-val mono small">{meta.audio.encoder_settings}</span></div>
											{/if}
										</div>
									{/if}

									<!-- Pochette -->
									<div class="section-subtitle">🖼️ Pochette</div>
									<div class="meta-grid">
										<div class="meta-row">
											<span class="meta-key">Intégrée (APIC)</span>
											<span class="meta-val {meta.id3.has_embedded_cover ? 'tag-present' : 'tag-absent'}">
												{meta.id3.has_embedded_cover ? '✅ Oui' : '❌ Non'}
											</span>
										</div>
										<div class="meta-row {!meta.has_album_cover ? 'row-warn' : ''}">
											<span class="meta-key">Pochette album</span>
											<span class="meta-val">
												{#if meta.has_album_cover}
													<span class="tag-present">✅ {meta.cover_files.join(', ')}</span>
												{:else}
													<span class="tag-absent">⚠️ Aucune — Jellyfin ne trouvera pas la couverture</span>
												{/if}
											</span>
										</div>
									</div>

									<!-- Preview -->
									{#if meta.has_album_cover && albumCoverUrl}
										<div class="cover-preview-area">
											<div class="cover-item">
												{#key coverTs}
													<img class="cover-thumb" src={albumCoverUrl} alt="Pochette" loading="lazy" />
												{/key}
												<span class="cover-label">Fichier externe</span>
											</div>
										</div>
									{/if}

									<!-- Upload zone -->
									<div class="cover-upload-zone">
										<p class="cover-hint">Remplacer la pochette — glisse, colle (Ctrl+V) ou clique</p>
										{#if coverError}<p class="save-error">{coverError}</p>{/if}
										<div class="cover-drop-row">
											<input
												type="file" accept="image/*" id="cover-file" class="hidden-file"
												on:change={(e) => uploadSongCover(e.currentTarget.files?.[0])}
											/>
											<label for="cover-file" class="btn btn-ghost btn-sm" class:loading={uploadingCover}>
												{uploadingCover ? '⏳…' : '📁 Choisir une image'}
											</label>
											{#if uploadingCover}<span class="cover-hint">Upload en cours…</span>{/if}
										</div>
									</div>
								{/if}
							</section>
						{/if}

					</div>
					</div>
					{#if selectedAlbum}
						<button
							class="song-nav-arrow song-nav-next"
							disabled={!nextTrack}
							on:click={goNextTrack}
							title={nextTrack ? `Titre suivant : ${songDisplayName(nextTrack.name)}` : 'Dernier titre de l\'album'}
							aria-label="Titre suivant"
						>›</button>
					{/if}
				</div>
			{/if}
		{/if}
	</main>
</div>

<style>
	.meta-layout {
		display: flex;
		/* 93px = header (52) + onglets (40) + bordure (1) — voir Header.svelte */
		height: calc(100dvh - 93px);
		overflow: hidden;
	}

	/* ── Sidebar ──────────────────────────────────────────────── */
	.meta-sidebar {
		width: 300px; flex-shrink: 0;
		border-right: 1px solid var(--sep);
		display: flex; flex-direction: column;
		background: var(--bg-2);
	}
	.sidebar-top {
		padding: var(--s3) var(--s3) var(--s2);
		display: flex; flex-direction: column; gap: var(--s2);
		border-bottom: 1px solid var(--sep);
	}
	.sidebar-search-row { display: flex; align-items: center; gap: var(--s2); }
	.sidebar-search-row .form-input { flex: 1; min-width: 0; }
	.sidebar-collapse-btn {
		flex-shrink: 0;
		width: 28px; height: 28px;
		background: none; border: 1px solid var(--sep);
		border-radius: var(--r-sm);
		color: var(--text-3); font-size: 13px;
		cursor: pointer;
		transition: color .1s, background .1s;
	}
	.sidebar-collapse-btn:hover { color: var(--text); background: rgba(255,255,255,.06); }

	/* Rail affiché quand la sidebar est repliée */
	.sidebar-rail {
		flex-shrink: 0;
		width: 28px;
		display: flex; flex-direction: column; align-items: center;
		gap: var(--s3); padding-top: var(--s3);
		background: var(--bg-2);
		border: none; border-right: 1px solid var(--sep);
		color: var(--text-3); cursor: pointer;
		transition: color .1s, background .1s;
	}
	.sidebar-rail:hover { color: var(--text); background: rgba(255,255,255,.04); }
	.sidebar-rail-icon { font-size: 13px; }
	.sidebar-rail-label {
		font-size: 11px; letter-spacing: .08em;
		writing-mode: vertical-rl;
	}
	.sidebar-scroll { flex: 1; overflow-y: auto; padding: var(--s2) 0; }
	.sidebar-empty { padding: var(--s6) var(--s4); text-align: center; color: var(--text-3); font-size: 13px; }

	/* ── Tree nodes ───────────────────────────────────────────── */
	.tree-artist {
		margin-bottom: 1px;
		border-top: 1px solid rgba(84,84,88,.18);
	}
	.tree-artist:first-child { border-top: none; }

	.tree-album {
		margin-left: 0;
		padding-left: 16px;
		border-left: 2px solid rgba(84,84,88,.2);
		margin-left: 14px;
	}

	/* Artist row */
	.artist-node {
		display: flex; align-items: center;
		border-radius: 0;
	}
	.artist-node.artist-selected { background: rgba(10,132,255,.08); }

	/* Album row (same split pattern as artist) */
	.album-node {
		display: flex; align-items: center;
	}
	.album-node.album-selected { background: rgba(10,132,255,.08); }

	.caret-btn {
		flex-shrink: 0;
		width: 28px; height: 100%; min-height: 30px;
		background: none; border: none;
		color: var(--text-3); font-size: 10px;
		cursor: pointer; display: flex; align-items: center; justify-content: center;
		transition: color .1s;
	}
	.caret-btn:hover { color: var(--text); }

	.artist-label-btn, .album-label-btn {
		flex: 1; min-width: 0;
		display: flex; align-items: center; gap: 5px;
		background: none; border: none;
		text-align: left; cursor: pointer;
		padding: 5px var(--s3) 5px 0;
		transition: background .1s, color .1s;
	}
	.artist-label-btn {
		color: var(--text); font-size: 13px; font-weight: 600;
	}
	.album-label-btn {
		color: var(--text-2); font-size: 12px; font-weight: 400;
	}
	.artist-label-btn:hover, .album-label-btn:hover { color: var(--text); background: rgba(255,255,255,.04); }

	.lib-drag-handle {
		flex-shrink: 0;
		cursor: grab;
		color: var(--text-3);
		font-size: 13px;
		padding: 0 2px;
		user-select: none;
		line-height: 1;
		opacity: 0;
		transition: opacity .1s;
	}
	.album-node:hover .lib-drag-handle { opacity: 1; }
	.lib-drag-handle:active { cursor: grabbing; }

	:global(.drop-target) {
		outline: 2px dashed var(--blue) !important;
		outline-offset: -2px;
		background: rgba(10, 132, 255, 0.07) !important;
	}

	.tree-node {
		display: flex; align-items: center; gap: 5px;
		width: 100%; padding: 5px var(--s3);
		background: none; border: none;
		color: var(--text-2); font-size: 13px;
		text-align: left; cursor: pointer;
		transition: background .1s, color .1s;
	}
	.tree-node:hover { background: rgba(255,255,255,.05); color: var(--text); }

	.tree-caret { font-size: 10px; color: var(--text-3); flex-shrink: 0; width: 10px; }
	.tree-icon  { font-size: 13px; flex-shrink: 0; }

	/* Vignette artiste dans l'arbre (photo ronde, 🎤 en repli) */
	.tree-artist-pic {
		position: relative; flex-shrink: 0;
		width: 22px; height: 22px;
		border-radius: 50%; overflow: hidden;
		background: var(--bg-3); border: 1px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.tree-artist-pic img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover; z-index: 1;
	}
	.tree-artist-pic-fallback { font-size: 11px; z-index: 0; }
	.tree-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.tree-count { font-size: 11px; color: var(--text-3); flex-shrink: 0; }
	.row-warn   { font-size: 11px; flex-shrink: 0; }

	.song-row {
		position: relative;
		display: flex; align-items: center;
		width: 100%; padding: 5px var(--s3) 5px 32px;
		background: none; border: none;
		color: var(--text-2); font-size: 12px;
		text-align: left; cursor: pointer;
		transition: background .1s, color .1s;
	}
	.song-row:hover { background: rgba(255,255,255,.05); color: var(--text); }
	.song-row.selected { background: rgba(10,132,255,.15); color: var(--blue); }
	.song-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

	/* ── Main ─────────────────────────────────────────────────── */
	.meta-main { flex: 1; overflow-y: auto; padding: var(--s6); background: var(--bg); }
	.meta-empty {
		height: 100%; display: flex; flex-direction: column;
		align-items: center; justify-content: center;
		gap: var(--s3); color: var(--text-3); text-align: center;
	}
	.meta-empty-icon { font-size: 40px; }
	.meta-empty p { font-size: 14px; max-width: 280px; line-height: 1.5; margin: 0; }

	.meta-content { max-width: 720px; margin: 0 auto; }

	/* ── Navigation titre précédent/suivant (panneau titre) ──────── */
	.song-nav-row { display: flex; align-items: flex-start; gap: var(--s3); }
	.song-nav-row > .meta-content { flex: 1 1 auto; min-width: 0; }
	.song-nav-arrow {
		flex-shrink: 0;
		position: sticky; top: var(--s6);
		width: 40px; height: 40px; border-radius: 50%;
		display: flex; align-items: center; justify-content: center;
		font-size: 20px; line-height: 1;
		background: var(--bg-2); border: 1px solid var(--sep); color: var(--text);
		cursor: pointer; transition: background .1s, color .1s, border-color .1s, opacity .1s;
	}
	.song-nav-arrow:hover:not(:disabled) { background: rgba(10,132,255,.12); color: var(--blue); border-color: var(--blue); }
	.song-nav-arrow:disabled { opacity: .3; cursor: default; }

	/* ── Fil d'Ariane unifié ──────────────────────────────────── */
	.crumbs {
		display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
		margin-bottom: var(--s4);
		font-size: 13px;
	}
	.crumb {
		background: none; border: none; padding: 0;
		color: var(--blue); font-size: 13px; cursor: pointer;
		max-width: 220px;
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.crumb:hover { text-decoration: underline; text-underline-offset: 2px; }
	.crumb-sep { color: var(--text-3); flex-shrink: 0; }
	.crumb-current {
		color: var(--text); font-weight: 500;
		max-width: 280px;
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}

	.meta-sections { display: flex; flex-direction: column; gap: var(--s4); }

	/* ── Suppression de dossier (admin) ───────────────────────── */
	.folder-delete-btn {
		margin-top: var(--s4);
		align-self: flex-start;
	}

	/* ── Artist panel ─────────────────────────────────────────── */
	.artist-panel {
		display: flex; gap: var(--s6); align-items: flex-start;
		padding: var(--s4) 0;
	}
	.artist-pic-zone {
		position: relative; width: 140px; height: 140px; flex-shrink: 0;
		border-radius: var(--r-md); overflow: hidden;
		background: var(--bg-3); border: 1px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.artist-pic {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover;
		border-radius: var(--r-md);
	}
	.artist-pic-placeholder { font-size: 48px; color: var(--text-3); }
	.artist-info { flex: 1; }
	.artist-folder-label { font-size: 11px; font-weight: 700; color: var(--text-3); letter-spacing: .05em; text-transform: uppercase; margin-bottom: 4px; }
	.artist-name { font-size: 22px; font-weight: 700; color: var(--text); margin-bottom: var(--s2); }
	.artist-pic-warn {
		font-size: 12px; color: var(--orange);
		background: rgba(255,159,10,.08);
		border: 1px solid rgba(255,159,10,.2);
		border-radius: var(--r-sm);
		padding: 5px 10px;
		margin-bottom: var(--s3);
		line-height: 1.4;
	}
	.artist-album-count-label { font-size: 13px; color: var(--text-3); margin-bottom: var(--s4); }

	/* Genre (TCON) appliqué à tout l'artiste */
	.artist-genre-zone { margin-bottom: var(--s4); }
	.artist-genre-zone .cover-hint { display: block; }
	.artist-genre-row { display: flex; align-items: center; gap: var(--s2); }
	.artist-genre-row .meta-input { max-width: 300px; }

	/* ── Artist album grid ────────────────────────────────────── */
	.artist-album-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
		gap: var(--s3);
		padding: var(--s4);
	}
	.artist-album-card {
		display: flex; flex-direction: column; align-items: center;
		gap: var(--s2); padding: var(--s3);
		background: none; border: none;
		border-radius: var(--r-md); cursor: pointer;
		transition: background .15s;
		text-align: center;
	}
	.artist-album-card:hover { background: rgba(255,255,255,.06); }
	.artist-album-cover {
		position: relative;
		width: 100%; aspect-ratio: 1;
		border-radius: var(--r-sm); overflow: hidden;
		background: var(--bg-3); border: 1px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.artist-album-cover img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover; z-index: 1;
	}
	.artist-album-placeholder { font-size: 26px; color: var(--text-3); z-index: 0; }

	/* Badge de complétude des tags (genre/année/n° de piste) */
	.album-badge {
		position: absolute; top: 4px; right: 4px; z-index: 2;
		width: 18px; height: 18px;
		display: flex; align-items: center; justify-content: center;
		border-radius: 50%;
		font-size: 11px; font-weight: 700;
		cursor: help;
	}
	.album-badge-ok   { background: rgba(48,209,88,.2);  color: var(--green);  border: 1px solid rgba(48,209,88,.4); }
	.album-badge-warn { background: rgba(255,159,10,.25); color: var(--orange); border: 1px solid rgba(255,159,10,.5); }
	.artist-album-name {
		font-size: 12px; font-weight: 500; color: var(--text);
		width: 100%;
		overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.artist-album-count { font-size: 11px; color: var(--text-3); }

	/* ── Album panel ──────────────────────────────────────────── */
	.album-header {
		display: flex; gap: var(--s6); align-items: flex-start;
		padding: var(--s4) 0 var(--s6);
	}
	.album-cover-zone {
		position: relative; width: 160px; height: 160px; flex-shrink: 0;
		border-radius: var(--r-md); overflow: hidden;
		background: var(--bg-3); border: 1px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
		cursor: pointer;
	}
	.album-cover-img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover; z-index: 1;
	}
	.album-cover-placeholder { font-size: 52px; color: var(--text-3); z-index: 0; }
	.album-cover-overlay {
		position: absolute; inset: 0;
		display: flex; align-items: center; justify-content: center;
		background: rgba(0,0,0,.45);
		font-size: 20px; cursor: pointer;
		opacity: 0; transition: opacity .15s;
		z-index: 2;
	}
	.album-cover-zone:hover .album-cover-overlay { opacity: 1; }

	.album-info { flex: 1; min-width: 0; padding-top: var(--s2); }
	.album-artist-chip {
		display: inline-block;
		font-size: 11px; font-weight: 700; color: var(--text-3);
		letter-spacing: .05em; text-transform: uppercase;
		margin-bottom: var(--s2);
	}
	.album-title {
		font-size: 22px; font-weight: 700; color: var(--text);
		margin-bottom: var(--s2);
		word-break: break-word;
	}
	.album-track-count {
		font-size: 13px; color: var(--text-3);
		margin-bottom: var(--s2);
	}


	/* ── Tracklist ────────────────────────────────────────────── */
	.tracklist { display: flex; flex-direction: column; }
	.track-row {
		display: flex; align-items: center; gap: var(--s3);
		width: 100%; padding: 9px var(--s4);
		background: none; border: none;
		border-bottom: 1px solid rgba(84,84,88,.2);
		color: var(--text-2); font-size: 13px;
		text-align: left; cursor: pointer;
		transition: background .1s, color .1s;
	}
	.track-row:last-child { border-bottom: none; }
	.track-row:hover { background: rgba(255,255,255,.05); color: var(--text); }
	.track-row.track-selected { background: rgba(10,132,255,.12); color: var(--blue); }
	.track-num {
		flex-shrink: 0; width: 24px;
		font-size: 12px; color: var(--text-3);
		font-family: var(--font-mono);
		text-align: right;
	}
	.track-num-missing { color: var(--orange); }
	.track-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.track-chevron { flex-shrink: 0; font-size: 14px; color: var(--text-3); }

	/* ── Renumérotation (mode Numéroter les pistes) ───────────── */
	.section-action {
		margin-left: auto;
		background: none; border: 1px solid var(--sep);
		border-radius: var(--r-sm);
		color: var(--blue); font-size: 11px; font-weight: 500;
		text-transform: none; letter-spacing: 0;
		padding: 3px 8px; cursor: pointer;
		transition: background .1s;
	}
	.section-action:hover { background: rgba(10,132,255,.08); }
	.section-action:disabled { opacity: .5; pointer-events: none; }

	.reorder-hint {
		padding: var(--s2) var(--s4);
		font-size: 11px; color: var(--text-3); line-height: 1.5;
		border-bottom: 1px solid rgba(84,84,88,.2);
	}
	.reorder-hint code { font-size: 10px; background: rgba(0,0,0,.25); padding: 1px 4px; border-radius: 3px; }

	.reorder-row { cursor: grab; user-select: none; }
	.reorder-row:active { cursor: grabbing; }
	.reorder-row.reorder-dragging { background: rgba(10,132,255,.12); }
	.reorder-grip { flex-shrink: 0; color: var(--text-3); font-size: 13px; }
	.reorder-badge {
		flex-shrink: 0;
		font-size: 10px; color: var(--text-3);
		font-family: var(--font-mono);
		background: rgba(0,0,0,.2);
		border-radius: 3px; padding: 1px 5px;
	}
	.reorder-badge-missing { color: var(--orange); background: rgba(255,159,10,.1); }
	.reorder-arrows { flex-shrink: 0; display: flex; gap: 2px; }
	.reorder-arrow {
		background: none; border: none;
		color: var(--text-3); font-size: 10px;
		cursor: pointer; padding: 2px 4px;
		border-radius: 3px;
		transition: color .1s, background .1s;
	}
	.reorder-arrow:hover { color: var(--text); background: rgba(255,255,255,.08); }
	.reorder-arrow:disabled { opacity: .3; pointer-events: none; }

	/* ── Sections ─────────────────────────────────────────────── */
	.meta-section {
		background: var(--bg-2); border: 1px solid var(--sep);
		border-radius: var(--r-md); overflow: hidden;
	}
	.section-title {
		margin: 0; padding: var(--s3) var(--s4);
		font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
		color: var(--text-2); border-bottom: 1px solid var(--sep);
		background: var(--bg-3);
		display: flex; align-items: center; gap: var(--s3);
	}
	.section-title-btn {
		display: flex; align-items: center; justify-content: space-between;
		width: 100%; padding: var(--s3) var(--s4);
		background: var(--bg-3); border: none;
		border-bottom: 1px solid var(--sep);
		font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
		color: var(--text-2); cursor: pointer; text-align: left;
		transition: background .1s;
	}
	.section-title-btn:hover { background: var(--bg-4); }
	.details-sub { font-size: 11px; font-weight: 400; color: var(--text-3); text-transform: none; letter-spacing: 0; }

	.section-subtitle {
		padding: var(--s2) var(--s4);
		font-size: 11px; font-weight: 600; color: var(--text-3);
		letter-spacing: .04em; text-transform: uppercase;
		border-bottom: 1px solid rgba(84,84,88,.2);
		background: rgba(0,0,0,.1);
	}
	.jellyfin-warn { font-size: 11px; font-weight: 500; color: var(--orange); text-transform: none; letter-spacing: 0; }

	.multi-hint {
		padding: var(--s2) var(--s4);
		font-size: 11px; color: var(--text-3);
		border-bottom: 1px solid rgba(84,84,88,.2);
	}
	.multi-hint code { font-size: 10px; background: rgba(0,0,0,.25); padding: 1px 4px; border-radius: 3px; }

	/* ── Grid rows ────────────────────────────────────────────── */
	.meta-grid { display: flex; flex-direction: column; }
	.details-grid { background: rgba(0,0,0,.08); }

	.meta-row {
		display: flex; align-items: center;
		gap: var(--s3); padding: var(--s2) var(--s4);
		border-bottom: 1px solid rgba(84,84,88,.2);
		min-height: 36px;
	}
	.meta-row:last-child { border-bottom: none; }
	.meta-row.row-warn { background: rgba(255,159,10,.06); }

	.meta-key {
		flex-shrink: 0; width: 180px;
		font-size: 12px; font-weight: 500; color: var(--text-3);
	}
	.meta-val {
		flex: 1; font-size: 13px; color: var(--text);
		word-break: break-word; line-height: 1.5;
	}
	.tag-present { color: var(--green); }
	.tag-absent  { color: var(--text-3); }
	.mono  { font-family: var(--font-mono); }
	.small { font-size: 11px; }

	/* ── Editable inputs ──────────────────────────────────────── */
	.meta-input {
		flex: 1; background: var(--bg-3);
		border: 1px solid rgba(255,255,255,.08);
		border-radius: var(--r-sm);
		color: var(--text); font-size: 13px;
		padding: 5px 10px; outline: none;
		font-family: inherit;
		transition: border-color .15s;
	}
	.meta-input:focus { border-color: var(--blue); background: var(--bg-4); }
	.meta-input.input-warn { border-color: rgba(255,159,10,.4); }

	/* ── Save bar ─────────────────────────────────────────────── */
	.save-bar {
		display: flex; align-items: center; justify-content: flex-end;
		gap: var(--s3); padding: var(--s3) var(--s4);
		border-top: 1px solid var(--sep);
		background: var(--bg-3);
	}
	.save-error { font-size: 12px; color: var(--red); flex: 1; }

	/* ── Details toggle ───────────────────────────────────────── */
	.details-toggle {
		display: flex; align-items: center; gap: 6px;
		width: 100%; padding: var(--s2) var(--s4);
		background: none; border: none;
		border-top: 1px solid rgba(84,84,88,.2);
		color: var(--blue); font-size: 12px; font-weight: 500;
		cursor: pointer; text-align: left;
		transition: background .1s;
	}
	.details-toggle:hover { background: rgba(10,132,255,.06); }

	/* ── Cover upload ─────────────────────────────────────────── */
	.cover-upload-zone {
		padding: var(--s4);
		border-top: 1px solid rgba(84,84,88,.2);
	}
	.cover-hint { font-size: 12px; color: var(--text-3); margin: 0 0 var(--s2); }
	.cover-hint kbd {
		font-size: 11px; background: var(--bg-4);
		border: 1px solid var(--sep); border-radius: 3px;
		padding: 1px 5px; font-family: inherit;
	}
	.cover-drop-row { display: flex; align-items: center; gap: var(--s3); flex-wrap: wrap; }
	.hidden-file { display: none; }
	.cover-preview-area {
		padding: var(--s4);
		border-top: 1px solid rgba(84,84,88,.2);
		display: flex; gap: var(--s4);
	}
	.cover-item { display: flex; flex-direction: column; align-items: center; gap: var(--s2); }
	.cover-thumb {
		width: 100px; height: 100px; object-fit: cover;
		border-radius: var(--r-sm); border: 1px solid var(--sep); background: var(--bg-3);
	}
	.cover-label { font-size: 11px; color: var(--text-3); }

	/* ── Global btn variants ──────────────────────────────────── */
	:global(.btn-orange) { background: rgba(255,159,10,.15); color: var(--orange); border: 1px solid rgba(255,159,10,.3); }
	:global(.btn-orange:hover) { background: rgba(255,159,10,.25); }
	:global(.loading) { opacity: .6; pointer-events: none; }

	/* ── Audit métadonnées ────────────────────────────────────── */
	.audit-intro { padding: var(--s4); }
	.audit-intro .cover-hint { margin-bottom: var(--s3); line-height: 1.5; }

	.audit-album { border-bottom: 1px solid rgba(84,84,88,.2); }
	.audit-album:last-of-type { border-bottom: none; }
	.audit-album-head {
		display: flex; align-items: baseline; justify-content: space-between;
		gap: var(--s3); padding: var(--s2) var(--s4);
		background: rgba(0,0,0,.1);
		border-bottom: 1px solid rgba(84,84,88,.2);
	}
	.audit-album-name { font-size: 13px; font-weight: 600; color: var(--text); }
	.audit-itunes { font-size: 11px; color: var(--green); flex-shrink: 0; }
	.audit-itunes-miss { color: var(--text-3); }

	.audit-rec {
		display: flex; align-items: flex-start; gap: var(--s3);
		padding: var(--s2) var(--s4);
		border-bottom: 1px solid rgba(84,84,88,.14);
		cursor: pointer;
		transition: background .1s;
	}
	.audit-rec:hover { background: rgba(255,255,255,.03); }
	.audit-rec input[type='checkbox'] { margin-top: 3px; accent-color: var(--blue); cursor: pointer; }
	.audit-rec-body { flex: 1; min-width: 0; }
	.audit-rec-line { font-size: 13px; color: var(--text); line-height: 1.5; word-break: break-word; }
	.audit-current  { color: var(--text-3); }
	.audit-arrow    { color: var(--text-3); margin: 0 2px; }
	.audit-proposed { color: var(--green); font-weight: 500; }
	.audit-rec-reason { font-size: 11px; color: var(--text-3); margin-top: 2px; }

	.audit-warn {
		font-size: 12px; color: var(--orange);
		padding: var(--s2) var(--s4);
		border-bottom: 1px solid rgba(84,84,88,.14);
		line-height: 1.4;
	}
	.audit-ok { font-size: 12px; color: var(--green); padding: var(--s2) var(--s4); }

	/* ── Home gallery (artist grid) ───────────────────────────── */
	.home-gallery {
		padding: var(--s6);
		overflow-y: auto;
	}
	.home-gallery-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: var(--s4);
	}
	.home-artist-card {
		display: flex; flex-direction: column; align-items: center;
		gap: var(--s2); padding: var(--s3);
		background: none; border: none;
		border-radius: var(--r-md); cursor: pointer;
		transition: background .15s;
		text-align: center;
	}
	.home-artist-card:hover { background: rgba(255,255,255,.06); }
	.home-artist-cover {
		position: relative;
		width: 100%; aspect-ratio: 1;
		border-radius: 50%; overflow: hidden;
		background: var(--bg-3); border: 2px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.home-artist-cover img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover; z-index: 1;
	}
	.home-artist-placeholder { font-size: 32px; color: var(--text-3); z-index: 0; }
	.home-artist-name {
		font-size: 13px; font-weight: 600; color: var(--text);
		width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.home-artist-meta { font-size: 11px; color: var(--text-3); }

	/* ── Responsive (sm < 480px) ─────────────────────────────── */
	@media (max-width: 480px) {
		/* Two-panel → stacked */
		.meta-layout { flex-direction: column; height: auto; overflow: visible; }
		.meta-sidebar { width: 100%; height: 300px; border-right: none; border-bottom: 1px solid var(--sep); }

		/* Rail replié : barre horizontale en haut */
		.sidebar-rail {
			width: 100%; flex-direction: row; justify-content: center;
			padding: var(--s2); gap: var(--s2);
			border-right: none; border-bottom: 1px solid var(--sep);
		}
		.sidebar-rail-label { writing-mode: horizontal-tb; }
		.meta-main { overflow-y: visible; padding: var(--s3); }

		/* Inputs need 16px to avoid iOS zoom */
		.meta-input { font-size: 16px; }

		/* Artist/album headers: stack photo + info */
		.artist-panel { flex-direction: column; gap: var(--s4); padding: var(--s3) 0; }
		.artist-pic-zone { width: 100px; height: 100px; }
		.album-header { flex-direction: column; gap: var(--s4); padding: var(--s3) 0 var(--s4); }
		.album-cover-zone { width: 120px; height: 120px; }

		/* Tag rows: label above value */
		.meta-row { flex-direction: column; align-items: flex-start; gap: var(--s1); min-height: unset; padding: var(--s2) var(--s3); }
		.meta-key { width: 100%; }
		.meta-input { width: 100%; }

		/* Save bar: stack buttons */
		.save-bar { flex-wrap: wrap; }

		/* Home gallery: fewer columns on tiny screens */
		.home-gallery { padding: var(--s3); }
		.home-gallery-grid { grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); }

		/* Hide drag handles (D&D is desktop-only) */
		.lib-drag-handle { display: none; }

		/* Song nav arrows: smaller, tighter gap */
		.song-nav-row { gap: var(--s2); }
		.song-nav-arrow { width: 32px; height: 32px; font-size: 16px; }
	}
</style>
