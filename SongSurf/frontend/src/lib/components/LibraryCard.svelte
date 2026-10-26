<script>
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/api.js';
	import { addToast, user, confirmAction } from '$lib/stores.js';

	// La bibliothèque se consulte et se range sur /metadata ; ici, seulement l'accès
	// et l'export ZIP (membres).

	// ── ZIP download ──────────────────────────────────────────────────────────
	// Le serveur construit le ZIP en arrière-plan : on suit l'avancement via
	// /api/zip-status, puis on lance le téléchargement. Un ZIP prêt (même après un
	// redémarrage du serveur) se récupère sans le reconstruire.
	let zip = { status: 'idle' };
	let zipPoll = null;
	// Bibliothèque admin permanente : pas d'export ZIP (SSF-10, refusé aussi côté API).
	$: isAdmin = $user?.role === 'admin';
	$: zipBuilding = zip.status === 'building';
	$: zipLabel = zipBuilding
		? `⏳ ZIP ${zip.done ?? 0} / ${zip.total ?? '…'}`
		: zip.status === 'ready' ? '📥 Récupérer le ZIP' : '📥 Télécharger ZIP';

	onMount(resumeZip);
	onDestroy(stopZipPolling);

	async function resumeZip() {
		if ($user?.role === 'admin') return;
		try {
			zip = await api.zipStatus();
			if (zip.status === 'building') startZipPolling();
		} catch { /* ignore */ }
	}

	function startZipPolling() {
		stopZipPolling();
		zipPoll = setInterval(async () => {
			try {
				zip = await api.zipStatus();
			} catch { return; }
			if (zip.status === 'ready') {
				stopZipPolling();
				startZipDownload();
			} else if (zip.status !== 'building') {
				stopZipPolling();
				if (zip.status === 'error') addToast(zip.error || 'Erreur ZIP.', 'error');
			}
		}, 1000);
	}

	function stopZipPolling() {
		if (zipPoll) clearInterval(zipPoll);
		zipPoll = null;
	}

	async function downloadZip() {
		const ok = await confirmAction({
			title: 'Télécharger la bibliothèque en ZIP ?',
			message:
				'⚠️ Votre musique sera supprimée du serveur dès que le téléchargement est terminé.',
			confirmLabel: 'Télécharger',
			danger: true,
		});
		if (!ok) return;

		if (zip.status === 'ready') {
			startZipDownload();
			return;
		}
		try {
			zip = await api.prepareZip();
			startZipPolling();
		} catch (err) {
			zip = { status: 'idle' };
			addToast(err.message || 'Impossible de créer le ZIP.', 'error');
		}
	}

	function startZipDownload() {
		addToast(`ZIP prêt : ${zip.count} fichiers (${zip.size_mb} MB). Téléchargement…`, 'info');
		window.location.href = (zip.download_url || '/api/download-zip') + '?t=' + Date.now();
		zip = { status: 'idle' };

		// Polling jusqu'à ce que le serveur ait supprimé la bibliothèque (max 5 min)
		let attempts = 0;
		const poll = setInterval(async () => {
			attempts++;
			try {
				const data = await api.getLibrary();
				const empty = (data?.artists?.length ?? 0) === 0 && (data?.playlists?.length ?? 0) === 0;
				if (empty || attempts >= 150) {
					clearInterval(poll);
					if (empty) addToast('✅ Bibliothèque vidée — musique supprimée du serveur.', 'info');
				}
			} catch { /* ignore */ }
		}, 2000);
	}
</script>

<div class="card">
	<h2 class="card-title">📚 Bibliothèque</h2>
	<div class="lib-actions">
		<a class="btn btn-primary" href="/metadata">📚 Voir ma bibliothèque</a>
		{#if !isAdmin}
			<button class="btn btn-success" on:click={downloadZip} disabled={zipBuilding}>
				{zipLabel}
			</button>
		{/if}
	</div>
</div>

<style>
	.lib-actions {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s3);
	}
</style>
