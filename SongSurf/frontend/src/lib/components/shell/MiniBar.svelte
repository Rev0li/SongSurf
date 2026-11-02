<script>
	// Mini-barre de téléchargement, visible depuis tous les écrans (comme le
	// lecteur réduit d'une appli de musique). Un appui ouvre « Ajouter ».
	import { untrack } from 'svelte';
	import { page } from '$app/state';
	import { downloadStatus } from '$lib/stores.js';
	import { myDownloads } from '$lib/downloads.js';
	import { asText, primaryArtist } from '$lib/utils.js';
	import Cover from '../ui/Cover.svelte';

	// Barre du lot qui ne recule jamais (l'estimation de yt-dlp varie en route).
	let shown = $state(0);
	let shownTotal = $state(0);
	$effect.pre(() => {
		const active = $myDownloads.active, total = Number($downloadStatus.batch_total ?? 0);
		const p = Math.max(0, Math.min(100, Number($downloadStatus.batch_percent ?? 0)));
		untrack(() => {
			if (!active || total !== shownTotal) { shown = 0; shownTotal = total; }
			shown = Math.max(shown, p);
		});
	});

	let d = $derived($myDownloads);
	let label = $derived(d.current ? asText(d.current.title, '…') : asText(d.pending[0]?.title, 'En attente'));
	let sub = $derived(d.waitingOther
		? `En attente${d.songsBefore > 0 ? ` · ton tour dans ${d.songsBefore} titre${d.songsBefore > 1 ? 's' : ''}` : ''}`
		: `${d.count > 1 ? `${d.count} en cours` : 'En cours'} · ${primaryArtist(d.current?.artist ?? d.pending[0]?.artist ?? '')}`);
	// Sur « Ajouter », la liste « En cours » est déjà affichée : pas de doublon.
	let visible = $derived(d.active && page.url.pathname !== '/');
</script>

{#if visible}
	<a class="minibar" href="/" aria-label="Téléchargements en cours : {label}">
		<Cover label={d.current?.album || label} size={38} radius={8} />
		<span class="txt">
			<span class="t">{label}</span>
			<span class="s">{sub}</span>
		</span>
		{#if !d.waitingOther}<span class="pct">{Math.round(shown)} %</span>{/if}
		<span class="line" style="width:{d.waitingOther ? 0 : shown}%"></span>
	</a>
{/if}

<style>
	.minibar {
		position: fixed; z-index: 210; left: 8px; right: 8px;
		bottom: calc(var(--tabbar-h) + var(--safe-b) + 6px);
		display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px;
		padding: 8px 12px 10px 8px; border-radius: 14px; overflow: hidden;
		background: var(--bg-2); border: 1px solid var(--sep); box-shadow: var(--shadow-soft);
		color: var(--text); text-decoration: none; max-width: 640px; margin: 0 auto;
	}
	.txt { min-width: 0; display: flex; flex-direction: column; }
	.t { font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.s { font-size: 12px; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.line { position: absolute; left: 0; bottom: 0; height: 3px; background: var(--accent); transition: width .4s; }
	@media (min-width: 900px) {
		.minibar { left: auto; right: 24px; bottom: 24px; width: 360px; }
	}
</style>
