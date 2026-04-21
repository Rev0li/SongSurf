# Technical Tickets V1 - SongSurf

Objectif: transformer la roadmap V1 en tickets techniques simples, testables et priorisables.

## Ticket V1-01 - Detection song vs playlist

Contexte:
- La logique actuelle est trop fragile sur les URLs YouTube Music.

Travail:
- Ajouter une fonction de detection centralisee dans `downloader.py`.
- Remplacer la logique inline dans `app.py`.
- Appliquer la meme regle pour admin et guest.

Critere d'acceptation:
- Une URL `watch?v=` est toujours traitee comme une chanson.
- Une URL playlist ou album est traitee comme une playlist.
- Les routes admin et guest utilisent la meme logique.

## Ticket V1-02 - Nettoyage dashboard

Contexte:
- La bibliotheque n'est pas livree.

Travail:
- Retirer les references visibles a la bibliotheque / metadata.
- Supprimer le code JS mort lie au cleanup manuel.
- Garder la section "Telechargements recents".

Critere d'acceptation:
- Aucun onglet ou commentaire de bibliotheque n'apparait.
- Aucun bouton cleanup inutile n'est affiche.

## Ticket V1-03 - Suppression `get_stats()`

Contexte:
- La fonction n'apporte pas de valeur produit immediate.

Travail:
- Supprimer `get_stats()` du backend.
- Retirer les appels et dependances associees.

Critere d'acceptation:
- Aucun code de production ne depend de `get_stats()`.

## Ticket V1-04 - Message auth Watcher

Contexte:
- Le warning actuel est trompeur en mode Watcher.

Travail:
- Corriger le message de configuration auth.
- Le message ne doit apparaitre que si aucune auth n'est definie.

Critere d'acceptation:
- Les logs Watcher ne signalent pas a tort une absence d'auth.

## Ticket V1-05 - Limite de duree download

Contexte:
- Un download trop long doit etre bloque avant lancement.

Travail:
- Ajouter `MAX_DURATION_SECONDS`.
- Verifier la duree avant le download.

Critere d'acceptation:
- Une video trop longue est refusee proprement avec un message clair.

## Ticket V1-06 - Bouton ZIP admin

Contexte:
- La section recents existe deja, il manque le bouton cote admin.

Travail:
- Ajouter le bouton ZIP dans le dashboard admin.
- Brancher la route backend correspondante.

Critere d'acceptation:
- L'admin peut telecharger son ZIP depuis le dashboard.

## Ticket V1-07 - ZIP Guest en fin de session

Contexte:
- Le nettoyage Guest doit se faire a la fin de session uniquement.

Travail:
- Conserver les fichiers jusqu'a la fermeture normale de la session.
- Ne pas supprimer les donnees juste apres le ZIP.

Critere d'acceptation:
- Le ZIP Guest n'entraine pas une suppression prematuree.

## Ticket V1-08 - Inactivite Watcher

Contexte:
- Il faut un comportement clair avant l'arret du Docker.

Travail:
- Ajouter un avertissement apres 1 heure d'inactivite.
- Forcer l'arret apres 15 minutes sans reponse.
- Garder une note dans la config pour ne pas oublier la logique.

Critere d'acceptation:
- Le message s'affiche au bon moment.
- Le stop force arrive seulement apres le delai de grace.

## Definition of Done V1

- Le comportement admin est stable.
- Le comportement Guest est clair.
- Les logs sont propres.
- Le dashboard ne montre que des fonctions livrees.