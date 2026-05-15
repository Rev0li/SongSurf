<script>
	import { fly } from 'svelte/transition';
	import { user, lastCompleted, theme } from '$lib/stores.js';
	import DownloadPanel from '$lib/components/DownloadPanel.svelte';
	import ProgressZone from '$lib/components/ProgressZone.svelte';
	import UrlQueue from '$lib/components/UrlQueue.svelte';
	import LibraryTree from '$lib/components/LibraryTree.svelte';

	function toggleTheme() {
		theme.update((t) => (t === 'dark' ? 'light' : 'dark'));
	}

	let libraryRef;
	let queueRef;
	let completedSong = null;
	let dismissTimer = null;

	$: if ($lastCompleted) {
		completedSong = $lastCompleted;
		libraryRef?.refresh();
		clearTimeout(dismissTimer);
		dismissTimer = setTimeout(() => { completedSong = null; }, 4500);
	}

	function handleAddToQueue(item) {
		queueRef?.enqueue(item);
	}
</script>

<svelte:head>
	<title>Dashboard — SongSurf</title>
</svelte:head>

<header class="header">
	<div class="header-brand">
		<span class="header-logo">🎵</span>
		<h1 class="header-title">SongSurf</h1>
	</div>
	<nav class="header-nav">
		{#if $user?.email}
			<span class="badge" title={$user.sub}>{$user.email}</span>
		{/if}
		<a href="/metadata" class="btn btn-ghost btn-sm">Métadonnées</a>
		<a href="/donation" class="btn btn-ghost btn-sm">Soutenir</a>
		<button class="btn btn-ghost btn-sm" on:click={toggleTheme} title="Changer de thème" aria-label="Changer de thème">
			{$theme === 'dark' ? '☀️' : '🌙'}
		</button>
		<a href="/logout" class="btn btn-ghost btn-sm">Déconnexion</a>
	</nav>
</header>

<DownloadPanel onAddToQueue={handleAddToQueue} />

<div class="page-body">
	<ProgressZone />
	<UrlQueue bind:this={queueRef} />
	<LibraryTree bind:this={libraryRef} />
</div>

<!-- Download completion popup -->
{#if completedSong}
	<div class="dl-notif" transition:fly={{ y: 16, duration: 250 }}>
		<span class="dl-notif-icon">✅</span>
		<div class="dl-notif-text">
			<span class="dl-notif-title">{completedSong.title}</span>
			<span class="dl-notif-artist">{completedSong.artist}</span>
		</div>
		<button class="dl-notif-close" on:click={() => completedSong = null}>✕</button>
	</div>
{/if}

<style>
	.dl-notif {
		position: fixed;
		bottom: 24px;
		right: 24px;
		z-index: 200;
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 16px;
		background: var(--bg-2);
		border: 1px solid var(--sep);
		border-left: 3px solid var(--accent);
		border-radius: var(--r-md);
		box-shadow: var(--shadow-hover);
		max-width: 300px;
		min-width: 200px;
	}
	.dl-notif-icon { font-size: 18px; flex-shrink: 0; }
	.dl-notif-text { flex: 1; min-width: 0; }
	.dl-notif-title {
		display: block;
		font-size: 13px;
		font-weight: 600;
		color: var(--text);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.dl-notif-artist {
		display: block;
		font-size: 11px;
		color: var(--text-3);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		margin-top: 2px;
	}
	.dl-notif-close {
		background: none;
		border: none;
		color: var(--text-3);
		cursor: pointer;
		font-size: 11px;
		padding: 3px 5px;
		flex-shrink: 0;
		border-radius: var(--r-sm);
		line-height: 1;
	}
	.dl-notif-close:hover { color: var(--text); background: var(--bg-4); }
</style>
