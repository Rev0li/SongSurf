# 02 - Architecture Cible

## Vision

Construire une architecture hybride temporaire:

- Python: telechargement media (yt-dlp/ffmpeg) pendant la phase transitoire
- Rust: auth, comptes, tokens, permissions, session restore

Puis migrer progressivement toutes les routes vers Rust.

## Couches cibles

1. API Layer
- HTTP handlers
- Validation input
- Mapping erreurs -> codes HTTP

2. Domain Layer
- AuthService
- AccountService
- SessionService
- PermissionService

3. Storage Layer
- Repositories (users, sessions, refresh_tokens, audit_logs)
- SQLite puis Postgres si besoin

## Contrat API stable (important)

Le frontend ne doit pas changer brutalement.
Conserver des endpoints compatibles, puis basculer l'implementation derriere.

Exemples de routes cibles:

- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/me`
- `GET /api/accounts`
- `POST /api/accounts`
- `PATCH /api/accounts/:id`
- `POST /api/accounts/:id/reset-password`

## Roles proposes

- `owner`: toi, droits complets
- `friend`: compte nominatif, droits limites
- `guest-temp`: eventuel acces temporaire

## Principes securite

- Access token court en cookie HttpOnly
- Refresh token rotatif et revocable
- Hash mot de passe (Argon2id recommande)
- Audit log minimal (login, echec, reset, revoke)
