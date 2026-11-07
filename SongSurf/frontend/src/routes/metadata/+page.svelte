<script>
	// Ancienne adresse de la bibliothèque (avant SSF-13) → « Ma musique ».
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	onMount(() => goto('/library', { replaceState: true }));
</script>
