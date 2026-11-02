<script>
	import { untrack } from 'svelte';
	import { downloadStatus, workerBusy, workerBusyByOther } from '$lib/stores.js';
	import { primaryArtist, asText } from '$lib/utils.js';

	let current = $derived($downloadStatus.current_download?.metadata ?? {});
	let pct = $derived(Math.max(0, Math.min(100, Number($downloadStatus.batch_percent ?? 0))));
	let total = $derived(Number($downloadStatus.batch_total ?? 0));

	// Une barre qui ne fait que se remplir : dans un même batch elle ne recule
	// jamais (l'estimation de taille de yt-dlp varie en cours de route). Nouveau
	// batch (total différent) ou worker libre → on repart de zéro.
	let shown = $state(0);
	let shownTotal = $state(0);
	$effect.pre(() => {
		const busy = $workerBusy, t = total, p = pct;
		untrack(() => {
			if (!busy || t !== shownTotal) {
				shown = 0;
				shownTotal = t;
			}
			shown = Math.max(shown, p);
		});
	});

	const PHASE_LABEL = { converting: ' · Conversion MP3…', organizing: ' · Organisation…' };
	let phase = $derived($downloadStatus.progress?.phase ?? '');
	let phaseLabel = $derived(PHASE_LABEL[phase] ?? '');

	let statusLabel = $derived(current.artist
		? `${primaryArtist(current.artist)} — ${asText(current.title, '…')}${phaseLabel}`
		: asText(current.title, 'En attente…'));

	// Worker pris par quelqu'un d'autre : l'admin voit qui et quoi, un membre
	// seulement « un autre membre » + combien de titres passent avant le sien.
	let worker = $derived($downloadStatus.worker ?? {});
	let otherLabel = $derived(worker.owner
		? `${worker.owner} : ${primaryArtist(worker.current?.artist ?? '')} — ${asText(worker.current?.title, '…')}`
		: 'Worker occupé par un autre membre');
	let before = $derived(Number(worker.songs_before_mine ?? 0));
	let waitLabel = $derived(before > 0 ? ` · ton tour dans ${before} morceau${before > 1 ? 'x' : ''}` : '');
</script>

{#if $workerBusy}
	<div class="card" id="progress-zone">
		<div class="pz-header">
			<span class="pz-label">Téléchargement</span>
		</div>
		<div class="progress-total">
			<div class="progress-total-fill" style="width: {$workerBusyByOther ? 100 : shown}%"></div>
		</div>
		{#if $workerBusyByOther}
			<div class="pz-track pz-other">{otherLabel}{waitLabel}</div>
		{:else}
			<div class="pz-track">{statusLabel}</div>
		{/if}
	</div>
{/if}

<style>
.pz-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: var(--s2);
}
.pz-label { font-size: 13px; font-weight: 600; color: var(--text-2); }
.pz-track  { font-size: 13px; color: var(--text-2); margin-top: var(--s2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pz-other  { color: var(--text-3); font-style: italic; }
</style>
