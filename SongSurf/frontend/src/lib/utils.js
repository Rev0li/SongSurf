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

export function extractYouTubeVideoId(url) {
	const raw = asText(url);
	const vMatch = raw.match(/[?&]v=([^&]+)/i);
	if (vMatch?.[1]) return vMatch[1];
	const shortMatch = raw.match(/youtu\.be\/([^?&/]+)/i);
	return shortMatch?.[1] ?? '';
}

function normalizeThumbUrl(url) {
	return asText(url).replace(/^https?:\/\/i\d+\.ytimg\.com\//i, 'https://i.ytimg.com/');
}

function shouldCacheBust(url) {
	if (!url) return false;
	if (/\/s_p\//i.test(url)) return false;
	if (/[?&](?:rs|sqp)=/i.test(url)) return false;
	return true;
}

function pushUnique(arr, value) {
	const v = asText(value);
	if (v && !arr.includes(v)) arr.push(v);
}

function candidatesFromVideoId(videoId) {
	if (!videoId) return [];
	return [
		`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`,
		`https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`,
		`https://i.ytimg.com/vi/${videoId}/default.jpg`,
	];
}

export function resolveCoverCandidates(data, currentUrl = '') {
	const out = [];
	for (const u of (data?.thumbnail_candidates ?? [])) {
		pushUnique(out, normalizeThumbUrl(u));
	}
	pushUnique(out, normalizeThumbUrl(data?.thumbnail_url));

	const songs = data?.songs ?? [];
	if (songs.length > 0) {
		const first = songs[0] ?? {};
		const id = asText(first.id) || extractYouTubeVideoId(first.url ?? '');
		for (const u of candidatesFromVideoId(id)) pushUnique(out, u);
	}

	const fallbackId = extractYouTubeVideoId(currentUrl);
	for (const u of candidatesFromVideoId(fallbackId)) pushUnique(out, u);

	return out;
}

export function bustUrl(url) {
	if (!url) return url;
	const sep = url.includes('?') ? '&' : '?';
	return shouldCacheBust(url) ? `${url}${sep}t=${Date.now()}` : url;
}

export function nrm(text) {
	return (text ?? '').toString().toLowerCase().trim();
}

export function matchesFilter(text, query) {
	if (!query) return true;
	return nrm(text).includes(query);
}
