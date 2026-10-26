<script>
	import { downloadStatus, workerBusy, workerBusyByOther } from '$lib/stores.js';
	import { primaryArtist, asText } from '$lib/utils.js';

	$: current = $downloadStatus.current_download?.metadata ?? {};
	$: pct = Math.max(0, Math.min(100, Number($downloadStatus.batch_percent ?? 0)));
	$: total = Number($downloadStatus.batch_total ?? 0);

	// Une barre qui ne fait que se remplir : dans un même batch elle ne recule
	// jamais (l'estimation de taille de yt-dlp varie en cours de route). Nouveau
	// batch (total différent) ou worker libre → on repart de zéro.
	let shown = 0;
	let shownTotal = 0;
	$: {
		if (!$workerBusy || total !== shownTotal) {
			shown = 0;
			shownTotal = total;
		}
		shown = Math.max(shown, pct);
	}

	const PHASE_LABEL = { converting: ' · Conversion MP3…', organizing: ' · Organisation…' };
	$: phase = $downloadStatus.progress?.phase ?? '';
	$: phaseLabel = PHASE_LABEL[phase] ?? '';

	$: statusLabel = current.artist
		? `${primaryArtist(current.artist)} — ${asText(current.title, '…')}${phaseLabel}`
		: asText(current.title, 'En attente…');

	// Worker pris par quelqu'un d'autre : l'admin voit qui et quoi, un membre
	// seulement « un autre membre » + combien de titres passent avant le sien.
	$: worker = $downloadStatus.worker ?? {};
	$: otherLabel = worker.owner
		? `${worker.owner} : ${primaryArtist(worker.current?.artist ?? '')} — ${asText(worker.current?.title, '…')}`
		: 'Worker occupé par un autre membre';
	$: before = Number(worker.songs_before_mine ?? 0);
	$: waitLabel = before > 0 ? ` · ton tour dans ${before} morceau${before > 1 ? 'x' : ''}` : '';
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
