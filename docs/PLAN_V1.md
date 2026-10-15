# Plan V1 — SongSurf

Basé sur `AUDIT_2026-10-15.md` (les codes S1, R3, M1… y renvoient).
Principe : **une étape à la fois**. Chaque étape commence par ses questions de décision ; rien n'est codé tant que tu n'as pas tranché. Ma recommandation est indiquée par ⭐, elle ne t'engage pas.

## La vision (validée le 2026-10-15)

```
Aujourd'hui                          V1                                    Après la V1
───────────                          ──                                    ───────────
rev0auth ──JWT──► SongSurf           SongSurf propre, auth = un            Un site unifié (portail)
(SongSurf dépend de rev0auth          "fournisseur" interchangeable         ├── service Auth (rev0auth)
 pour exister)                        (rev0auth en est un parmi d'autres)    ├── service SongSurf
                                                                            └── UI commune (header, thème)
```

- Les **deux micro-services** sont **Auth + SongSurf** : deux services indépendants, réunis sous un même portail avec une UI commune.
- La V1 ne change **pas** l'architecture de déploiement : on nettoie, on sécurise, on découpe le code.
- Mais la V1 prépare le détachement : l'authentification est isolée derrière une interface unique, pour que « brancher SongSurf sur autre chose que rev0auth » devienne un changement local, pas une réécriture.
- Le portail unifié est **hors V1** (étape 8, à cadrer plus tard).

## Workflow

- Un ticket par étape dans `docs/tickets/SSF-0X.md` (format `ticket-handoff` : code → test → refactor → valide, une branche `feat/ssf-0x` par ticket).
- Au début de chaque ticket : on répond d'abord aux **Questions** du ticket, les réponses sont notées dans le ticket, puis on code.

---

## Étape 0 — Cadrage + ménage de la documentation ✅ (2026-10-15)

Décisions prises :
- `documentation/` renommé en `docs/` (même convention que rev0auth).
- Supprimés : `RELEASE_NOTES.md` (mode guest obsolète, remplacé par un `CHANGELOG.md` à la V1), `REV0AUTH_INTEGRATION.md` (backend Rust supprimé ; `CONNECTOR.md` reste le seul contrat), `KNOWN_ISSUES.md` (détails repris dans l'audit, R1 et R2).
- Fusionnés : `SongSurf/DEPLOY.md` + `deploy_action.md` + `deploy_troubleshooting.md` → `docs/DEPLOY.md` (§11 = pièges Synology).
- Liens mis à jour dans `README.md`, `CLAUDE.md`, `CONNECTOR.md`, `server/app.py`.
- Tickets SSF-01 à SSF-08 créés dans `docs/tickets/` (SSF-07 = polish UI/UX ajouté le 2026-10-15).

Docs restantes : `README.md`, `CLAUDE.md`, `docs/{ARCHITECTURE, API_OR_MODULES, CONNECTOR, DEPLOY, TEST_PLAN, AUDIT_2026-10-15, PLAN_V1}.md`. `TEST_PLAN.md` mentionne encore le téléchargement playlist (supprimé) : à remettre à jour à l'étape 6.

---

## Étape 1 — Sécurité · SSF-01 (bloquant avant toute nouveauté)

Audit : S1 (CORS), S2 (cookies), S3 (taille des requêtes), S4 (fuite `/api/status`).

**Questions**
1. CORS : on n'autorise **que** l'ID de l'extension SongSurf ⭐ — ou tu veux garder une liste configurable de plusieurs extensions ?
2. Cookies YouTube : réservés à l'admin ⭐ (simple, un seul compte YouTube) — ou cookies par utilisateur (chaque membre utilise son compte) ?
3. Taille max des requêtes : 10 Mo ⭐ ?

**Fini quand** : tests ajoutés pour chaque correctif, testé avec l'extension réelle sur le NAS.

---

## Étape 2 — Fiabilité de l'exploitation · SSF-02

Audit : R1 (SIGKILL), R2 (healthcheck), R4 (yt-dlp), R6 (serveur de prod), R7 (restes).

**Questions**
1. yt-dlp : version épinglée + `make bump-ytdlp` manuel ⭐ — ou garder la mise à jour automatique au boot ?
2. Serveur HTTP : `waitress` ⭐ — ou garder le serveur Flask (suffisant pour quelques utilisateurs) ?
3. `cancel_flag` : supprimer maintenant ⭐ et réintroduire proprement avec F2 — ou câbler l'annulation tout de suite ?

**Fini quand** : `docker stop` < 2 s avec exit 0, conteneur « healthy » sur le NAS.

---

## Étape 3 — État persistant + équité multi-utilisateur · SSF-03

Audit : R3 (file en mémoire), R5 (ZIP), E1 (quota), E2 (file FIFO).

**Questions**
1. Persistance : SQLite local dans `/data` ⭐ — ou PostgreSQL de rev0auth (plus de couplage, contraire à la vision) — ou rester en mémoire ?
2. Quota journalier : par utilisateur ⭐, admin illimité ?
3. File : round-robin entre utilisateurs ⭐ — ou FIFO avec priorité admin ?
4. ZIP : génération en arrière-plan + polling ⭐ — ou juste passer en `ZIP_STORED` pour l'instant ?

**Fini quand** : un redémarrage en plein batch reprend la file ; deux membres en parallèle avancent tous les deux.

---

## Étape 4 — Refactor backend (+ isolation de l'auth) · SSF-04

Audit : M1. C'est l'étape qui prépare la vision long terme.

Découpage proposé de `server/app.py` (2 026 lignes) :
```
server/
├── app.py              # création de l'app, enregistrement des blueprints, ~100 lignes
├── auth/               # ← interface unique "qui est l'utilisateur ?"
│   ├── provider.py     #   contrat : get_current_user() -> User | None
│   ├── watcher.py      #   fournisseur actuel (headers injectés par le Watcher)
│   └── dev.py          #   DEV_MODE
├── core/               # queue/worker, storage par utilisateur, state (SQLite)
├── routes/             # download, library, metadata, extension, admin, zip
└── (downloader, organizer, genre_lookup, library_audit inchangés)
```

**Questions**
1. Tu valides ce découpage, ou tu préfères moins de niveaux (tout à plat dans `server/`) ?
2. Le Watcher reste-t-il le seul point d'entrée en V1 ⭐ — ou on prévoit déjà que SongSurf puisse valider un JWT lui-même (utile si le Watcher disparaît un jour) ?
3. Les routes gardent les mêmes URLs ⭐ (zéro changement pour l'extension et le frontend) ?

**Fini quand** : tous les tests passent sans modification de comportement, aucun fichier > ~500 lignes.

---

## Étape 5 — Refactor frontend · SSF-05

Audit : M2, M3.

**Questions**
1. Ordre : d'abord découper `metadata/+page.svelte` en Svelte 4, puis migrer en Svelte 5 ⭐ (deux étapes plus sûres) — ou tout d'un coup ?
2. Node 22 LTS ⭐ ?
3. Pendant le découpage, on prépare déjà les composants pour MyCss (variables CSS centralisées, pas de valeurs en dur) ⭐ — l'adaptation graphique elle-même se fait à l'étape 7 ?

**Fini quand** : aucun composant > ~400 lignes, `svelte-check` à 0 erreur, aucun changement visuel.

---

## Étape 6 — Qualité : CI, tests, doc · SSF-06

Audit : M4, M5 + resynchronisation des docs.

**Questions**
1. CI GitHub Actions (pytest + ruff + build frontend) ⭐ — ou juste un `make check` local ?
2. Tests frontend : `svelte-check` seul ⭐ pour la V1 — ou Vitest dès maintenant ?

**Fini quand** : CI verte, `ARCHITECTURE.md` / `API_OR_MODULES.md` / `TEST_PLAN.md` / `CLAUDE.md` alignés sur le nouveau code.

---

## Étape 7 — Polish UI/UX : adaptation à MyCss · SSF-07

Refonte graphique **par adaptation** (pas de refonte de zéro) : SongSurf adopte les variables et composants de MyCss, puis une passe de finition UI/UX. Placée en fin de parcours pour travailler sur un frontend déjà découpé (étape 5) et stable.

**Questions**
1. Périmètre : variables MyCss seules (couleurs, espacements, arrondis, typo) ⭐ — ou aussi les composants MyCss (boutons, cards, modales) ?
2. Comment MyCss arrive dans SongSurf : sous-module git (comme rev0auth) ⭐, paquet npm, ou copie des fichiers ?
3. La passe UX : on fait d'abord une liste des irritants (parcours Téléchargement, Métadonnées, mobile) que tu valides ⭐, ou je propose directement des maquettes ?
4. Le Header commun (93 px, « ← Mon espace ») : on l'aligne déjà sur celui de rev0auth, en prévision du site unifié ?

**Fini quand** : plus aucune valeur de couleur/espacement en dur hors MyCss, clair et sombre OK, mobile OK, parcours validés par toi.

---

## Étape 8 — Sortie de la V1 · SSF-08

Audit : M6.

**Questions**
1. Numéro : `1.0.0` commun au serveur, au frontend et à l'extension ⭐ ?
2. Où afficher la version : `/ping` + pied de page ⭐ ?
3. Tag git `v1.0.0` + `CHANGELOG.md` ⭐ ?

**Fini quand** : V1 déployée sur le NAS, extension en 1.0.0, tag posé.

---

## Pistes liées (hors repo SongSurf)

### MyCss — design system commun
- Repo séparé (`MyCss`), en cours de récupération. Il sera la source des variables CSS et des composants communs à SongSurf, rev0auth et au portfolio.
- **SongSurf n'est pas refondu de zéro** : on l'*adapte* à MyCss (remplacer ses variables locales de `frontend/src/lib/styles/design-system.css` par celles de MyCss, sans changer l'UX). Préparé en SSF-05 (question 3), réalisé en **SSF-07** (polish UI/UX).
- Les couleurs actuelles de SongSurf (rose `#E8B7C4`, turquoise `#6EDAD3`) correspondent déjà au questionnaire d'identité (Obsidian `revosafe/Mycss/`).

### Portfolio — vitrine publique
- La vitrine « SongSurf + Jellyfin » vit dans le **portfolio** (`~/dev/portfolio`, refait de zéro dans une autre session), pas dans ce repo. Idées : [`VITRINE_IDEAS.md`](VITRINE_IDEAS.md).
- Ce que SongSurf devra fournir plus tard (après la V1) : un mode **bac à sable** (bibliothèque de démo en musique libre, aucun téléchargement réel, remise à zéro auto) et l'acceptation d'un rôle `demo` à jeton court émis par rev0auth. À transformer en ticket le moment venu.

---

## Étape 9 — Après la V1 : détachement et site unifié (à cadrer plus tard)

Pas de code ici, seulement les questions à trancher le moment venu :

1. ~~Que sont les deux micro-services ?~~ → **Auth + SongSurf** (décidé le 2026-10-15).
2. **Le site unifié** : un portail (shell) qui intègre chaque service sous son chemin (`/songsurf`, `/auth`…) avec un header commun ? Ou un seul frontend SvelteKit qui appelle les APIs des services ?
3. **L'auth** : rev0auth reste-t-il le fournisseur central, ou un standard (OIDC) pour que SongSurf fonctionne aussi seul, sans rev0auth ?
4. **Le Watcher** (démarrage à la demande) : il reste propre à SongSurf, ou devient une passerelle commune à tous les services ?
5. Les fonctionnalités F1 à F6 de l'audit : on les fait avant ou après ce découpage ?
