<script>
	// Barre du haut : retour au portail, logo, compte. Sur grand écran, elle porte
	// aussi les onglets (sur mobile ils sont en bas, voir TabBar).
	import { page } from '$app/state';
	import { user } from '$lib/stores.js';
	import { openSheet } from '$lib/ui/sheets.js';
	import Icon from '../ui/Icon.svelte';

	let initial = $derived(($user?.pseudo ?? $user?.sub ?? '?').trim().charAt(0).toUpperCase() || '?');
	let onLibrary = $derived(page.url.pathname.startsWith('/library'));
</script>

<header class="topbar">
	<div class="left">
		<a class="home" href="/logout" title="Retour au portail (SongSurf se met en veille)">
			<Icon name="back" size={16} /><span class="home-label">Mon espace</span>
		</a>
		<nav class="top-tabs" aria-label="Navigation">
			<a href="/" aria-current={onLibrary ? undefined : 'page'}><Icon name="plus" size={18} />Ajouter</a>
			<a href="/library" aria-current={onLibrary ? 'page' : undefined}><Icon name="music" size={18} />Ma musique</a>
		</nav>
	</div>
	<a class="logo" href="/" aria-label="SongSurf, accueil">SongSurf</a>
	<button class="avatar" type="button" onclick={() => openSheet('account')} aria-label="Mon compte ({$user?.pseudo ?? 'inconnu'})">
		{initial}
		{#if $user?.role === 'admin'}<span class="badge-admin">ADMIN</span>{/if}
	</button>
</header>

<style>
	.topbar {
		position: sticky; top: 0; z-index: 100; height: var(--topbar-h);
		display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: var(--s2);
		padding: 0 var(--s4); background: color-mix(in srgb, var(--bg) 92%, transparent);
		backdrop-filter: blur(10px); border-bottom: 1px solid var(--sep);
	}
	.left { justify-self: start; display: flex; align-items: center; gap: var(--s4); min-width: 0; }
	.home {
		display: inline-flex; align-items: center; gap: 2px;
		font-size: 13px; color: var(--text-2); text-decoration: none; padding: 6px 4px; white-space: nowrap;
	}
	.home:hover { color: var(--text); }
	.logo { font-family: var(--font-display); font-size: clamp(22px, 7vw, 28px); line-height: 1; letter-spacing: .5px; white-space: nowrap; color: var(--text); text-decoration: none; }
	.top-tabs { display: none; }
	.avatar {
		justify-self: end; position: relative; width: 36px; height: 36px; border-radius: 50%; border: 0; cursor: pointer;
		background: var(--primary); color: #111; font: inherit; font-weight: 700;
	}
	.badge-admin {
		position: absolute; right: -6px; bottom: -4px; font-size: 9px; font-weight: 700; line-height: 1;
		background: var(--text); color: var(--bg); border-radius: 6px; padding: 2px 4px;
	}
	/* Très petits écrans (320 px) : la flèche seule, pour laisser le titre au centre. */
	@media (max-width: 359px) { .home-label { display: none; } }
	@media (min-width: 900px) {
		.logo { font-size: 34px; }
		.top-tabs { display: flex; gap: var(--s1); }
		.top-tabs a {
			display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: var(--r-full);
			color: var(--text-2); text-decoration: none; font-weight: 600; font-size: 14px;
		}
		.top-tabs a:hover { color: var(--text); background: var(--bg-4); }
		.top-tabs a[aria-current='page'] { color: var(--text); background: var(--bg-4); }
	}
</style>
