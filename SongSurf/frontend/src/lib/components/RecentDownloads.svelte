<script>
	import { recentDownloads } from '$lib/stores.js';
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';

	let loading = false;

	// Group individual tracks by their parent folder (album/playlist).
	// filePath example: /data/music/Artist/Album/Title.mp3
	// We extract the folder name (last directory segment) and use the full
	// parent path as key so Artist/Album and Artist/SingleAlbum stay separate.
	function groupByFolder(downloads) {
		const map = new Map(); // folderPath → { name, count, latestTimestamp }
		for (const dl of downloads) {
			if (!dl.filePath) continue;
			const parts = dl.filePath.replace(/\\/g, '/').split('/');
			// drop filename (last part), keep parent dir
			parts.pop();
			const folderPath = parts.join('/');
			const folderName = parts[parts.length - 1] ?? '?';
			if (map.has(folderPath)) {
				map.get(folderPath).count++;
			} else {
				map.set(folderPath, { name: folderName, count: 1, timestamp: dl.timestamp });
			}
		}
		// Return sorted newest-first (insertion order already is newest-first,
		// but explicit sort makes it resilient to future changes).
		return [...map.values()].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
	}

	$: grouped = groupByFolder($recentDownloads);

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

	{#if grouped.length === 0}
		<div class="empty-state">
			<div class="empty-state-icon">📭</div>
			<p class="empty-state-text">Aucun téléchargement</p>
		</div>
	{:else}
		<div id="dl-list">
			{#each grouped as folder (folder.name + folder.timestamp)}
				<div class="dl-item">
					<span class="dl-folder-icon">📁</span>
					<strong>{folder.name}</strong>
					<span class="dl-count">{folder.count} titre{folder.count > 1 ? 's' : ''}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.dl-item {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 4px;
		border-bottom: 1px solid rgba(255, 255, 255, 0.06);
	}
	.dl-item:last-child {
		border-bottom: none;
	}
	.dl-folder-icon {
		font-size: 16px;
		flex-shrink: 0;
	}
	.dl-count {
		margin-left: auto;
		font-size: 12px;
		color: var(--color-text-muted, #888);
		white-space: nowrap;
	}
</style>
