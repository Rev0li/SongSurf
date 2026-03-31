# 05 - Plan Etape 2: Migration Progressive vers Rust

## Strategie

Migration en strangler pattern:

- On garde Python en place.
- On introduit un service Rust devant certaines routes.
- On migre route par route.

## Phase A - Service Rust Auth (Semaine 1-2)

Stack conseillee:

- Framework: Axum
- DB: SQLx + SQLite (puis Postgres possible)
- Crypto: argon2 + jsonwebtoken (ou paseto)
- Config: dotenvy + envy

Routes Rust initiales:

- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/me`

Python devient client interne de verification token (ou trust via reverse proxy).

## Phase B - Accounts & RBAC (Semaine 3)

Nouvelles routes Rust:

- `GET /api/accounts`
- `POST /api/accounts`
- `PATCH /api/accounts/:id`
- `POST /api/accounts/:id/reset-password`

Le dashboard admin continue d'utiliser les memes chemins API.

## Phase C - Session Guest/Queue metadata (Semaine 4)

- Basculer la gestion session guest en base
- Exposer endpoint `GET /api/guest/session`
- Garder le telechargement media sur Python

## Phase D - Media endpoints (Semaine 5+)

Deux options:

1. Rust orchestre, Python worker media conserve
2. Rust remplace aussi workers media (plus complexe)

Recommandation: option 1 d'abord.

## Critere de rollback

Toujours pouvoir rerouter vers Python si:

- taux erreur auth > 2%
- erreurs refresh token anormales
- probleme compat frontend

Rollback doit etre un switch de routing, pas un revert code urgent.
