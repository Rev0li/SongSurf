<script>
	import { fly } from 'svelte/transition';
	import { user, lastCompleted } from '$lib/stores.js';
	import DownloadPanel from '$lib/components/DownloadPanel.svelte';
	import ProgressZone from '$lib/components/ProgressZone.svelte';
	import LibraryTree from '$lib/components/LibraryTree.svelte';

	let libraryRef;
	let completedSong = null;
	let dismissTimer = null;

	$: if ($lastCompleted) {
		completedSong = $lastCompleted;
		libraryRef?.refresh();
		clearTimeout(dismissTimer);
		dismissTimer = setTimeout(() => { completedSong = null; }, 4500);
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
		<a href="/donation" class="btn btn-ghost btn-sm">Soutenir</a>
	</nav>
</header>

<DownloadPanel />

<div class="page-body">
	<ProgressZone />
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
		background: rgba(28, 28, 30, 0.88);
		backdrop-filter: blur(24px);
		-webkit-backdrop-filter: blur(24px);
		border: 1px solid rgba(255, 255, 255, 0.10);
		border-left: 3px solid var(--green);
		border-radius: var(--r-md);
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
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
	.dl-notif-close:hover { color: var(--text); background: rgba(255, 255, 255, 0.08); }
</style>
