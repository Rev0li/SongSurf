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
