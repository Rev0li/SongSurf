<script>
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
		<button class="btn btn-ghost btn-sm" on:click={toggleTheme} title="Changer de thème" aria-label="Changer de thème">
			{$theme === 'dark' ? '☀️' : '🌙'}
		</button>
		<a href="/logout" class="btn btn-ghost btn-sm">← Mon espace</a>
	</nav>
</header>

<DownloadPanel onAddToQueue={handleAddToQueue} />

<div class="page-body">
	<ProgressZone />
	<UrlQueue bind:this={queueRef} />
	<LibraryTree bind:this={libraryRef} />
</div>

