<script>
	// Onglets du bas (mobile). Toucher « Ma musique » quand on y est déjà ramène
	// à l'accueil de la bibliothèque, comme dans une appli de musique.
	import { page } from '$app/state';
	import Icon from '../ui/Icon.svelte';

	let onLibrary = $derived(page.url.pathname.startsWith('/library'));
</script>

<nav class="tabbar" aria-label="Navigation">
	<a href="/" aria-current={onLibrary ? undefined : 'page'}><Icon name="plus" size={24} />Ajouter</a>
	<a href="/library" aria-current={onLibrary ? 'page' : undefined}><Icon name="music" size={24} />Ma musique</a>
</nav>

<style>
	.tabbar {
		position: fixed; left: 0; right: 0; bottom: 0; z-index: 200;
		display: grid; grid-template-columns: 1fr 1fr;
		height: calc(var(--tabbar-h) + var(--safe-b)); padding-bottom: var(--safe-b);
		background: color-mix(in srgb, var(--bg) 94%, transparent); backdrop-filter: blur(10px);
		border-top: 1px solid var(--sep);
	}
	a {
		display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
		font-size: 11.5px; font-weight: 600; color: var(--text-3); text-decoration: none;
	}
	a[aria-current='page'] { color: var(--text); }
	a[aria-current='page'] :global(.ico) { color: var(--accent-ink); }
	@media (min-width: 900px) { .tabbar { display: none; } }
</style>
