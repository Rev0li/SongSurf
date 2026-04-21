# Migration SongSurf (Python -> Rust)

Ce dossier est ton guide de migration progressif.
Objectif: apprendre Rust en construisant, sans casser la prod.

## Parcours recommande

1. Lire `01_etat_actuel.md`
2. Lire `02_architecture_cible.md`
3. Implémenter la base securite dans `04_plan_python_stabilisation.md`
4. Construire les comptes/tokens selon `03_modele_donnees_comptes_tokens.md`
5. Demarrer la migration Rust avec `05_plan_migration_rust.md`
6. Suivre l'entrainement `06_roadmap_apprentissage_rust.md`
7. Valider chaque jalon avec `07_checklists_go_live.md`
8. Implementer la partie UI comptes via `08_backlog_dashboard_accounts.md`

## Regle d'or de migration

- Pas de big-bang rewrite.
- Garder des API stables pour le frontend.
- Migrer par vertical slice (auth, puis comptes, puis media).
- Mesurer avant/apres (latence, erreurs, taux de login reussi).

## Definitions rapides

- Access token: token court (ex: 15 min)
- Refresh token: token long (ex: 7-30 jours), revocable
- RBAC: controle des permissions par role (`owner`, `friend`, `guest-temp`)
- Session restore: retrouver l'utilisateur apres refresh/restart
