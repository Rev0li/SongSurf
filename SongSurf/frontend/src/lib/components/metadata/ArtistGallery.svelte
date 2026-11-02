<script>
	// Accueil de /metadata : galerie des artistes (photo ronde, albums, titres).
	import { api } from '$lib/api.js';
	import { tree, imgVersions, selectArtist } from '$lib/metadata/library.js';
	import { countSongs } from '$lib/metadata/id3.js';
</script>

{#if $tree === null}
	<div class="meta-empty">
		<span class="meta-empty-icon">⏳</span>
		<p>Chargement de la bibliothèque…</p>
	</div>
{:else if ($tree.artists?.length ?? 0) > 0}
	<div class="home-gallery">
		<div class="home-gallery-grid">
			{#each ($tree.artists ?? []) as artist (artist.path)}
				<button class="home-artist-card" on:click={() => selectArtist(artist)}>
					<div class="home-artist-cover">
						<img
							src={api.getArtistPictureUrl(artist.path, $imgVersions[artist.path] ?? 0)}
							alt="" loading="lazy"
							on:load={(e) => e.currentTarget.style.display=''}
							on:error={(e) => e.currentTarget.style.display='none'}
						/>
						<div class="home-artist-placeholder">🎤</div>
					</div>
					<div class="home-artist-name" title={artist.name}>{artist.name}</div>
					<div class="home-artist-meta">
						{artist.albums?.length ?? 0} album{(artist.albums?.length ?? 0) > 1 ? 's' : ''}
						· {countSongs(artist.albums)} titres
					</div>
				</button>
			{/each}
		</div>
	</div>
{:else}
	<div class="meta-empty">
		<span class="meta-empty-icon">🎵</span>
		<p>Ta bibliothèque est vide — télécharge tes premiers titres pour la remplir.</p>
		<a href="/" class="btn btn-primary btn-sm">⬇️ Aller au Téléchargement</a>
	</div>
{/if}

<style>
	.home-gallery {
		padding: var(--s6);
		overflow-y: auto;
	}
	.home-gallery-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: var(--s4);
	}
	.home-artist-card {
		display: flex; flex-direction: column; align-items: center;
		gap: var(--s2); padding: var(--s3);
		background: none; border: none;
		border-radius: var(--r-md); cursor: pointer;
		transition: background .15s;
		text-align: center;
	}
	.home-artist-card:hover { background: rgba(255,255,255,.06); }
	.home-artist-cover {
		position: relative;
		width: 100%; aspect-ratio: 1;
		border-radius: 50%; overflow: hidden;
		background: var(--bg-3); border: 2px solid var(--sep);
		display: flex; align-items: center; justify-content: center;
	}
	.home-artist-cover img {
		position: absolute; inset: 0;
		width: 100%; height: 100%; object-fit: cover; z-index: 1;
	}
	.home-artist-placeholder { font-size: 32px; color: var(--text-3); z-index: 0; }
	.home-artist-name {
		font-size: 13px; font-weight: 600; color: var(--text);
		width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.home-artist-meta { font-size: 11px; color: var(--text-3); }

	@media (max-width: 480px) {
		/* Home gallery: fewer columns on tiny screens */
		.home-gallery { padding: var(--s3); }
		.home-gallery-grid { grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); }
	}
</style>
