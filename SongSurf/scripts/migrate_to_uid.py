#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration SSF-03 : dossiers et cookies nommés par pseudo → nommés par UUID du portail.

À lancer UNE fois, dans le conteneur SongSurf déjà déployé avec SSF-03 :

    sudo docker exec songsurf python3 tools/migrate_to_uid.py --map /data/state/uid-map.txt
    sudo docker exec songsurf python3 tools/migrate_to_uid.py --map /data/state/uid-map.txt --apply

Sans --apply : simulation, rien n'est modifié. Correspondance validée par l'admin,
une ligne par compte (lignes vides et # ignorées) :

    <dossier actuel>  <uuid du portail>  [pseudo exact]

Pour chaque ligne :
  /data/music/<dossier>      → /data/music/<uuid>   (+ fichier .owner = pseudo)
  /data/cookies/<dossier>.txt → /data/cookies/<uuid>.txt

La bibliothèque admin est un point de montage (docker-compose.nas.yml, ADMIN_UID) :
elle ne se renomme pas, l'ancien dossier vide est simplement retiré.
Stdlib uniquement.
"""

import argparse
import re
import sys
from pathlib import Path

UID_RE = re.compile(r'^[A-Za-z0-9-]{8,64}$')       # même règle que server/app.py
OWNER_FILE = '.owner'


def parse_map(path: Path) -> list:
    entries = []
    for n, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) not in (2, 3):
            raise SystemExit(f"ligne {n} : attendu « <dossier> <uuid> [pseudo] », reçu {raw!r}")
        folder, uid = parts[0], parts[1]
        pseudo = parts[2] if len(parts) == 3 else folder
        if not UID_RE.match(uid):
            raise SystemExit(f"ligne {n} : UUID invalide {uid!r}")
        if '/' in folder or folder in ('.', '..'):
            raise SystemExit(f"ligne {n} : nom de dossier invalide {folder!r}")
        entries.append((folder, uid, pseudo))
    uids = [e[1] for e in entries]
    if len(set(uids)) != len(uids):
        raise SystemExit("le même UUID apparaît sur plusieurs lignes")
    folders = [e[0] for e in entries]
    if len(set(folders)) != len(folders):
        raise SystemExit("le même dossier apparaît sur plusieurs lignes")
    return entries


def is_mount_point(path: Path) -> bool:
    if path.is_mount():
        return True
    try:
        with open('/proc/self/mountinfo', encoding='utf-8') as f:
            points = {line.split()[4].encode().decode('unicode_escape') for line in f}
    except OSError:
        return False
    return str(path.resolve()) in points


def only_owner_file(d: Path) -> bool:
    """Dossier créé par une requête depuis le déploiement : vide hormis .owner."""
    return d.is_dir() and all(p.name == OWNER_FILE for p in d.iterdir())


def migrate_library(music: Path, folder: str, uid: str, pseudo: str, apply: bool) -> str:
    src, dst = music / folder, music / uid
    if not src.exists():
        return 'absent'
    if is_mount_point(dst):
        # Bibliothèque admin : déjà montée sur l'UUID, l'ancien dossier est le point
        # de montage abandonné (vide).
        if src.is_dir() and not any(src.iterdir()):
            if apply:
                src.rmdir()
            return 'montage UUID en place, ancien dossier vide retiré'
        return 'CONFLIT : montage UUID en place mais ancien dossier non vide — à vérifier'
    if is_mount_point(src):
        return 'CONFLIT : ancien dossier encore monté — renseigner ADMIN_UID et redéployer'
    if dst.exists():
        if not only_owner_file(dst):
            return 'CONFLIT : dossier UUID déjà rempli — rien déplacé'
        if apply:
            for p in dst.iterdir():
                p.unlink()
            dst.rmdir()
    if apply:
        src.rename(dst)
        (dst / OWNER_FILE).write_text(pseudo + '\n', encoding='utf-8')
    return 'renommé'


def migrate_cookies(cookies: Path, folder: str, uid: str, apply: bool) -> str:
    src, dst = cookies / f'{folder}.txt', cookies / f'{uid}.txt'
    if not src.exists():
        return 'absents'
    if dst.exists():
        return 'CONFLIT : cookies UUID déjà présents — rien déplacé'
    if apply:
        src.rename(dst)
    return 'renommés'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--map', required=True, type=Path, help='fichier de correspondance dossier → uuid')
    ap.add_argument('--music', default=Path('/data/music'), type=Path)
    ap.add_argument('--cookies', default=Path('/data/cookies'), type=Path)
    ap.add_argument('--apply', action='store_true', help='effectuer les changements (sinon simulation)')
    args = ap.parse_args(argv)

    entries = parse_map(args.map)
    print(('APPLICATION' if args.apply else 'SIMULATION (ajouter --apply pour effectuer)') + '\n')
    conflicts = 0
    for folder, uid, pseudo in entries:
        lib = migrate_library(args.music, folder, uid, pseudo, args.apply)
        ck = migrate_cookies(args.cookies, folder, uid, args.apply)
        conflicts += lib.startswith('CONFLIT') + ck.startswith('CONFLIT')
        print(f"  {folder} → {uid} ({pseudo})\n      bibliothèque : {lib}\n      cookies      : {ck}")

    mapped = {f for f, _, _ in entries} | {u for _, u, _ in entries}
    # Les dossiers déjà nommés par identifiant portent un .owner (écrit par SongSurf).
    leftovers = sorted(p.name for p in args.music.iterdir()
                       if p.is_dir() and p.name not in mapped and not (p / OWNER_FILE).exists())
    if leftovers:
        print("\nDossiers sans correspondance (laissés tels quels) : " + ', '.join(leftovers))
    print(f"\n{len(entries)} compte(s), {conflicts} conflit(s).")
    return 1 if conflicts else 0


if __name__ == '__main__':
    sys.exit(main())
