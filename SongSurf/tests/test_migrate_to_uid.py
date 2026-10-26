"""
Script de migration SSF-03 (scripts/migrate_to_uid.py) : dossiers et cookies
nommés par pseudo → nommés par UUID du portail.
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import migrate_to_uid as mig  # noqa: E402

UID_A = '3f2a9c1e-7b4d-4e8a-9c2f-1a2b3c4d5e6f'
UID_B = '9b1d6c2e-0f4a-4c3b-8e7d-5a6b7c8d9e0f'
UID_ADMIN = '11111111-2222-4333-8444-555555555555'


@pytest.fixture
def layout(tmp_path):
    music, cookies = tmp_path / 'music', tmp_path / 'cookies'
    (music / 'alice' / 'Art' / 'Alb').mkdir(parents=True)
    (music / 'alice' / 'Art' / 'Alb' / 'song.mp3').write_bytes(b'ID3')
    (music / 'ax').mkdir()                         # ancien dossier « Max » (collision)
    (music / 'ax' / 'x.mp3').write_bytes(b'ID3')
    (music / 'rev0admin').mkdir()                  # ancien point de montage admin, vide
    (music / UID_ADMIN).mkdir()                    # nouveau point de montage admin
    (music / 'orphan').mkdir()
    (music / 'Xk9pQ2rT7vLm4nB8cD1eF6gH3jK5sW0y').mkdir()   # id BetterAuth, déjà migré
    (music / 'Xk9pQ2rT7vLm4nB8cD1eF6gH3jK5sW0y' / '.owner').write_text('zoe\n')
    cookies.mkdir()
    (cookies / 'alice.txt').write_text('c')
    mapfile = tmp_path / 'uid-map.txt'
    mapfile.write_text(f"# dossier uuid pseudo\nalice {UID_A}\nax {UID_B} Max\n\nrev0admin {UID_ADMIN}\n")
    return music, cookies, mapfile


def _run(layout, *extra):
    music, cookies, mapfile = layout
    admin_mount = str((music / UID_ADMIN).resolve())
    with patch.object(mig, 'is_mount_point', side_effect=lambda p: str(p.resolve()) == admin_mount):
        return mig.main(['--map', str(mapfile), '--music', str(music), '--cookies', str(cookies), *extra])


def test_dry_run_changes_nothing(layout, capsys):
    music, cookies, _ = layout
    assert _run(layout) == 0
    assert (music / 'alice').is_dir() and not (music / UID_A).exists()
    assert (cookies / 'alice.txt').exists()
    assert 'SIMULATION' in capsys.readouterr().out


def test_apply_renames_libraries_and_cookies(layout, capsys):
    music, cookies, _ = layout
    assert _run(layout, '--apply') == 0
    assert (music / UID_A / 'Art' / 'Alb' / 'song.mp3').is_file()
    assert (music / UID_A / '.owner').read_text() == 'alice\n'
    assert (music / UID_B / '.owner').read_text() == 'Max\n'
    assert (cookies / f'{UID_A}.txt').read_text() == 'c'
    assert not (music / 'alice').exists() and not (cookies / 'alice.txt').exists()
    # Admin : le montage UUID est en place, l'ancien dossier vide disparaît
    assert not (music / 'rev0admin').exists() and (music / UID_ADMIN).is_dir()
    out = capsys.readouterr().out
    assert 'orphan' in out and 'Xk9pQ2rT' not in out and '0 conflit' in out


def test_apply_replaces_folder_created_since_deploy(layout):
    music, _, _ = layout
    (music / UID_A).mkdir()
    (music / UID_A / '.owner').write_text('alice\n')   # créé par une requête après le déploiement
    assert _run(layout, '--apply') == 0
    assert (music / UID_A / 'Art' / 'Alb' / 'song.mp3').is_file()


def test_conflict_when_uid_folder_has_music(layout, capsys):
    music, _, _ = layout
    (music / UID_A).mkdir()
    (music / UID_A / 'other.mp3').write_bytes(b'ID3')
    assert _run(layout, '--apply') == 1
    assert (music / 'alice').is_dir()                   # rien déplacé
    assert 'CONFLIT' in capsys.readouterr().out


@pytest.mark.parametrize('content', [
    "alice\n",                                          # pas d'uuid
    "alice ../etc\n",                                   # uuid invalide
    f"../x {UID_A}\n",                                  # dossier invalide
    f"alice {UID_A}\nbob {UID_A}\n",                    # uuid en double
])
def test_invalid_map_rejected(tmp_path, content):
    mapfile = tmp_path / 'm.txt'
    mapfile.write_text(content)
    with pytest.raises(SystemExit):
        mig.parse_map(mapfile)
