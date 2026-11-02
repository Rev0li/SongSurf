<script>
	import Header from '$lib/components/Header.svelte';
	import DownloadPanel from '$lib/components/DownloadPanel.svelte';
	import ProgressZone from '$lib/components/ProgressZone.svelte';
	import UpcomingQueue from '$lib/components/UpcomingQueue.svelte';
	import LibraryCard from '$lib/components/LibraryCard.svelte';
</script>

<svelte:head>
	<title>Dashboard — SongSurf</title>
</svelte:head>

<Header />

<DownloadPanel />

<div class="page-body">
	<ProgressZone />
	<UpcomingQueue />
	<LibraryCard />
</div>
