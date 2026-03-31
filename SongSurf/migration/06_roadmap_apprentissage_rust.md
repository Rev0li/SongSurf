# 06 - Roadmap Apprentissage Rust (Mode Senior Prof)

Objectif: apprendre Rust en construisant des briques utiles a SongSurf.

## Semaine 1 - Fondamentaux utiles

- Ownership/borrowing
- Result/Option
- Struct/Enum/Traits
- Modules et crates

Exercices:

1. Ecrire un parseur de config env -> struct
2. Ecrire un validateur de mot de passe (Result detaille)
3. Ecrire un mini service CLI de hash Argon2

## Semaine 2 - API Web Axum

- Router, extractors, middleware
- Gestion erreurs propre (`thiserror`, `anyhow`)
- Serialization (`serde`)

Exercices:

1. `POST /health/auth` mock
2. `POST /api/auth/login` avec user hardcode
3. tests integration avec `reqwest`

## Semaine 3 - SQLx + Auth reelle

- Migrations SQLx
- Repositories
- Transactions
- Refresh token rotation

Exercices:

1. table `users`
2. login reel + access token
3. refresh rotation + revoke

## Semaine 4 - RBAC + dashboard accounts

- Autorisation par role/permissions
- Endpoints comptes
- Audit logs

Exercices:

1. middleware RBAC
2. endpoint create account
3. endpoint disable account

## Regles de progression

- Toujours ecrire un test avant chaque endpoint critique.
- 1 PR = 1 brique metier.
- Si une brique n'est pas testee, elle n'est pas "apprise".

## Livrables d'apprentissage

A la fin, tu dois etre capable de:

1. Expliquer ownership sur ton code auth.
2. Implementer un endpoint Axum + SQLx sans copier-coller.
3. Diagnostiquer un bug token/session avec logs + tests.
