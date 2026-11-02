<script>
	// Audit des métadonnées d'un artiste (mode expert) : compare chaque album
	// avec iTunes + contrôles de cohérence, propose des corrections à cocher.
	// Rien n'est écrit sans validation.
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { ID3_LABELS } from '$lib/metadata/id3.js';

	export let artistPath;

	let audit    = null;       // rapport /api/library/audit/artist
	let loading  = false;
	let error    = '';
	let selected = new Set();  // ids des recommandations cochées
	let applying = false;

	async function run() {
		if (loading) return;
		loading = true; error = ''; audit = null;
		try {
			const data = await api.auditArtist(artistPath);
			audit = data;
			selected = new Set(
				(data.albums ?? []).flatMap((al) => (al.recommendations ?? []).map((r) => r.id))
			);
		} catch (e) { error = e.message ?? 'Erreur'; }
		finally { loading = false; }
	}

	function toggleRec(id) {
		if (selected.has(id)) selected.delete(id);
		else selected.add(id);
		selected = new Set(selected);
	}

	$: changes = !audit ? [] : (audit.albums ?? []).flatMap((al) =>
		(al.recommendations ?? [])
			.filter((r) => selected.has(r.id))
			.flatMap((r) => (r.changes ?? []).map((c) => ({ path: c.path, field: r.field, value: c.value })))
	);

	async function apply() {
		if (changes.length === 0 || applying) return;
		applying = true;
		try {
			const res = await api.auditApply(changes);
			if ((res.errors ?? []).length === 0) {
				addToast(`${res.applied} tag${res.applied > 1 ? 's' : ''} appliqué${res.applied > 1 ? 's' : ''}.`, 'info');
			} else {
				addToast(`${res.applied} OK, ${res.errors.length} erreur${res.errors.length > 1 ? 's' : ''}.`, 'error');
			}
			await run();
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { applying = false; }
	}
</script>

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
			{#if error}<p class="save-error">{error}</p>{/if}
			<button class="btn btn-primary btn-sm" on:click={run} disabled={loading}>
				{loading ? '⏳ Audit en cours…' : "🔎 Lancer l'audit"}
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
							checked={selected.has(rec.id)}
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
			<button class="btn btn-ghost btn-sm" on:click={run} disabled={loading || applying}>
				{loading ? '⏳…' : '↻ Relancer'}
			</button>
			<button
				class="btn btn-primary btn-sm"
				on:click={apply}
				disabled={changes.length === 0 || applying}
			>
				{applying ? '⏳ Application…' : `✓ Appliquer la sélection (${changes.length})`}
			</button>
		</div>
	{/if}
</section>

<style>
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
</style>
