<script>
	import { downloadStatus, workerBusy } from '$lib/stores.js';
	import { primaryArtist, asText } from '$lib/utils.js';

	$: current = $downloadStatus.current_download?.metadata ?? {};
	$: pct = Math.max(0, Math.min(100, Number($downloadStatus.batch_percent ?? 0)));
	$: total = Number($downloadStatus.batch_total ?? 0);
	$: done = Number($downloadStatus.batch_done ?? 0);

	$: statusLabel = $workerBusy
		? (current.artist
			? `${primaryArtist(current.artist)} — ${asText(current.title, '…')}`
			: asText(current.title, 'En attente…'))
		: 'En attente…';
</script>

{#if $workerBusy}
	<div class="card" id="progress-zone">
		<h2 class="card-title">⏳ Téléchargement en cours</h2>
		<div class="progress-total">
			<div class="progress-total-fill" style="width: {pct}%"></div>
		</div>
		<div class="progress-text">
			<span>{statusLabel}</span>
			<span>{pct.toFixed(1)}%</span>
		</div>
		<div class="progress-subtext">{done} / {total} titre{total > 1 ? 's' : ''}</div>
	</div>
{/if}
