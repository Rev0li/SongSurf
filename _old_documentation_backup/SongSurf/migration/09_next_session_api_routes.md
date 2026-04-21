# Next Session - Audit API, Routes et Redirections

## Contexte
Des redirections semblent instables (boucles, mauvaise page cible, comportement non deterministe entre admin/guest).

Objectif de cette session: stabiliser le flux de navigation en validant toute la chaine:
- Watcher (auth + loading + proxy)
- SongSurf (routes Flask + decorators)
- Frontend (calls API + redirections JS)

## Resultat attendu
A la fin de la session, on doit avoir:
- un mapping clair de toutes les routes critiques
- une politique unique de redirection
- une suppression des boucles loading/ready
- une checklist de tests de non-regression admin/guest

## Scope prioritaire
1. Watcher
- `/administrator`
- `/guest/login`
- `/watcher/loading`
- `/watcher/ready`
- proxy catch-all

2. SongSurf
- routes auth admin
- routes auth guest
- decorators (`login_required`, `guest_required`)
- pages dashboard (`/`, `/guest`, `/guest/login`)

3. Frontend
- scripts de page admin/guest
- gestion des erreurs API (401/403/5xx)
- redirections forcees apres login/logout

## Plan pas-a-pas
1. Inventaire des routes
- Extraire toutes les routes Watcher + SongSurf.
- Noter methodes HTTP + conditions d'acces.

2. Cartographie des transitions
- Tracer les transitions de pages:
  - anonymous -> login admin -> loading -> dashboard admin
  - anonymous -> login guest -> loading -> dashboard guest
  - session expiree -> retour login

3. Verification des points de rupture
- Refresh navigateur pendant loading.
- Refresh apres login guest/admin.
- Favicon et assets statiques via proxy.
- Cas SongSurf indisponible (timeout court + fallback propre).

4. Regles de redirection uniques
- Definir qui decide la redirection (backend vs frontend).
- Eviter les doubles decisions contradictoires.
- Normaliser les codes de retour API (401/403/409/5xx).

5. Correctifs
- Appliquer correctifs backend d'abord.
- Puis corriger JS de navigation.
- Ajouter logs explicites des redirections.

6. Validation
- Rejouer les scenarios de bout en bout.
- Valider en local et mode NAS.

## Checklist de debug (a utiliser pendant la session)
- `curl -s http://127.0.0.1:8080/watcher/ready`
- `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081/ping`
- `docker logs watcher --tail 200`
- `docker logs songsurf --tail 200`
- verifier cookies de session (admin + guest)

## Definition of Done
- plus de boucle infinie loading
- redirection correcte apres login admin et guest
- refresh navigateur preserve l'etat attendu
- si backend indisponible: message propre + retry controle
- documentation mise a jour dans `debug.md` et `DEPLOY.md` si necessaire

## Livrables de la prochaine session
- patch backend routes/decorators
- patch frontend redirections
- table de correspondance route -> redirection cible
- rapport de test court (scenarios + resultat)


Enlever le button nettoyage des fichier temporaire. Cette fonction nous est utile en background pas en frontend. La bibliotheque des Guest n'est pas bien a jour sur leur data/music_guest/session/bibliotheque a corriger. 
La cover n'a pas etait extraite dans le dossier album comme en admin.
Quand le serveur se down je voudrai que l'app se "referme" soit en mode lock avec un button launch. (je vais enlever l identification)
Une nouvelle pro arrive on se branchera dessus pour Le projet.
