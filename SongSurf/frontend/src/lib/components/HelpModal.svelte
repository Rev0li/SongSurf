<script>
	import { helpOpen } from '$lib/stores.js';

	// Deux catégories ; chacune est un carrousel d'étapes (texte + image).
	// Les images sont des placeholders : dépose les fichiers dans /static/help/.
	const categories = {
		download: {
			label: 'Téléchargement',
			icon: '⬇️',
			tagline: 'Récupérer de la musique depuis YouTube Music',
			steps: [
				{
					title: 'Coller une URL & télécharger',
					img: '/help/download-1.png',
					body:
						"Copie le lien d'un titre, d'un album depuis music.youtube.com, " +
						"colle-le dans le champ puis valide. SongSurf extrait les métadonnées et lance le téléchargement en MP3.",
				},
				{
					title: "File d'attente & progression",
					img: '/help/download-2.png',
					body:
						"Les ajouts s'empilent dans la file d'attente et sont traités un par un. " +
						"La zone de progression affiche le titre en cours, l'avancement et l'état de la file.",
				},
				{
					title: 'Export ZIP de ta bibliothèque',
					img: '/help/download-3.png',
					body:
						"Quand tes morceaux sont prêts, prépare puis télécharge un ZIP de ta bibliothèque. " +
						"⚠️ Pour les membres, la bibliothèque est supprimée après l'export (bibliothèques temporaires).",
				},
			],
		},
		metadata: {
			label: 'Métadonnées',
			icon: '🏷️',
			tagline: 'Corriger les tags et organiser la bibliothèque',
			steps: [
				{
					title: "Éditeur de métadonnées",
					img: '/help/metadata-1.png',
					body:
						"Navigue dans l'arbre Artiste / Album / Titre et édite les tags ID3 : titre, artiste(s), " +
						"album, année, genre, compositeur. Sépare les valeurs multiples par « ; ».",
				},
				{
					title: 'Audit par artiste',
					img: '/help/metadata-2.png',
					body:
						"L'audit compare chaque album à iTunes et vérifie la cohérence locale (numéros de piste, " +
						"album-artist, pochettes…). Rien n'est écrit sans ta validation explicite.",
				},
				{
					title: 'Numéroter les pistes',
					img: '/help/metadata-3.png',
					body:
						"Réordonne les pistes d'un album par glisser-déposer, puis applique : SongSurf réécrit " +
						"les numéros de piste « 1/N … N/N » sur tout l'album.",
				},
			],
		},
	};

	let view = 'home'; // 'home' | 'download' | 'metadata'
	let stepIndex = 0;
	let imgError = false;

	$: cat = view === 'home' ? null : categories[view];
	$: step = cat ? cat.steps[stepIndex] : null;
	$: { step; imgError = false; } // reset image fallback whenever the step changes

	function open(catKey) {
		view = catKey;
		stepIndex = 0;
	}
	function home() {
		view = 'home';
	}
	function next() {
		if (cat && stepIndex < cat.steps.length - 1) stepIndex += 1;
	}
	function prev() {
		if (stepIndex > 0) stepIndex -= 1;
	}
	function close() {
		helpOpen.set(false);
		// Revenir à l'accueil pour la prochaine ouverture
		view = 'home';
		stepIndex = 0;
	}

	function onKeydown(e) {
		if (!$helpOpen) return;
		if (e.key === 'Escape') close();
		else if (view !== 'home' && e.key === 'ArrowRight') next();
		else if (view !== 'home' && e.key === 'ArrowLeft') prev();
	}
</script>

<svelte:window on:keydown={onKeydown} />

{#if $helpOpen}
	<div
		class="help-overlay"
		role="presentation"
		on:click|self={close}
	>
		<div class="help-card" class:is-step={view !== 'home'} role="dialog" aria-modal="true" aria-label="Aide SongSurf">
			<button class="help-close btn btn-ghost btn-sm" on:click={close} aria-label="Fermer l'aide" title="Fermer (Échap)">✕</button>

			{#if view === 'home'}
				<div class="help-home">
					<h2 class="help-h2">Bienvenue sur SongSurf 🎵</h2>
					<p class="help-lead">Choisis ce que tu veux apprendre :</p>
					<div class="help-choices">
						{#each Object.entries(categories) as [key, c]}
							<button class="help-choice" on:click={() => open(key)}>
								<span class="help-choice-icon">{c.icon}</span>
								<span class="help-choice-label">{c.label}</span>
								<span class="help-choice-tag">{c.tagline}</span>
							</button>
						{/each}
					</div>
				</div>
			{:else}
				<div class="help-step">
					<div class="help-step-head">
						<button class="btn btn-ghost btn-sm" on:click={home}>← Catégories</button>
						<span class="help-crumb">{cat.icon} {cat.label}</span>
					</div>

					<div class="help-media">
						{#if imgError}
							<div class="help-img-ph">
								<span class="help-img-ph-icon">🖼️</span>
								<span class="help-img-ph-path">{step.img}</span>
							</div>
						{:else}
							<img src={step.img} alt={step.title} on:error={() => (imgError = true)} />
						{/if}
					</div>

					<h3 class="help-step-title">{step.title}</h3>
					<p class="help-step-body">{step.body}</p>

					<div class="help-nav">
						<button class="btn btn-ghost btn-sm" on:click={prev} disabled={stepIndex === 0}>← Précédent</button>
						<div class="help-progress-group">
							<div class="help-dots">
								{#each cat.steps as _, i}
									<span class="help-dot" class:active={i === stepIndex}></span>
								{/each}
							</div>
							<span class="help-progress">{stepIndex + 1} / {cat.steps.length}</span>
						</div>
						{#if stepIndex < cat.steps.length - 1}
							<button class="btn btn-primary btn-sm" on:click={next}>Suivant →</button>
						{:else}
							<button class="btn btn-primary btn-sm" on:click={close}>Terminer ✓</button>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.help-overlay {
		position: fixed; inset: 0; z-index: 9000;
		display: flex; align-items: center; justify-content: center;
		background: rgba(0, 0, 0, 0.6);
		padding: var(--s4);
		backdrop-filter: blur(2px);
	}
	.help-card {
		position: relative;
		width: 100%; max-width: 720px;
		max-height: calc(100dvh - 2 * var(--s4));
		overflow-y: auto;
		background: var(--bg-2);
		border: 1px solid var(--sep);
		border-radius: var(--r-xl, 16px);
		box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
		padding: var(--s6) var(--s6) var(--s5);
	}
	/* Mode étape : carte quasi plein écran pour laisser un maximum de place à l'image. */
	.help-card.is-step {
		max-width: min(1280px, 96vw);
		width: 96vw;
		height: calc(100dvh - 2 * var(--s4));
		max-height: none;
		overflow: hidden;
		display: flex; flex-direction: column;
	}
	.help-close {
		position: absolute; top: var(--s3); right: var(--s3);
		z-index: 2;
	}

	/* ── Accueil : choix de catégorie ── */
	.help-h2 { margin: 0 0 var(--s2); font-size: 22px; color: var(--text); }
	.help-lead { margin: 0 0 var(--s5); color: var(--text-2); }
	.help-choices {
		display: grid; grid-template-columns: 1fr 1fr; gap: var(--s4);
	}
	.help-choice {
		display: flex; flex-direction: column; align-items: flex-start; gap: var(--s2);
		text-align: left;
		padding: var(--s5);
		background: var(--bg-3);
		border: 1px solid var(--sep);
		border-radius: var(--r-lg, 12px);
		cursor: pointer;
		transition: border-color .15s, background .15s, transform .12s;
	}
	.help-choice:hover {
		border-color: var(--accent);
		background: var(--accent-soft);
		transform: translateY(-2px);
	}
	.help-choice-icon { font-size: 28px; }
	.help-choice-label { font-size: 16px; font-weight: 600; color: var(--text); }
	.help-choice-tag { font-size: 13px; color: var(--text-2); }

	/* ── Étape : carrousel ── */
	.help-step {
		display: flex; flex-direction: column;
		flex: 1; min-height: 0;
	}
	.help-step-head {
		display: flex; align-items: center; justify-content: space-between;
		gap: var(--s2); margin-bottom: var(--s3);
		padding-right: 40px; /* laisse la place à la croix de fermeture */
		flex-shrink: 0;
	}
	.help-crumb { font-weight: 600; color: var(--text); }
	.help-progress { font-size: 13px; color: var(--text-3, var(--text-2)); }
	.help-progress-group { display: flex; align-items: center; gap: var(--s3); }

	.help-media {
		width: 100%;
		flex: 1; min-height: 0;
		aspect-ratio: 16 / 9;
		border-radius: var(--r-lg, 12px);
		overflow: hidden; margin-bottom: var(--s3);
		background: var(--bg-3);
		border: 1px solid var(--sep);
	}
	/* En mode plein écran l'image occupe tout l'espace dispo, sans aspect-ratio
	   imposé ni recadrage (contain → aucune partie du screenshot n'est coupée). */
	.is-step .help-media { aspect-ratio: auto; }
	.help-media img { width: 100%; height: 100%; object-fit: contain; display: block; }
	.help-img-ph {
		width: 100%; height: 100%;
		display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s2);
		color: var(--text-3, var(--text-2));
	}
	.help-img-ph-icon { font-size: 40px; opacity: .6; }
	.help-img-ph-path { font-size: 12px; font-family: var(--font-body); opacity: .7; }

	.help-step-title { margin: 0 0 var(--s2); font-size: 18px; color: var(--text); flex-shrink: 0; }
	.help-step-body { margin: 0 0 var(--s4); color: var(--text-2); line-height: 1.5; flex-shrink: 0; }

	.help-nav {
		display: flex; align-items: center; justify-content: space-between; gap: var(--s3);
		flex-shrink: 0;
	}
	.help-dots { display: flex; gap: 6px; }
	.help-dot {
		width: 8px; height: 8px; border-radius: var(--r-full);
		background: var(--sep); transition: background .15s, transform .15s;
	}
	.help-dot.active { background: var(--accent); transform: scale(1.25); }

	@media (max-width: 540px) {
		.help-card { padding: var(--s5) var(--s4) var(--s4); }
		.help-choices { grid-template-columns: 1fr; }
	}
</style>
