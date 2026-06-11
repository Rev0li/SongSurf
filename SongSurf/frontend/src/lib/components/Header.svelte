<script>
	import { page } from '$app/stores';
	import { user, theme } from '$lib/stores.js';

	function toggleTheme() {
		theme.update((t) => (t === 'dark' ? 'light' : 'dark'));
	}

	$: activeTab = $page.url.pathname.startsWith('/metadata') ? 'metadata' : 'download';
</script>

<!-- Hauteurs fixes (52 + 40 px) : les pages plein écran (/metadata) calculent
     leur hauteur avec calc(100dvh - 93px) — 1 px de bordure inclus. -->
<div class="app-chrome">
	<header class="header app-header">
		<div class="header-side">
			<a href="/logout" class="btn btn-ghost btn-sm">← Mon espace</a>
		</div>
		<div class="header-brand">
			<span class="header-logo">🎵</span>
			<h1 class="header-title">SongSurf</h1>
		</div>
		<div class="header-side header-side-right">
			{#if $user}
				<span class="badge" title={$user.email || $user.sub}>{$user.pseudo ?? $user.email}</span>
			{/if}
			<button class="btn btn-ghost btn-sm" on:click={toggleTheme} title="Changer de thème" aria-label="Changer de thème">
				{$theme === 'dark' ? '☀️' : '🌙'}
			</button>
		</div>
	</header>
	<nav class="app-tabs">
		<a href="/" class="app-tab" class:app-tab-active={activeTab === 'download'}>⬇️ Téléchargement</a>
		<a href="/metadata" class="app-tab" class:app-tab-active={activeTab === 'metadata'}>🏷️ Métadonnées</a>
	</nav>
</div>

<style>
	.app-chrome {
		position: sticky; top: 0; z-index: 100;
	}
	/* .header (global) est sticky : ici c'est .app-chrome qui colle */
	.app-chrome .header { position: static; }

	.app-header {
		height: 52px;
		padding-top: 0; padding-bottom: 0;
		box-sizing: border-box;
	}
	.header-side {
		flex: 1; min-width: 0;
		display: flex; align-items: center; gap: var(--s3);
	}
	.header-side-right { justify-content: flex-end; }

	.app-tabs {
		height: 40px;
		box-sizing: border-box;
		display: flex; align-items: center; justify-content: center;
		gap: var(--s2);
		background: var(--bg-2);
		border-bottom: 1px solid var(--sep);
	}
	.app-tab {
		padding: 5px 16px;
		border-radius: var(--r-full);
		border: 1px solid transparent;
		font-size: 13px; font-weight: 500;
		color: var(--text-2); text-decoration: none;
		transition: background .15s, color .15s;
	}
	.app-tab:hover { background: rgba(255,255,255,.06); color: var(--text); }
	.app-tab-active {
		background: var(--accent-soft);
		border-color: var(--sep);
		color: var(--text);
	}

	@media (max-width: 480px) {
		.app-header { padding-left: var(--s3); padding-right: var(--s3); }
		.header-side .badge { display: none; }
	}
</style>
