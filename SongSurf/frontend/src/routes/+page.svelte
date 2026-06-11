<script>
	import { lastCompleted } from '$lib/stores.js';
	import Header from '$lib/components/Header.svelte';
	import DownloadPanel from '$lib/components/DownloadPanel.svelte';
	import ProgressZone from '$lib/components/ProgressZone.svelte';
	import UrlQueue from '$lib/components/UrlQueue.svelte';
	import LibraryTree from '$lib/components/LibraryTree.svelte';

	let libraryRef;
	let queueRef;
	let shownTimestamp = '';

	$: if ($lastCompleted && $lastCompleted.timestamp !== shownTimestamp) {
		shownTimestamp = $lastCompleted.timestamp;
		libraryRef?.refresh();
	}

	function handleAddToQueue(item) {
		queueRef?.enqueue(item);
	}
</script>

<svelte:head>
	<title>Dashboard — SongSurf</title>
</svelte:head>

<Header />

<DownloadPanel onAddToQueue={handleAddToQueue} />

<div class="page-body">
	<ProgressZone />
	<UrlQueue bind:this={queueRef} />
	<LibraryTree bind:this={libraryRef} />
</div>

