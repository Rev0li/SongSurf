<script>
	// « Ajouter » (SSF-13) : coller un lien YouTube Music → analyse automatique →
	// fiche (pochette, titre, artiste, album) avec « Corriger » replié → Ajouter.
	import { api } from '$lib/api.js';
	import { addToast } from '$lib/stores.js';
	import { asText, inferPlaylistArtist } from '$lib/utils.js';
	import Icon from '../ui/Icon.svelte';
	import Cover from '../ui/Cover.svelte';

	let url = $state('');
	let phase = $state('idle'); // idle | analyzing | ready | error
	let errorMsg = $state('');
	let extract = $state(null);
	let fixOpen = $state(false);
	let submitting = $state(false);
	let input;

	// Champs corrigeables
	let title = $state('');
	let artist = $state('');
	let album = $state('');
	let year = $state('');

	let isAlbum = $derived(!!extract?.is_playlist);
	let songs = $derived(extract?.songs ?? []);

	async function analyze(raw) {
		const link = (raw ?? '').trim();
		if (!link || phase === 'analyzing') return;
		url = link;
		phase = 'analyzing'; errorMsg = ''; extract = null; fixOpen = false;
		try {
			const data = await api.extract(link);
			if (!data.success) throw new Error(data.error || 'Analyse impossible.');
			extract = { ...data, url: link };
			if (data.is_playlist) {
				artist = inferPlaylistArtist(data);
				album = asText(data.title, 'Unknown Album');
				year = asText(data.year);
			} else {
				title = asText(data.title, 'Unknown Title');
				artist = asText(data.artist, 'Unknown Artist');
				album = asText(data.album, 'Unknown Album');
				year = asText(data.year);
			}
			phase = 'ready';
		} catch (e) {
			errorMsg = e.message || 'Analyse impossible.';
			phase = 'error';
		}
	}

	// Bouton « Coller » : lit le presse-papiers (le navigateur demande l'autorisation
	// la 1re fois). Refusé → on explique l'appui long dans le champ.
	async function pasteFromClipboard() {
		try {
			const text = (await navigator.clipboard.readText()).trim();
			if (text) return analyze(text);
			addToast('Le presse-papiers est vide : copie d\'abord le lien dans YouTube Music.', 'info', 6000);
		} catch {
			input?.focus();
			addToast('Ton navigateur bloque la lecture du presse-papiers : appuie longuement dans le champ puis « Coller ».', 'info', 7000);
		}
	}

	function onPaste(e) {
		const text = e.clipboardData?.getData('text')?.trim();
		if (!text) return;
		e.preventDefault();
		analyze(text);
	}

	function onKeydown(e) {
		if (e.key === 'Enter') { e.preventDefault(); analyze(url); }
	}

	function reset() {
		url = ''; phase = 'idle'; extract = null; errorMsg = ''; fixOpen = false;
		title = artist = album = year = '';
	}

	async function add() {
		if (!extract || submitting) return;
		submitting = true;
		try {
			if (isAlbum) {
				await api.downloadPlaylist({
					playlist_metadata: {
						title: asText(album, 'Unknown Album'),
						artist: asText(artist, 'Unknown Artist'),
						year: asText(year),
						songs,
					},
				});
				addToast(`${songs.length} titre${songs.length > 1 ? 's' : ''} ajouté${songs.length > 1 ? 's' : ''} à la file.`, 'info');
			} else {
				await api.download({
					url: extract.url,
					title: asText(title, 'Unknown Title'),
					artist: asText(artist, 'Unknown Artist'),
					album: asText(album, 'Unknown Album'),
					year: asText(year),
					track_number: extract.track_number ?? '',
					duration: extract.duration ?? 0, // estimation de l'avancement
					album_artist: extract.album_artist ?? '',
					// Artiste corrigé à la main → la liste multi-artistes extraite n'est plus fiable
					artists: asText(artist) === asText(extract.artist, 'Unknown Artist') ? (extract.artists ?? []) : [],
				});
				addToast(`« ${asText(title, '?')} » ajouté à la file.`, 'info');
			}
			reset();
		} catch (e) {
			addToast(e.message || 'Impossible d\'ajouter à la file.', 'error', 8000);
		} finally {
			submitting = false;
		}
	}
</script>

<div class="paste">
	<div class="field">
		<Icon name="link" />
		<input
			bind:this={input}
			bind:value={url}
			type="url"
			inputmode="url"
			enterkeyhint="go"
			autocomplete="off"
			aria-label="Lien YouTube Music"
			placeholder="Colle ou tape le lien ici"
			onpaste={onPaste}
			onkeydown={onKeydown}
			disabled={phase === 'analyzing'}
		/>
		{#if url}
			<button class="icon-btn clear" type="button" onclick={reset} aria-label="Effacer le lien"><Icon name="close" size={16} /></button>
		{/if}
	</div>
	<button class="btn btn-primary btn-block btn-big with-ico" type="button" onclick={pasteFromClipboard} disabled={phase === 'analyzing'}>
		<Icon name="clip" />Coller le lien copié
	</button>
	<p class="why center">Un appui suffit : le lien est collé et analysé tout seul.</p>
</div>

{#if phase === 'analyzing'}
	<div class="ss-card" aria-live="polite">
		<div class="state">
			<div class="spinner"></div>
			<div><strong>Analyse du lien…</strong><div class="why">On récupère le titre, l'artiste et la pochette.</div></div>
		</div>
	</div>
{:else if phase === 'error'}
	<div class="ss-card err" role="alert">
		<div class="err-title">Ce lien n'a pas pu être analysé</div>
		<p class="why">{errorMsg}</p>
		{#if /url|lien/i.test(errorMsg)}
			<p class="why">Il doit venir de <b>music.youtube.com</b> : un titre, un album ou une playlist.</p>
		{/if}
		<button class="btn btn-soft btn-sm self-start" type="button" onclick={reset}>Effacer</button>
	</div>
{:else if phase === 'ready' && extract}
	<article class="ss-card">
		<div class="fiche">
			<Cover src={extract.thumbnail_url ?? ''} label={isAlbum ? album : title} size={72} radius={12} />
			<div class="fiche-txt">
				<span class="kind">{isAlbum ? `Album · ${songs.length} titre${songs.length > 1 ? 's' : ''}` : 'Titre'}</span>
				<strong>{isAlbum ? album : title}</strong>
				<span class="why">{artist}{isAlbum ? '' : ` · ${album}`}{year ? ` · ${year}` : ''}</span>
			</div>
			<button class="icon-btn" type="button" onclick={reset} aria-label="Annuler"><Icon name="close" /></button>
		</div>

		{#if isAlbum && songs.length > 0}
			<ol class="preview">
				{#each songs.slice(0, 3) as s, i (i)}<li>{asText(s.title, '…')}</li>{/each}
			</ol>
			{#if songs.length > 3}<p class="why more">et {songs.length - 3} autre{songs.length - 3 > 1 ? 's' : ''} titre{songs.length - 3 > 1 ? 's' : ''}</p>{/if}
		{/if}

		<button class="fix-toggle" type="button" aria-expanded={fixOpen} onclick={() => (fixOpen = !fixOpen)}>
			<Icon name="edit" size={16} />Corriger les infos avant d'ajouter<span class="chev"><Icon name="chev" size={16} /></span>
		</button>
		{#if fixOpen}
			<div class="form">
				{#if !isAlbum}
					<div class="f"><label for="add-title">Titre</label><input id="add-title" class="inp" bind:value={title} /></div>
				{/if}
				<div class="f">
					<label for="add-artist">Artiste</label>
					<input id="add-artist" class="inp" bind:value={artist} />
					{#if !isAlbum}<span class="hint">Plusieurs artistes : sépare-les par « ; »</span>{/if}
				</div>
				<div class="two">
					<div class="f"><label for="add-album">Album</label><input id="add-album" class="inp" bind:value={album} /></div>
					<div class="f"><label for="add-year">Année</label><input id="add-year" class="inp" bind:value={year} inputmode="numeric" placeholder="ex. 2017" /></div>
				</div>
			</div>
		{/if}

		<button class="btn btn-primary btn-block btn-big with-ico" type="button" onclick={add} disabled={submitting}>
			<Icon name="plus" />{submitting ? 'Envoi…' : isAlbum ? `Ajouter les ${songs.length} titres` : 'Ajouter à Ma musique'}
		</button>
	</article>
{/if}

<style>
	.paste { display: flex; flex-direction: column; gap: 10px; }
	.field {
		display: flex; align-items: center; gap: 10px; min-height: 52px; padding: 0 6px 0 14px;
		background: var(--bg-2); border: 1px solid var(--sep); border-radius: var(--r-md); color: var(--text-2);
	}
	.field:focus-within { border-color: var(--accent); }
	.field input { flex: 1; min-width: 0; border: 0; background: none; outline: none; color: var(--text); padding: 14px 0; font: inherit; }
	.field input::placeholder { color: var(--text-3); }
	.clear { width: 34px; height: 34px; }
	.with-ico { display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
	.center { text-align: center; }
	.self-start { align-self: flex-start; }
	.state { display: flex; gap: var(--s3); align-items: center; }
	.fiche { display: flex; gap: var(--s3); align-items: center; }
	.fiche-txt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
	.fiche-txt strong { font-size: 17px; overflow-wrap: anywhere; }
	.kind { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px; color: var(--accent-ink); }
	.preview { margin: 0; padding-left: 20px; color: var(--text-2); font-size: 14px; }
	.more { margin-top: -8px; }
	.fix-toggle {
		display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 12px; border-radius: 12px;
		background: var(--bg-4); border: 0; color: var(--text); font: inherit; font-weight: 600; font-size: 14px; cursor: pointer;
	}
	.chev { margin-left: auto; display: inline-flex; transition: transform .2s; }
	.fix-toggle[aria-expanded='true'] .chev { transform: rotate(180deg); }
</style>
