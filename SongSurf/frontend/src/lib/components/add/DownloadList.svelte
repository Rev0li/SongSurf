<script>
	// « En cours » (SSF-13) : le titre en cours, la file (albums regroupés), puis
	// les échecs (Réessayer) et les terminés de la session (Voir dans Ma musique).
	import { goto } from '$app/navigation';
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { myDownloads, dlHistory, removeHistory, clearDoneHistory } from '$lib/downloads.js';
	import { albumUrl } from '$lib/library/data.js';
	import { asText, primaryArtist } from '$lib/utils.js';
	import Icon from '../ui/Icon.svelte';
	import Cover from '../ui/Cover.svelte';

	// Titres consécutifs d'un même album = une ligne « Album (12 titres) »
	function group(list) {
		const out = [];
		for (const p of list) {
			const artist = primaryArtist(p.artist);
			const album = asText(p.album);
			const last = out[out.length - 1];
			if (last && last.artist === artist && last.album === album) last.count += 1;
			else out.push({ artist, album, title: asText(p.title, '…'), count: 1 });
		}
		return out;
	}

	let d = $derived($myDownloads);
	let queued = $derived(group(d.pending));
	let errors = $derived($dlHistory.filter((h) => h.status === 'error'));
	let done = $derived($dlHistory.filter((h) => h.status === 'done'));
	let hasAny = $derived(d.active || $dlHistory.length > 0);

	let retrying = $state('');

	async function retry(h) {
		if (!h.url || retrying) return;
		retrying = h.key;
		try {
			const m = h.metadata ?? {};
			await api.download({
				url: h.url, title: m.title, artist: m.artist, album: m.album, year: m.year ?? '',
				track_number: m.track_number ?? '', album_artist: m.album_artist ?? '', artists: m.artists ?? [],
			});
			removeHistory(h.key);
			addToast(`« ${h.title} » relancé.`, 'info');
		} catch (e) {
			addToast(e.message || 'Impossible de relancer.', 'error', 8000);
		} finally {
			retrying = '';
		}
	}

	// Chemin « Artiste/Album/Titre.mp3 » → page de l'album
	function see(h) {
		const parts = (h.filePath ?? '').split('/');
		if (parts.length >= 3) goto(albumUrl(parts.slice(0, -1).join('/')));
		else goto('/library');
	}
</script>

{#if hasAny}
	<section class="dl" aria-labelledby="dl-title">
		<h2 class="sec-title" id="dl-title">
			En cours {#if d.count > 0}<span class="count-pill">{d.count}</span>{/if}
			{#if done.length > 0}<button class="link-btn small right" type="button" onclick={clearDoneHistory}>Effacer les terminés</button>{/if}
		</h2>

		{#if d.waitingOther}
			<p class="note">Un autre membre utilise SongSurf. Tes titres partent juste après{d.songsBefore > 0 ? ` (ton tour dans ${d.songsBefore} titre${d.songsBefore > 1 ? 's' : ''})` : ''}.</p>
		{/if}

		<ul class="qlist">
			{#if d.current}
				<li class="qitem">
					<Cover label={d.current.album || d.current.title} size={44} />
					<div class="txt">
						<div class="t">{asText(d.current.title, '…')}</div>
						<div class="s">{primaryArtist(d.current.artist ?? '')}</div>
						<div class="bar" aria-hidden="true"><i style="width:{d.percent}%"></i></div>
					</div>
					<span class="pct">{d.percent} %</span>
				</li>
			{/if}
			{#each queued as g, i (i)}
				<li class="qitem">
					<Cover label={g.album || g.title} size={44} />
					<div class="txt">
						<div class="t">{g.count > 1 ? g.album || g.title : g.title}</div>
						<div class="s">{g.artist}{g.count > 1 ? ` · ${g.count} titres` : ''}</div>
						<div class="s">{i === 0 && !d.current && !d.waitingOther ? 'Le prochain' : 'En attente'}</div>
					</div>
				</li>
			{/each}
			{#each errors as h (h.key)}
				<li class="qitem">
					<Cover label={h.album || h.title} size={44} />
					<div class="txt">
						<div class="t">{h.title}</div>
						<div class="s">{primaryArtist(h.artist)}</div>
						<div class="s error">Échec : {h.error}</div>
						<div class="acts">
						{#if h.url}
							<button class="btn btn-soft btn-sm with-ico" type="button" onclick={() => retry(h)} disabled={!!retrying}>
								<Icon name="retry" size={16} />Réessayer
							</button>
						{/if}
							<button class="btn btn-ghost btn-sm" type="button" onclick={() => removeHistory(h.key)}>Retirer</button>
						</div>
					</div>
				</li>
			{/each}
			{#each done as h (h.key)}
				<li class="qitem">
					<Cover label={h.album || h.title} size={44} />
					<div class="txt">
						<div class="t">{h.title}</div>
						<div class="s">{primaryArtist(h.artist)}</div>
						<div class="s ok">{h.skipped ? 'Déjà dans ta bibliothèque' : 'Ajouté à Ma musique'}</div>
					</div>
					<button class="btn btn-soft btn-sm" type="button" onclick={() => see(h)}>Voir</button>
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
	.bar { margin-top: 6px; }
	.acts { display: flex; align-items: center; gap: var(--s2); margin-top: 6px; }
	.with-ico { display: inline-flex; align-items: center; gap: 6px; }
</style>
