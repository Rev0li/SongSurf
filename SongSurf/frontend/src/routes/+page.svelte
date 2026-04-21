<script>
	import { user } from '$lib/stores.js';
	import DownloadPanel from '$lib/components/DownloadPanel.svelte';
	import ProgressZone from '$lib/components/ProgressZone.svelte';
	import RecentDownloads from '$lib/components/RecentDownloads.svelte';
	import LibraryTree from '$lib/components/LibraryTree.svelte';

	let libraryRef;

	function onDownloadQueued() {
		libraryRef?.refresh();
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
			<span class="badge badge-primary" title={$user.sub}>{$user.email}</span>
		{/if}
		<a href="/donation" class="btn btn-ghost btn-sm">Donation</a>
	</nav>
</header>

<DownloadPanel onDownloadQueued={onDownloadQueued} />

<div class="main-grid">
	<div class="main-column">
		<ProgressZone />
		<LibraryTree bind:this={libraryRef} />
	</div>
	<div class="side-column">
		<RecentDownloads />
	</div>
</div>

<style>
	.main-grid {
		display: grid;
		grid-template-columns: 70% 30%;
		gap: var(--space-6);
		max-width: 1200px;
		margin: 0 auto;
		padding: var(--space-8) var(--space-5);
	}
	@media (max-width: 1024px) {
		.main-grid { grid-template-columns: 1fr; }
		.side-column { order: -1; }
	}
</style>
