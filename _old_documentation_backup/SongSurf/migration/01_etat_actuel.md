# 01 - Etat Actuel (Python)

## Ce que fait le backend aujourd'hui

Fichiers centraux:

- `server/app.py`: routes, auth, sessions, workers
- `server/downloader.py`: extraction metadata et telechargement media
- `server/organizer.py`: organisation fichiers et tags

Observations importantes:

1. Secret Flask
- `app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))`
- Risque: fallback aleatoire au redemarrage si variable absente.

2. Sessions guest
- Stockees en memoire: `guest_sessions = {}`
- Risque: perte apres restart du process.

3. Auth actuelle
- Admin: mot de passe unique env
- Guest: mot de passe unique env + session en memoire
- Pas de comptes individuels amis

4. Workers
- Queue admin globale + worker thread
- Queue guest par session + worker thread

## Probleme metier actuel

- Au refresh/restart, certains guests tombent sur session invalide/null.
- Difficile de donner des acces personnalises a tes potes.
- Architecture monolithique complique la migration Rust.

## Priorites avant migration Rust

1. Stabiliser auth/session/token en Python.
2. Introduire base de donnees (SQLite au debut).
3. Creer comptes et permissions (RBAC simple).
4. Garder le frontend compatible API actuelle.
