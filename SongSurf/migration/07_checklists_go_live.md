# 07 - Checklists Go-Live

## Checklist securite

- Secret de signature stable en prod
- Cookies `HttpOnly` actifs
- HTTPS force en prod
- Hash mot de passe Argon2id
- Refresh tokens revocables
- Logout invalide refresh token

## Checklist fonctionnalite

- Login owner OK
- Login friend OK
- Refresh navigateur: session conservee
- Redemarrage backend: session restauree (si refresh valide)
- Disable account: acces bloque immediat

## Checklist observabilite

- Logs login success/fail
- Logs refresh success/fail
- Correlation ID par requete (ideal)
- Dashboard erreurs 401/403/500

## Checklist migration Rust

- Endpoints auth Rust en production progressive
- Latence stable
- Taux erreur stable
- Rollback routing documente et teste

## Tests minimaux obligatoires

- Unit tests service auth
- Integration tests login/refresh/logout
- Test revocation refresh token
- Test role owner vs friend
