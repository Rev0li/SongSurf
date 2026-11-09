<script>
	// Sections avancées du panneau titre (mode expert) : tags TXXX en lecture
	
	/**
	 * @typedef {Object} Props
	 * @property {any} meta - seule, puis « Plus de détails » (audio, état de la pochette).
	 * @property {string} [albumCoverUrl]
	 */

	/** @type {Props} */
	let {
		meta,
		albumCoverUrl = ''
	} = $props();

	let detailsOpen = $state(false);

	let customTags = $derived(meta.id3?.custom_tags ? Object.entries(meta.id3.custom_tags) : []);
</script>

<!-- Custom TXXX (lecture seule) -->
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

<!-- Plus de détails : audio + pochette -->
<section class="meta-section">
	<button class="section-title-btn" onclick={() => detailsOpen = !detailsOpen}>
		<span>{detailsOpen ? '▾' : '▸'} Plus de détails</span>
		<span class="details-sub">Audio · Pochette</span>
	</button>

	{#if detailsOpen}
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

		{#if meta.has_album_cover && albumCoverUrl}
			<div class="cover-preview-area">
				<div class="cover-item">
					{#key albumCoverUrl}
						<img class="cover-thumb" src={albumCoverUrl} alt="Pochette" loading="lazy" />
					{/key}
					<span class="cover-label">Fichier externe</span>
				</div>
			</div>
		{/if}

	{/if}
</section>

<style>
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
</style>
