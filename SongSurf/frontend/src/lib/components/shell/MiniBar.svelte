<script>
	// Mini-barre de téléchargement, visible depuis tous les écrans (comme le
	// lecteur réduit d'une appli de musique). Un appui ouvre « Ajouter ».
	// Elle suit l'ajout en cours : un album = une barre « 3 / 12 titres ».
	import { page } from '$app/state';
	import { myDownloads } from '$lib/downloads.js';
	import { asText, primaryArtist } from '$lib/utils.js';
	import Cover from '../ui/Cover.svelte';

	let d = $derived($myDownloads);
	let job = $derived(d.running ?? d.jobs[0] ?? null);
	let label = $derived(job ? (job.isAlbum ? job.album || job.title : job.title)
		: asText(d.current?.title ?? d.pending[0]?.title, 'En attente'));
	let others = $derived(d.jobs.length > 1 ? ` · +${d.jobs.length - 1} ajout${d.jobs.length > 2 ? 's' : ''}` : '');
	let sub = $derived(d.waitingOther
		? `En attente${d.songsBefore > 0 ? ` · ton tour dans ${d.songsBefore} titre${d.songsBefore > 1 ? 's' : ''}` : ''}`
		: job?.isAlbum
			? `Titre ${Math.min(job.done + 1, job.total)} sur ${job.total}${others}`
			: `${primaryArtist(job?.artist ?? d.current?.artist ?? '')}${others}`);
	let pct = $derived(d.waitingOther || !job ? 0 : job.percent);
	// Sur « Ajouter », la liste « En cours » est déjà affichée : pas de doublon.
	let visible = $derived(d.active && page.url.pathname !== '/');
</script>

{#if visible}
	<a class="minibar" href="/" aria-label="Téléchargements en cours : {label}">
		<Cover label={job?.album || label} size={38} radius={8} />
		<span class="txt">
			<span class="t">{label}</span>
			<span class="s">{sub}</span>
		</span>
		{#if !d.waitingOther && job}<span class="pct">{Math.floor(pct)} %</span>{/if}
		<span class="line" style="width:{pct}%"></span>
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
	.line { position: absolute; left: 0; bottom: 0; height: 3px; background: var(--accent); transition: width 1.4s linear; }
	@media (min-width: 900px) {
		.minibar { left: auto; right: 24px; bottom: 24px; width: 360px; }
	}
</style>
