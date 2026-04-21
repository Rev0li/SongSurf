<script>
	import { recentDownloads } from '$lib/stores.js';
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';

	let loading = false;

	async function downloadZip() {
		loading = true;
		try {
			const res = await api.prepareZip();
			if (!res.success) {
				addToast(res.error || 'Impossible de créer le ZIP.', 'error');
				return;
			}
			addToast(`ZIP prêt : ${res.count} fichiers (${res.size_mb} MB). Téléchargement…`, 'info');
			window.location.href = (res.download_url || '/api/download-zip') + '?t=' + Date.now();
		} catch (err) {
			addToast(err.message || 'Erreur ZIP.', 'error');
		} finally {
			loading = false;
		}
	}
</script>

<div class="card">
	<h2 class="card-title">✅ Téléchargements récents</h2>
	<button
		class="btn btn-success btn-block"
		style="margin-bottom: var(--space-3)"
		on:click={downloadZip}
		disabled={loading}
	>
		{loading ? '⏳ Préparation…' : '📥 Télécharger mon ZIP'}
	</button>

	{#if $recentDownloads.length === 0}
		<div class="empty-state">
			<div class="empty-state-icon">📭</div>
			<p class="empty-state-text">Aucun téléchargement</p>
		</div>
	{:else}
		<div id="dl-list">
			{#each $recentDownloads as dl (dl.timestamp)}
				<div class="dl-item">
					<strong>{dl.artist} — {dl.title}</strong>
					{#if dl.filePath}
						<div class="progress-subtext">{dl.filePath}</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
