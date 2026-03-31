# 03 - Modele de Donnees (Comptes + Tokens)

## Tables minimales (SQLite)

## `users`

- `id` (uuid)
- `username` (unique)
- `display_name`
- `password_hash`
- `role` (`owner|friend|guest-temp`)
- `is_active` (bool)
- `created_at`
- `updated_at`
- `last_login_at` (nullable)

## `permissions`

- `id`
- `user_id`
- `can_download_mp3` (bool)
- `can_download_mp4` (bool)
- `can_playlist_mode` (bool)
- `max_songs_per_day` (int, nullable)
- `max_queue_size` (int, nullable)

## `refresh_tokens`

- `id` (uuid)
- `user_id`
- `token_hash` (jamais token brut)
- `expires_at`
- `revoked_at` (nullable)
- `created_at`
- `rotated_from` (nullable)
- `ip`
- `user_agent`

## `sessions`

- `id` (uuid)
- `user_id`
- `status` (`active|expired|revoked`)
- `created_at`
- `expires_at`
- `last_seen_at`

## `audit_logs`

- `id`
- `user_id` (nullable)
- `action` (login_success, login_failed, token_refresh, account_created...)
- `meta_json`
- `created_at`

## Regles de securite

1. Mot de passe
- Hash Argon2id
- Jamais de mot de passe en clair en base/log

2. Refresh token
- Stocker uniquement le hash
- Rotation a chaque refresh
- Revocation a logout

3. Access token
- Duree courte (15 min)
- Claims minimales: `sub`, `role`, `exp`, `session_id`

## Mapping avec ton besoin metier

- Eviter "session NULL": session basee sur token + restauration DB.
- Comptes amis custom: table `users` + `permissions`.
- Controle entourage: desactiver/revoquer un compte individuellement.
