export function asText(value, fallback = '') {
	const v = (value ?? '').toString().trim();
	return v || fallback;
}

export function primaryArtist(value) {
	const str = asText(value, 'Unknown Artist');
	const parts = str.split(/\s*(?:,|;|\||&|\band\b|\bet\b|\/)\s*/i).filter(Boolean);
	return parts[0] || str;
}

function artistFromSongTitle(title) {
	const raw = asText(title);
	if (!raw.includes(' - ')) return '';
	const maybeArtist = raw.split(' - ')[0].trim();
	if (!maybeArtist || maybeArtist.toLowerCase().includes('unknown')) return '';
	return primaryArtist(maybeArtist);
}

export function inferPlaylistArtist(data) {
	const fromApi = primaryArtist(data?.artist ?? 'Unknown Artist');
	if (fromApi && fromApi.toLowerCase() !== 'unknown artist') return fromApi;
	for (const s of (data?.songs ?? [])) {
		const a = primaryArtist(s.artist ?? 'Unknown Artist');
		if (a && a.toLowerCase() !== 'unknown artist') return a;
		const parsed = artistFromSongTitle(s.title ?? '');
		if (parsed) return parsed;
	}
	return 'Unknown Artist';
}

export function nrm(text) {
	return (text ?? '').toString().toLowerCase().trim();
}

// ── Recherche permissive ─────────────────────────────────────────────────────
// « Angèle », « ANGELE » et « angele » donnent la même clé : sans accents, sans
// casse, ponctuation remplacée par des espaces (l'amour = l’amour = l amour).
export function fold(text) {
	return (text ?? '').toString().normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
		.replace(/œ/g, 'oe').replace(/æ/g, 'ae').replace(/ß/g, 'ss')
		.replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

/** Prépare une recherche : renvoie (texte) => bool. Tous les mots doivent être
 *  présents, dans n'importe quel ordre ; « acdc » trouve aussi « AC/DC ». */
export function matcher(query) {
	const words = fold(query).split(' ').filter(Boolean);
	const compact = words.join('');
	if (!words.length) return () => true;
	return (text) => {
		const hay = fold(text);
		return words.every((w) => hay.includes(w)) || hay.replaceAll(' ', '').includes(compact);
	};
}
