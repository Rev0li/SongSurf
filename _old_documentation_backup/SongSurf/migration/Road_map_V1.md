# Road Map V1 - SongSurf

Objectif: sortir une version stable, lisible et maintenable sans changer l'architecture globale.

## Phase 1 - Stabilisation critique

Priorite: corriger ce qui peut casser le comportement utilisateur ou la logique de traitement.

1. Fiabiliser la detection song vs playlist
- Remplacer la heuristique fragile par une detection centralisee dans `downloader.py`.
- Appliquer la meme regle sur les routes admin et guest.

2. Nettoyer le dashboard
- Retirer la reference a la bibliotheque / metadata.
- Supprimer le code mort du frontend.
- Garder la section "Telechargements recents".

3. Supprimer `get_stats()`
- Enlever la fonction du backend.
- Retirer toute dependance UI associee.

4. Fixer le warning auth
- Corriger le message `SONGSURF_PASSWORD` pour ne pas polluer les logs en mode Watcher.

5. Limiter les durees de download
- Ajouter `MAX_DURATION_SECONDS`.
- Bloquer les fichiers trop longs avant le download.

Definition of done:
- Plus de confusion song/playlist.
- Plus de reference a une bibliotheque non livree.
- Les logs Watcher restent propres.

## Phase 2 - Finition produit

Priorite: rendre l'interface plus claire et coherente pour les usages reellement livrables.

1. Bouton ZIP admin
- Ajouter le bouton ZIP sur le dashboard admin.
- Garder la logique Guest existante.

2. Telechargements recents
- Afficher les items recents dans les deux dashboards.
- Garder le format simple et lisible.

3. Nettoyage Guest en fin de session
- Conserver les fichiers jusqu'a la fin de session.
- Ne pas supprimer immediatement apres un ZIP.

4. Message d'inactivite Watcher
- Afficher un avertissement apres 1 heure d'inactivite.
- Prevoir un arret force apres 15 minutes sans reponse.

Definition of done:
- L'UX annonce clairement l'etat de la session.
- Le ZIP est disponible au bon endroit.
- Le nettoyage Guest ne surprend pas l'utilisateur.

## Phase 3 - Evolution future

Priorite: garder les evolutions lourdes hors du chemin critique.

1. Auth externe
- Garder l'auth interne pour maintenant.
- Migrer plus tard vers une auth externe unifiee.

2. Session Guest sans limite
- Lever la limite de duree de session plus tard.
- Conserver le suivi d'inactivite et le stop Docker.

3. Bibliotheque comme module separe
- Reprendre la bibliotheque seulement si le besoin produit est valide.

4. Protection API
- Ajouter le rate limiting sur `/api/extract`.

Definition of done:
- Les fonctions lourdes restent decouplees.
- Les evolutions ne cassent pas la V1.
