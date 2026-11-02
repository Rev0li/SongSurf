<script>
	// « En cours » (SSF-13) : une ligne par ajout — un album = une seule ligne
	// « 3 / 12 titres » avec sa barre —, puis les échecs (Réessayer) et les
	// terminés de la session, regroupés par album (Voir dans Ma musique).
	import { goto } from '$app/navigation';
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { myDownloads, dlHistory, removeHistory, clearDoneHistory } from '$lib/downloads.js';
	import { albumUrl } from '$lib/library/data.js';
	import { asText, primaryArtist } from '$lib/utils.js';
	import Icon from '../ui/Icon.svelte';
	import Cover from '../ui/Cover.svelte';

	const albumKey = (artist, album) => `${primaryArtist(artist ?? '').toLowerCase()}|${asText(album).toLowerCase()}`;

	// Entrées de l'historique d'un même album = un groupe (ordre : le plus récent d'abord)
	function groupHistory(list) {
		const groups = new Map();
		for (const h of list) {
			const k = h.album ? albumKey(h.artist, h.album) : h.key;
			if (!groups.has(k)) groups.set(k, { key: k, album: h.album, artist: primaryArtist(h.artist), items: [] });
			groups.get(k).items.push(h);
		}
		return [...groups.values()];
	}

	let d = $derived($myDownloads);
	// Un album encore en cours n'apparaît pas aussi dans les terminés
	let busyAlbums = $derived(new Set(d.jobs.filter((j) => j.isAlbum).map((j) => albumKey(j.artist, j.album))));
	let errors = $derived(groupHistory($dlHistory.filter((h) => h.status === 'error')));
	let done = $derived(groupHistory($dlHistory.filter((h) => h.status === 'done' && !busyAlbums.has(albumKey(h.artist, h.album)))));
	let hasDone = $derived($dlHistory.some((h) => h.status === 'done'));
	let hasAny = $derived(d.active || $dlHistory.length > 0);

	let retrying = $state('');

	async function retryOne(h) {
		const m = h.metadata ?? {};
		await api.download({
			url: h.url, title: m.title, artist: m.artist, album: m.album, year: m.year ?? '',
			track_number: m.track_number ?? '', album_artist: m.album_artist ?? '', artists: m.artists ?? [],
		});
		removeHistory(h.key);
	}

	async function retry(g) {
		const items = g.items.filter((h) => h.url);
		if (!items.length || retrying) return;
		retrying = g.key;
		let ok = 0;
		try {
			for (const h of items) { await retryOne(h); ok += 1; }
			addToast(ok > 1 ? `${ok} titres relancés.` : `« ${items[0].title} » relancé.`, 'info');
		} catch (e) {
			addToast(e.message || 'Impossible de relancer.', 'error', 8000);
		} finally {
			retrying = '';
		}
	}

	function forget(g) {
		for (const h of g.items) removeHistory(h.key);
	}

	// Chemin « Artiste/Album/Titre.mp3 » → page de l'album
	function see(g) {
		const h = g.items.find((x) => x.filePath) ?? g.items[0];
		const parts = (h.filePath ?? '').split('/');
		if (parts.length >= 3) goto(albumUrl(parts.slice(0, -1).join('/')));
		else goto('/library');
	}

	function doneLabel(g) {
		const n = g.items.length;
		const skipped = g.items.filter((h) => h.skipped).length;
		if (n === 1) return skipped ? 'Déjà dans ta bibliothèque' : 'Ajouté à Ma musique';
		if (skipped === n) return `${n} titres déjà dans ta bibliothèque`;
		return `${n - skipped} titres ajoutés${skipped ? `, ${skipped} déjà là` : ''}`;
	}

	function waitLabel(j, i) {
		if (j.done > 0) return d.waitingOther ? 'En pause : un autre membre passe avant' : 'Titre suivant…';
		return i === 0 && !d.running && !d.waitingOther ? 'Le prochain' : 'En attente';
	}
</script>

{#if hasAny}
	<section class="dl" aria-labelledby="dl-title">
		<h2 class="sec-title" id="dl-title">
			En cours {#if d.count > 0}<span class="count-pill">{d.count}</span>{/if}
			{#if hasDone}<button class="link-btn small right" type="button" onclick={clearDoneHistory}>Effacer les terminés</button>{/if}
		</h2>

		{#if d.waitingOther}
			<p class="note">Un autre membre utilise SongSurf. Tes titres partent juste après{d.songsBefore > 0 ? ` (ton tour dans ${d.songsBefore} titre${d.songsBefore > 1 ? 's' : ''})` : ''}.</p>
		{/if}

		<ul class="qlist">
			{#each d.jobs as j, i (j.key)}
				<li class="qitem">
					<Cover label={j.album || j.title} size={44} />
					<div class="txt">
						<div class="t">{j.isAlbum ? j.album || j.title : j.title}</div>
						<div class="s">{primaryArtist(j.artist)}{j.isAlbum ? ` · ${j.done} / ${j.total} titres` : ''}</div>
						{#if j.active}
							{#if j.isAlbum && j.currentTitle}<div class="s now">{j.currentTitle}</div>{/if}
						{:else}
							<div class="s">{waitLabel(j, i)}</div>
						{/if}
						{#if j.active || j.done > 0}
							<div class="bar" aria-hidden="true"><i style="width:{j.percent}%"></i></div>
						{/if}
					</div>
					{#if j.active || j.done > 0}<span class="pct">{Math.floor(j.percent)} %</span>{/if}
				</li>
			{/each}
			{#each errors as g (g.key)}
				{@const many = g.items.length > 1}
				<li class="qitem">
					<Cover label={g.album || g.items[0].title} size={44} />
					<div class="txt">
						<div class="t">{many ? g.album : g.items[0].title}</div>
						<div class="s">{g.artist}</div>
						<div class="s error">{many ? `${g.items.length} titres en échec : ${g.items[0].error}` : `Échec : ${g.items[0].error}`}</div>
						<div class="acts">
							{#if g.items.some((h) => h.url)}
								<button class="btn btn-soft btn-sm with-ico" type="button" onclick={() => retry(g)} disabled={!!retrying}>
									<Icon name="retry" size={16} />{many ? 'Tout réessayer' : 'Réessayer'}
								</button>
							{/if}
							<button class="btn btn-ghost btn-sm" type="button" onclick={() => forget(g)}>Retirer</button>
						</div>
					</div>
				</li>
			{/each}
			{#each done as g (g.key)}
				{@const many = g.items.length > 1}
				<li class="qitem">
					<Cover label={g.album || g.items[0].title} size={44} />
					<div class="txt">
						<div class="t">{many ? g.album : g.items[0].title}</div>
						<div class="s">{g.artist}</div>
						<div class="s ok">{doneLabel(g)}</div>
					</div>
					<button class="btn btn-soft btn-sm" type="button" onclick={() => see(g)}>Voir</button>
				</li>
			{/each}
		</ul>
	</section>
{/if}

<style>
	.dl { display: flex; flex-direction: column; gap: 6px; }
	.right { margin-left: auto; }
	.small { font-size: 13px; }
	.qlist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
	.qitem { display: grid; grid-template-columns: auto 1fr auto; gap: var(--s3); align-items: center; padding: 8px 0; border-bottom: 1px solid var(--sep); }
	.qitem:last-child { border-bottom: 0; }
	.txt { min-width: 0; display: flex; flex-direction: column; gap: 1px; }
	.t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.s { font-size: 13px; color: var(--text-2); }
	.s.error { color: var(--danger-ink); }
	.s.ok { color: var(--ok-ink); }
	.s.now { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.bar { margin-top: 6px; }
	.acts { display: flex; align-items: center; gap: var(--s2); margin-top: 6px; }
	.with-ico { display: inline-flex; align-items: center; gap: 6px; }
</style>
