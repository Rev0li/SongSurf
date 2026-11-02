// Constantes et petits formateurs de la page /metadata.

export const EDITABLE_KEYS = [
	'title', 'artist', 'album_artist', 'album', 'year',
	'track_number', 'disc_number', 'genre', 'composer', 'conductor',
	'bpm', 'key', 'language', 'isrc', 'publisher', 'copyright',
	'encoded_by', 'comment',
];

// Disposition des champs : principaux (Jellyfin) / secondaires (repliés)
export const ID3_PRIMARY   = ['title', 'artist', 'album_artist', 'album', 'year', 'track_number', 'disc_number', 'genre'];
export const ID3_SECONDARY = ['composer', 'conductor', 'bpm', 'key', 'language', 'isrc', 'publisher', 'copyright', 'encoded_by', 'comment'];

// Champs multi-valeurs : « A; B » écrit deux valeurs ID3 distinctes (TPE1 null-séparé)
export const MULTI_FIELDS = new Set(['artist', 'genre', 'composer']);
export const MULTI_HINT   = 'Plusieurs valeurs possibles — sépare par « ; »';

// Champs dont l'absence gêne Jellyfin
export const JELLYFIN_KEYS = ['album_artist', 'track_number', 'genre', 'year'];

export const ID3_LABELS = {
	title: 'Titre', artist: 'Artiste(s) (TPE1)', album_artist: 'Artiste album (TPE2)',
	conductor: 'Chef d\'orchestre', album: 'Album', year: 'Année / Date',
	track_number: 'N° piste (TRCK)', disc_number: 'N° disque (TPOS)',
	genre: 'Genre (TCON)', composer: 'Compositeur (TCOM)',
	copyright: 'Copyright', publisher: 'Éditeur (TPUB)',
	bpm: 'BPM', key: 'Tonalité', language: 'Langue',
	encoded_by: 'Encodé par', isrc: 'ISRC', comment: 'Commentaire',
};

export function songDisplayName(name) {
	return name.replace(/\.mp3$/i, '');
}

export function fmtBytes(n) {
	if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
	return `${(n / 1048576).toFixed(2)} MB`;
}

export function plural(n, word) {
	return `${n} ${word}${n > 1 ? 's' : ''}`;
}

export function countSongs(albums) {
	return (albums ?? []).reduce((n, al) => n + (al.songs?.length ?? 0), 0);
}
