# 04 - Plan Etape 1: Stabiliser Python Avant Rust

Objectif: fiabiliser l'auth des maintenant, sans attendre Rust.

## Sprint 1 - Fiabilite session/token (2-3 jours)

1. Secret stable
- Rendre `FLASK_SECRET_KEY` obligatoire en prod.
- Bloquer le demarrage si absent.

2. Cookies securises
- `SESSION_COOKIE_HTTPONLY = True`
- `SESSION_COOKIE_SAMESITE = Lax`
- `SESSION_COOKIE_SECURE = True` (en HTTPS)

3. Token guest signe
- Generer token (itsdangerous ou JWT)
- Stockage en cookie HttpOnly
- Fallback dans `guest_required` si session Flask vide

4. Persistance minimale
- Sauvegarder etat session guest en SQLite/JSON
- Restaurer session au refresh/restart

## Sprint 2 - Comptes et permissions (3-5 jours)

1. Ajouter modeles `users`, `permissions`, `sessions`, `refresh_tokens`
2. Ajouter login par compte (username/password)
3. Garder compat mode legacy (mot de passe guest global) temporairement
4. Ajouter endpoint `GET /api/me` pour le frontend

## Sprint 3 - Admin accounts dashboard (3-5 jours)

1. Nouvelle page `Account`
- Creer compte
- Activer/desactiver
- Reset mot de passe
- Voir derniere connexion

2. Permissions par compte
- mp3/mp4
- playlist mode
- quota journalier

3. Audit
- afficher derniers evenements de securite

## Definition of Done Etape 1

- Refresh navigateur ne casse plus la session valide.
- Restart service ne deconnecte pas tous les users si refresh token valide.
- Comptes amis utilisables individuellement.
- Revocation compte immediate effective.
