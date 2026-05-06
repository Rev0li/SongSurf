<script>
	import { recentDownloads } from '$lib/stores.js';

	function groupByFolder(downloads) {
		const map = new Map();
		for (const dl of downloads) {
			if (!dl.filePath) continue;
			const parts = dl.filePath.replace(/\\/g, '/').split('/');
			parts.pop();
			const folderPath = parts.join('/');
			const folderName = parts[parts.length - 1] ?? '?';
			if (map.has(folderPath)) {
				map.get(folderPath).count++;
			} else {
				map.set(folderPath, { name: folderName, count: 1, timestamp: dl.timestamp });
			}
		}
		return [...map.values()].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
	}

	$: grouped = groupByFolder($recentDownloads);
</script>

<div class="card">
	<h2 class="card-title">✅ Téléchargements récents</h2>

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
	.dl-item:last-child { border-bottom: none; }
	.dl-folder-icon { font-size: 16px; flex-shrink: 0; }
	.dl-count {
		margin-left: auto;
		font-size: 12px;
		color: var(--text-2);
		white-space: nowrap;
	}
</style>
