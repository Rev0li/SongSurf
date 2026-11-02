<script>
	// Compte : pseudo, rôle, thème, mise en veille (retour au portail).
	import { user, theme } from '$lib/stores.js';
	import Sheet from '../ui/Sheet.svelte';
	import Icon from '../ui/Icon.svelte';

	let { onClose } = $props();
	let isAdmin = $derived($user?.role === 'admin');
</script>

<Sheet title={$user?.pseudo ?? 'Mon compte'} sub={isAdmin ? 'Administrateur · bibliothèque Jellyfin' : 'Membre'} {onClose}>
	<div class="f">
		<span class="flab">Thème</span>
		<div class="themes" role="group" aria-label="Thème">
			<button type="button" class="btn btn-sm" class:btn-dark={$theme === 'light'} class:btn-soft={$theme !== 'light'}
				aria-pressed={$theme === 'light'} onclick={() => theme.set('light')}><Icon name="sun" size={16} />Clair</button>
			<button type="button" class="btn btn-sm" class:btn-dark={$theme === 'dark'} class:btn-soft={$theme !== 'dark'}
				aria-pressed={$theme === 'dark'} onclick={() => theme.set('dark')}><Icon name="moon" size={16} />Sombre</button>
		</div>
	</div>
	<a class="btn btn-soft btn-block" href="/logout"><Icon name="power" size={18} />Mettre SongSurf en veille</a>
	<p class="why">SongSurf s'endort et tu reviens au portail. Les téléchargements en cours se terminent quand même.</p>
</Sheet>

<style>
	.themes { display: flex; gap: var(--s2); }
	.themes .btn { display: inline-flex; gap: 6px; align-items: center; }
	a.btn { display: inline-flex; gap: 8px; align-items: center; justify-content: center; text-decoration: none; }
</style>
