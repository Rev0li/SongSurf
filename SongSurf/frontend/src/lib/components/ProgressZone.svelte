<script>
	import { downloadStatus, workerBusy } from '$lib/stores.js';
	import { primaryArtist, asText } from '$lib/utils.js';

	$: current = $downloadStatus.current_download?.metadata ?? {};
	$: pct = Math.max(0, Math.min(100, Number($downloadStatus.batch_percent ?? 0)));
	$: total = Number($downloadStatus.batch_total ?? 0);
	$: done = Number($downloadStatus.batch_done ?? 0);

	const PHASE_LABEL = { converting: ' · Conversion MP3…', organizing: ' · Organisation…' };
	$: phase = $downloadStatus.progress?.phase ?? '';
	$: phaseLabel = PHASE_LABEL[phase] ?? '';

	$: statusLabel = $workerBusy
		? (current.artist
			? `${primaryArtist(current.artist)} — ${asText(current.title, '…')}${phaseLabel}`
			: asText(current.title, 'En attente…'))
		: 'En attente…';
</script>

{#if $workerBusy}
	<div class="card" id="progress-zone">
		<div class="pz-header">
			<span class="pz-label">Téléchargement</span>
			<span class="pz-count">{done} / {total}</span>
		</div>
		<div class="progress-total">
			<div class="progress-total-fill" style="width: {pct}%"></div>
		</div>
		<div class="pz-track">{statusLabel}</div>
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
.pz-count  { font-size: 12px; color: var(--text-3); }
.pz-track  { font-size: 13px; color: var(--text-2); margin-top: var(--s2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
