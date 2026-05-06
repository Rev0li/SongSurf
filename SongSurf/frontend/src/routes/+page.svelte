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
			<span class="badge" title={$user.sub}>{$user.email}</span>
		{/if}
		<a href="/donation" class="btn btn-ghost btn-sm">Soutenir</a>
	</nav>
</header>

<DownloadPanel onDownloadQueued={onDownloadQueued} />

<div class="page-body">
	<div class="main-grid">
		<div class="main-column">
			<ProgressZone />
			<LibraryTree bind:this={libraryRef} />
		</div>
		<div class="side-column">
			<RecentDownloads />
		</div>
	</div>
</div>
