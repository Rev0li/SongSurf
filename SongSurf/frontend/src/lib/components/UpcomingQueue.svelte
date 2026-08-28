<script>
	import { downloadStatus } from '$lib/stores.js';
	import { primaryArtist, asText } from '$lib/utils.js';

	// Le serveur envoie déjà la file dans l'ordre de passage, limitée à mes
	// propres titres (extension ou input) — jamais ceux d'un autre membre.
	// On regroupe les titres consécutifs d'un même album (un album = un job
	// côté serveur) pour ne pas afficher 65 lignes pour une seule discographie.
	function group(list) {
		const out = [];
		for (const p of list) {
			const artist = primaryArtist(p.artist);
			const album = asText(p.album, '');
			const last = out[out.length - 1];
			if (last && last.artist === artist && last.album === album) {
				last.count += 1;
			} else {
				out.push({ artist, album, title: asText(p.title, '…'), count: 1 });
			}
		}
		return out;
	}

	$: pending = $downloadStatus.pending ?? [];
	$: grouped = group(pending);
</script>

{#if grouped.length > 0}
	<div class="card">
		<div class="upcoming-header">
			<h2 class="card-title" style="margin:0">🔜 À venir</h2>
			<span class="queue-badge">{pending.length} titre{pending.length > 1 ? 's' : ''}</span>
		</div>
		<ul class="upcoming-list">
			{#each grouped as g, i (i)}
				<li class="upcoming-item">
					<span class="upcoming-artist">{g.artist}</span>
					<span class="upcoming-sep">—</span>
					{#if g.count > 1}
						<span class="upcoming-label">{g.album || g.title} <span class="upcoming-count">({g.count} titres)</span></span>
					{:else}
						<span class="upcoming-label">{g.title}</span>
					{/if}
				</li>
			{/each}
		</ul>
	</div>
{/if}

<style>
	.upcoming-header {
		display: flex;
		align-items: center;
		gap: var(--s3);
		margin-bottom: var(--s3);
	}
	.queue-badge {
		font-size: 11px;
		background: var(--blue);
		color: #fff;
		padding: 2px 8px;
		border-radius: var(--r-full);
		font-weight: 600;
	}
	.upcoming-list {
		list-style: none;
		margin: 0; padding: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
		max-height: 260px;
		overflow-y: auto;
	}
	.upcoming-item {
		display: flex;
		align-items: baseline;
		gap: 6px;
		padding: 6px var(--s2);
		border-radius: var(--r-sm);
		background: var(--bg-3);
		font-size: 13px;
		min-width: 0;
	}
	.upcoming-artist { flex-shrink: 0; font-weight: 600; color: var(--text); }
	.upcoming-sep { flex-shrink: 0; color: var(--text-3); }
	.upcoming-label {
		flex: 1; min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--text-2);
	}
	.upcoming-count { color: var(--text-3); font-size: 11px; }
</style>
