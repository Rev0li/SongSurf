<script>
	// Icônes au trait (24×24, couleur du texte). Décoratives : aria-hidden.
	let { name, size = 20 } = $props();

	const PATHS = {
		plus: '<path d="M12 5v14M5 12h14"/>',
		music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
		search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
		more: '<circle cx="5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/>',
		back: '<path d="M15 18l-6-6 6-6"/>',
		next: '<path d="M9 18l6-6-6-6"/>',
		chev: '<path d="M6 9l6 6 6-6"/>',
		check: '<path d="M5 13l4 4L19 7"/>',
		warn: '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4M12 17v.5"/>',
		down: '<path d="M12 4v12M6 10l6 6 6-6M5 20h14"/>',
		clip: '<rect x="8" y="3" width="8" height="4" rx="1"/><path d="M16 5h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2"/>',
		close: '<path d="M6 6l12 12M18 6L6 18"/>',
		edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
		move: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M10 13h6M14 11l2 2-2 2"/>',
		trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
		image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 8"/>',
		retry: '<path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 4v4h4"/>',
		link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
		spark: '<path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/>',
		hash: '<path d="M5 9h14M5 15h14M10 4L8 20M16 4l-2 16"/>',
		tag: '<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
		sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4"/>',
		moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
		power: '<path d="M12 3v9"/><path d="M6.3 7.3a8 8 0 1 0 11.4 0"/>',
	};
</script>

<svg class="ico" width={size} height={size} style="width:{size}px;height:{size}px" viewBox="0 0 24 24" fill="none"
	stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
	{@html PATHS[name] ?? ''}
</svg>
