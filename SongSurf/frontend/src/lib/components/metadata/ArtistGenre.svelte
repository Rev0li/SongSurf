<script>
	import { untrack } from 'svelte';
	// Genre (TCON) de l'artiste (mode expert) : une saisie réécrite sur tous ses
	// titres, pré-remplie avec la combinaison de genres la plus fréquente.
	import { api } from '$lib/api.js';
	import { addToast, confirmAction } from '$lib/stores.js';
	import { countSongs } from '$lib/metadata/id3.js';

	let {
		artist,
		albums = [],
		albumStatus = {},
		onApplied = () => {}
	} = $props();

	let genre   = $state('');
	let touched = $state(false); // saisie manuelle en cours → ne pas écraser par le pré-remplissage
	let saving  = $state(false);


	function prefill(status) {
		if (touched || Object.keys(status).length === 0) return;
		const counts = new Map();
		for (const st of Object.values(status)) {
			const g = (st.genres ?? []).join('; ');
			if (g) counts.set(g, (counts.get(g) ?? 0) + 1);
		}
		genre = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? '';
	}

	async function apply() {
		const value = genre.trim();
		if (!value || saving) return;
		const nSongs = countSongs(albums);
		const ok = await confirmAction({
			title: `Appliquer « ${value} » ?`,
			message: `Le genre (TCON) sera réécrit sur les ${nSongs} titre${nSongs > 1 ? 's' : ''} `
				+ `des ${albums.length} album${albums.length > 1 ? 's' : ''} de ${artist.name}.`,
			confirmLabel: 'Appliquer',
		});
		if (!ok) return;
		saving = true;
		try {
			const res = await api.setArtistGenre(artist.path, value);
			if ((res.errors ?? []).length === 0) {
				addToast(`Genre appliqué à ${res.updated} titre${res.updated > 1 ? 's' : ''}.`, 'info');
			} else {
				addToast(`${res.updated} OK, ${res.errors.length} erreur${res.errors.length > 1 ? 's' : ''}.`, 'error');
			}
			touched = false;
			onApplied(); // rafraîchit badges + pré-remplissage
		} catch (e) { addToast(e.message ?? 'Erreur', 'error'); }
		finally { saving = false; }
	}
	// Pré-remplit dès que le statut des albums est chargé (objet vide = en cours de chargement).
	$effect.pre(() => {
		const status = albumStatus;
		untrack(() => prefill(status));
	});
</script>

<div class="artist-genre-zone">
	<label class="cover-hint" for="artist-genre-input">
		Genre (TCON) — réécrit sur tous les albums · plusieurs valeurs : « ; »
	</label>
	<div class="artist-genre-row">
		<input
			id="artist-genre-input"
			class="meta-input"
			placeholder="Rap français; Hip-hop"
			bind:value={genre}
			oninput={() => { touched = true; }}
			onkeydown={(e) => e.key === 'Enter' && apply()}
		/>
		<button
			class="btn btn-primary btn-sm"
			onclick={apply}
			disabled={saving || !genre.trim()}
		>
			{saving ? '⏳…' : '🎼 Appliquer'}
		</button>
	</div>
</div>

<style>
	.artist-genre-zone { margin-bottom: var(--s4); }
	.artist-genre-zone .cover-hint { display: block; }
	.artist-genre-row { display: flex; align-items: center; gap: var(--s2); }
	.artist-genre-row .meta-input { max-width: 300px; }
</style>
