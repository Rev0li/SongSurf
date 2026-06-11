"""
Tests for library_audit — audit métadonnées par artiste + backfill genre.

Fichiers MP3 factices (octets + tag ID3 mutagen, pas de frames MPEG) et
lookups iTunes injectés : zéro réseau.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server'))

import threading
import pytest
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TDRC, TRCK, TCON

import library_audit
from library_audit import audit_artist, backfill_genres, _read_tags


def _make_mp3(path, title=None, artists=None, album_artist=None, album=None,
              year=None, track=None, genres=None):
    """Fichier factice avec un vrai tag ID3 (lisible par mutagen.id3.ID3)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x00' * 128)
    id3 = ID3()
    if title:        id3['TIT2'] = TIT2(encoding=3, text=title)
    if artists:      id3['TPE1'] = TPE1(encoding=3, text=artists)
    if album_artist: id3['TPE2'] = TPE2(encoding=3, text=album_artist)
    if album:        id3['TALB'] = TALB(encoding=3, text=album)
    if year:         id3['TDRC'] = TDRC(encoding=3, text=year)
    if track:        id3['TRCK'] = TRCK(encoding=3, text=track)
    if genres:       id3['TCON'] = TCON(encoding=3, text=genres)
    id3.save(path)
    return path


ITUNES_OK = {'found': True, 'genres': ['Rap français', 'Hip-Hop/Rap'],
             'year': '2016', 'album_artist': 'Nekfeu', 'track_count': 2}
ITUNES_MISS = {'found': False, 'genres': [], 'year': '', 'album_artist': '', 'track_count': 0}


def _recs_by_field(report, field):
    return [r for album in report['albums'] for r in album['recommendations']
            if r['field'] == field]


def _all_warnings(report):
    return [w for album in report['albums'] for w in album['warnings']]


# ── _read_tags ────────────────────────────────────────────────────────────────

class TestReadTags:
    def test_full_tags(self, tmp_music_dir):
        f = _make_mp3(tmp_music_dir / 'A' / 'B' / 's.mp3',
                      title='Song', artists=['A', 'Feat'], album_artist='A',
                      album='B', year='2020', track='1/10', genres=['Rock'])
        tags = _read_tags(f)
        assert tags['title'] == 'Song'
        assert tags['artists'] == ['A', 'Feat']
        assert tags['album_artist'] == 'A'
        assert tags['year'] == '2020'
        assert tags['track_number'] == '1/10'
        assert tags['genres'] == ['Rock']

    def test_no_id3_header(self, tmp_music_dir):
        f = tmp_music_dir / 'raw.mp3'
        f.write_bytes(b'\x00' * 64)
        tags = _read_tags(f)
        assert tags['artists'] == [] and tags['genres'] == []


# ── audit_artist ──────────────────────────────────────────────────────────────

class TestAuditArtist:
    def test_clean_album_no_recommendations(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        for i, t in enumerate(('One', 'Two'), start=1):
            _make_mp3(d / f'{t}.mp3', title=t, artists=['Nekfeu'], album_artist='Nekfeu',
                      album='Cyborg', year='2016', track=f'{i}/2',
                      genres=['Rap français', 'Hip-Hop/Rap'])
        (d / 'cover.jpg').write_bytes(b'x')
        (tmp_music_dir / 'Nekfeu' / 'folder.jpg').write_bytes(b'x')

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        assert report['total_recommendations'] == 0
        assert _all_warnings(report) == []
        assert report['artist_warnings'] == []

    def test_missing_genre_proposes_itunes(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', track='1/2')
        _make_mp3(d / 'Two.mp3', title='Two', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', track='2/2', genres=['Rap français'])

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        recs = _recs_by_field(report, 'genre')
        assert len(recs) == 1
        assert recs[0]['proposed'] == 'Rap français; Hip-Hop/Rap'
        assert recs[0]['changes'] == [{'path': 'Nekfeu/Cyborg/One.mp3',
                                       'value': 'Rap français; Hip-Hop/Rap'}]

    def test_missing_genre_itunes_not_found_warns(self, tmp_music_dir):
        d = tmp_music_dir / 'X' / 'Obscur'
        _make_mp3(d / 'One.mp3', title='One', artists=['X'], album_artist='X')

        report = audit_artist(tmp_music_dir / 'X', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_MISS))
        assert _recs_by_field(report, 'genre') == []
        assert any('introuvable sur iTunes' in w for w in _all_warnings(report))

    def test_missing_year_proposes_itunes_year(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'], album_artist='Nekfeu',
                  genres=['Rap'], track='1/2')

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        recs = _recs_by_field(report, 'year')
        assert len(recs) == 1
        assert recs[0]['proposed'] == '2016'

    def test_inconsistent_years_aligned_on_itunes(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'], track='1/2')
        _make_mp3(d / 'Two.mp3', title='Two', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2021', genres=['Rap'], track='2/2')

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        recs = _recs_by_field(report, 'year')
        assert len(recs) == 1
        assert recs[0]['proposed'] == '2016'
        # Seul le titre divergent est corrigé
        assert recs[0]['changes'] == [{'path': 'Nekfeu/Cyborg/Two.mp3', 'value': '2016'}]

    def test_album_artist_aligned_on_folder(self, tmp_music_dir):
        # TPE2 = dossier artiste (groupement Jellyfin), même si iTunes dit autre chose
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'],
                  album_artist='Nekfeu & S-Crew', year='2016', genres=['Rap'], track='1/2')

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        recs = _recs_by_field(report, 'album_artist')
        assert len(recs) == 1
        assert recs[0]['proposed'] == 'Nekfeu'

    def test_missing_tpe1_proposes_folder_artist(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', album_artist='Nekfeu',
                  year='2016', genres=['Rap'], track='1/2')

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        recs = _recs_by_field(report, 'artist')
        assert len(recs) == 1
        assert recs[0]['proposed'] == 'Nekfeu'

    def test_tpe2_not_in_tpe1_warns(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['S-Crew'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'], track='1/2')

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        assert any("n'apparaît pas dans TPE1" in w for w in _all_warnings(report))

    def test_bare_track_number_normalized(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'], track='1')
        _make_mp3(d / 'Two.mp3', title='Two', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'], track='2/2')

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        recs = _recs_by_field(report, 'track_number')
        assert len(recs) == 1
        # total = track_count iTunes (2)
        assert recs[0]['changes'] == [{'path': 'Nekfeu/Cyborg/One.mp3', 'value': '1/2'}]

    def test_missing_track_number_warns_only(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'])

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        assert _recs_by_field(report, 'track_number') == []
        assert any('Numéro de piste manquant' in w for w in _all_warnings(report))

    def test_incomplete_album_vs_itunes_warns(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'], track='1/2')
        itunes = {**ITUNES_OK, 'track_count': 14}

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(itunes))
        assert any('14 titres' in w for w in _all_warnings(report))

    def test_missing_covers_warn(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'], track='1/2')

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        assert any('Pochette album manquante' in w for w in _all_warnings(report))
        assert any('Photo artiste manquante' in w for w in report['artist_warnings'])

    def test_empty_album_dir_skipped(self, tmp_music_dir):
        (tmp_music_dir / 'Nekfeu' / 'Vide').mkdir(parents=True)

        report = audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                              album_lookup=lambda a, b: dict(ITUNES_OK))
        assert report['albums'] == []

    def test_one_lookup_per_album(self, tmp_music_dir):
        for album in ('A1', 'A2'):
            _make_mp3(tmp_music_dir / 'Art' / album / 'One.mp3', title='One',
                      artists=['Art'], album_artist='Art', year='2016',
                      genres=['Rap'], track='1/1')
        calls = []

        def fake_lookup(artist, album):
            calls.append((artist, album))
            return dict(ITUNES_MISS)

        audit_artist(tmp_music_dir / 'Art', tmp_music_dir, album_lookup=fake_lookup)
        assert calls == [('Art', 'A1'), ('Art', 'A2')]


# ── Numéros de piste via tracklist iTunes ─────────────────────────────────────

ITUNES_WITH_ID = {**ITUNES_OK, 'collection_id': 987654}


def _it_track(title, number, count=2):
    return {'title': title, 'track_number': number, 'track_count': count}


class TestTrackNumberFromItunes:
    def _audit(self, music_dir, tracklist):
        return audit_artist(music_dir / 'Nekfeu', music_dir,
                            album_lookup=lambda a, b: dict(ITUNES_WITH_ID),
                            track_lookup=lambda cid: list(tracklist))

    def test_missing_trck_matched_by_title(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'Squa.mp3', title='Squa', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'])
        _make_mp3(d / 'Humanoide.mp3', title='Humanoïde', artists=['Nekfeu'],
                  album_artist='Nekfeu', year='2016', genres=['Rap'])

        report = self._audit(tmp_music_dir,
                             [_it_track('Humanoïde', 1), _it_track('Squa', 2)])
        recs = _recs_by_field(report, 'track_number')
        assert len(recs) == 1
        assert recs[0]['changes'] == [
            {'path': 'Nekfeu/Cyborg/Humanoide.mp3', 'value': '1/2'},
            {'path': 'Nekfeu/Cyborg/Squa.mp3',      'value': '2/2'},
        ]
        # Tout est matché → plus de warning TRCK
        assert not any('Numéro de piste manquant' in w for w in _all_warnings(report))

    def test_match_via_filename_when_no_tit2(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'Squa.mp3', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'])

        report = self._audit(tmp_music_dir, [_it_track('Squa', 2)])
        recs = _recs_by_field(report, 'track_number')
        assert recs and recs[0]['changes'][0]['value'] == '2/2'

    def test_feat_suffix_stripped_for_match(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'S.mp3', title='Sans titre (feat. Doums)', artists=['Nekfeu'],
                  album_artist='Nekfeu', year='2016', genres=['Rap'])

        report = self._audit(tmp_music_dir, [_it_track('Sans titre', 1)])
        recs = _recs_by_field(report, 'track_number')
        assert recs and recs[0]['changes'][0]['value'] == '1/2'

    def test_ambiguous_duplicate_titles_not_proposed(self, tmp_music_dir):
        # Deux pistes iTunes au même nom → match ambigu → warning seulement
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'Intro.mp3', title='Intro', artists=['Nekfeu'],
                  album_artist='Nekfeu', year='2016', genres=['Rap'])

        report = self._audit(tmp_music_dir,
                             [_it_track('Intro', 1), _it_track('Intro', 9)])
        assert _recs_by_field(report, 'track_number') == []
        assert any('Numéro de piste manquant' in w for w in _all_warnings(report))

    def test_no_match_keeps_warning(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'Inedit.mp3', title='Inédit bonus', artists=['Nekfeu'],
                  album_artist='Nekfeu', year='2016', genres=['Rap'])

        report = self._audit(tmp_music_dir, [_it_track('Autre chose', 1)])
        assert _recs_by_field(report, 'track_number') == []
        assert any('Numéro de piste manquant' in w for w in _all_warnings(report))

    def test_no_collection_id_no_tracklist_call(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'One.mp3', title='One', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'])
        calls = []

        def track_lookup(cid):
            calls.append(cid)
            return []

        audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                     album_lookup=lambda a, b: dict(ITUNES_OK),  # pas de collection_id
                     track_lookup=track_lookup)
        assert calls == []

    def test_tracklist_fetched_once_per_album(self, tmp_music_dir):
        d = tmp_music_dir / 'Nekfeu' / 'Cyborg'
        _make_mp3(d / 'A.mp3', title='A', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'])
        _make_mp3(d / 'B.mp3', title='B', artists=['Nekfeu'], album_artist='Nekfeu',
                  year='2016', genres=['Rap'])
        calls = []

        def track_lookup(cid):
            calls.append(cid)
            return [_it_track('A', 1), _it_track('B', 2)]

        audit_artist(tmp_music_dir / 'Nekfeu', tmp_music_dir,
                     album_lookup=lambda a, b: dict(ITUNES_WITH_ID),
                     track_lookup=track_lookup)
        assert calls == [987654]


# ── backfill_genres ───────────────────────────────────────────────────────────

class TestBackfillGenres:
    def _run(self, music_dir, lookup):
        state = {'status': 'running'}
        backfill_genres(music_dir, state, threading.Lock(), genre_lookup_fn=lookup)
        return state

    def test_writes_missing_tcon(self, tmp_music_dir):
        f = _make_mp3(tmp_music_dir / 'Art' / 'Alb' / 'One.mp3',
                      title='One', artists=['Art'], album='Alb')
        state = self._run(tmp_music_dir, lambda a, t, al: ['Rap français', 'Hip-Hop/Rap'])
        assert state == {'status': 'done', 'total': 1, 'done': 1, 'updated': 1,
                         'failed': 0, 'last_file': 'Art/Alb/One.mp3'}
        assert _read_tags(f)['genres'] == ['Rap français', 'Hip-Hop/Rap']

    def test_existing_tcon_untouched(self, tmp_music_dir):
        f = _make_mp3(tmp_music_dir / 'Art' / 'Alb' / 'One.mp3',
                      title='One', artists=['Art'], album='Alb', genres=['Jazz'])
        state = self._run(tmp_music_dir, lambda a, t, al: ['Rock'])
        assert state['total'] == 0
        assert _read_tags(f)['genres'] == ['Jazz']

    def test_lookup_empty_counts_as_done_not_updated(self, tmp_music_dir):
        _make_mp3(tmp_music_dir / 'Art' / 'Alb' / 'One.mp3',
                  title='One', artists=['Art'], album='Alb')
        state = self._run(tmp_music_dir, lambda a, t, al: [])
        assert state['done'] == 1 and state['updated'] == 0 and state['failed'] == 0

    def test_lookup_error_counted_failed(self, tmp_music_dir):
        def boom(a, t, al):
            raise RuntimeError('réseau')
        _make_mp3(tmp_music_dir / 'Art' / 'Alb' / 'One.mp3',
                  title='One', artists=['Art'], album='Alb')
        state = self._run(tmp_music_dir, boom)
        assert state['failed'] == 1 and state['done'] == 1
        assert state['status'] == 'done'

    def test_fallback_folder_names_when_no_tags(self, tmp_music_dir):
        # Aucun tag → artiste/album déduits des dossiers, titre du nom de fichier
        f = tmp_music_dir / 'FolderArt' / 'FolderAlb' / 'My Song.mp3'
        f.parent.mkdir(parents=True)
        f.write_bytes(b'\x00' * 64)
        seen = []

        def lookup(artist, title, album):
            seen.append((artist, title, album))
            return ['Pop']

        state = self._run(tmp_music_dir, lookup)
        assert seen == [('FolderArt', 'My Song', 'FolderAlb')]
        assert state['updated'] == 1
        assert _read_tags(f)['genres'] == ['Pop']

    def test_file_without_artist_skipped(self, tmp_music_dir):
        # MP3 à la racine, sans tag → ni artiste tag ni dossier artiste → ignoré
        f = tmp_music_dir / 'orphan.mp3'
        f.write_bytes(b'\x00' * 64)
        state = self._run(tmp_music_dir, lambda a, t, al: ['Pop'])
        assert state['total'] == 0
