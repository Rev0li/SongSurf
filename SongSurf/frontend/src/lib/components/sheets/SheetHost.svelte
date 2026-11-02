<script>
	// Rend le panneau du bas ouvert (store `sheet`). Retour arrière du téléphone
	// → l'entrée d'historique du panneau disparaît → on le ferme (voir ui/sheets.js).
	import { untrack } from 'svelte';
	import { get } from 'svelte/store';
	import { page } from '$app/state';
	import { sheet, closeSheet } from '$lib/ui/sheets.js';
	import AccountSheet from './AccountSheet.svelte';
	import MenuSheet from './MenuSheet.svelte';
	import TrackEditSheet from './TrackEditSheet.svelte';
	import AlbumEditSheet from './AlbumEditSheet.svelte';
	import MoveSheet from './MoveSheet.svelte';
	import FillWizard from './FillWizard.svelte';
	import RecoverSheet from './RecoverSheet.svelte';
	import ToolSheet from './ToolSheet.svelte';

	const KINDS = {
		account: AccountSheet,
		menu: MenuSheet,
		editTrack: TrackEditSheet,
		editAlbum: AlbumEditSheet,
		move: MoveSheet,
		fill: FillWizard,
		recover: RecoverSheet,
		tool: ToolSheet,
	};

	let lastState;
	$effect(() => {
		const st = page.state?.sheetId;
		untrack(() => {
			const open = get(sheet);
			if (open && lastState !== undefined && st !== lastState && open.id === lastState) sheet.set(null);
			lastState = st;
		});
	});

	let Current = $derived($sheet ? KINDS[$sheet.kind] : null);
</script>

{#if $sheet && Current}
	{#key $sheet.id}
		<Current {...$sheet.props} onClose={closeSheet} />
	{/key}
{/if}
