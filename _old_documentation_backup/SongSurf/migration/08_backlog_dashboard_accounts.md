# 08 - Backlog Dashboard "Accounts"

Objectif: depuis ton dashboard, gerer les acces de tes potes sans laisser ouvert a tout le monde.

## Ecran `Accounts` (nouveau)

## Liste comptes

Colonnes:

- Username
- Display name
- Role
- Etat (actif/inactif)
- Derniere connexion
- Quota
- Actions

Actions:

- Editer permissions
- Reset password
- Desactiver/activer
- Revoquer sessions

## Creation compte

Champs:

- username (unique)
- display_name
- password temporaire
- role (`friend` par defaut)
- permissions

## Permissions recommandee (preset)

Preset `Ami standard`:

- mp3: oui
- mp4: non
- playlist: oui
- quota/jour: 20

Preset `Ami avance`:

- mp3: oui
- mp4: oui
- playlist: oui
- quota/jour: 100

## API a brancher

- `GET /api/accounts`
- `POST /api/accounts`
- `PATCH /api/accounts/:id`
- `POST /api/accounts/:id/reset-password`
- `POST /api/accounts/:id/revoke-sessions`

## UX/Securite

- Confirmation obligatoire avant disable/delete
- Password temporaire visible une seule fois
- Toast succes/erreur clair
- Audit visible sur la fiche compte

## Definition of Done

- Tu peux creer un compte ami en moins de 30 secondes.
- Tu peux couper un acces immediatement.
- Tu peux limiter precisement ce que chaque pote peut faire.
