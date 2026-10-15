---
ticket: SSF-04
title: Refactor backend + isolation de l'auth
status: todo          # todo → coded → tested → refactored → validated
branch: feat/ssf-04
updated: 2026-10-15
---

# SSF-04 — Refactor backend + isolation de l'auth

## 🎯 Objectif
Découper `server/app.py` (2 026 lignes) en blueprints (M1) et isoler l'auth derrière une interface `get_current_user()` unique — préparation du détachement Auth / SongSurf. Découpage proposé dans `PLAN_V1.md` étape 4.

**Fini quand** : Tous les tests passent sans changement de comportement ; aucun fichier > ~500 lignes.

## ❓ Questions à trancher avant de coder
1. Valider le découpage proposé (`auth/`, `core/`, `routes/`), ou une structure plus plate ?
   → Réponse :
2. Le Watcher reste-t-il le seul point d'entrée en V1 ⭐, ou SongSurf doit-il déjà pouvoir valider un JWT lui-même ?
   → Réponse :
3. Garder exactement les mêmes URLs d'API ⭐ (zéro changement pour l'extension et le frontend) ?
   → Réponse :

## ✅ Definition of Done
- [ ] Code implémenté
- [ ] Tests passent (unitaires + intégration)
- [ ] Sécurité vérifiée (si auth / secrets / RBAC concernés)
- [ ] Refactor si nécessaire (tests verts avant ET après)
- [ ] Lint + type-check OK
- [ ] Testé en dev
- [ ] Doc à jour

---

## 🔨 Code — <date>
**Fait :**
**Décisions (& pourquoi) :**
**Fichiers :**
**Reste / questions pour le test :**

## 🧪 Test — <date>
**Couvert :**
**NON couvert (assumé) :**
**Sécurité vérifiée :**
**Bugs trouvés :**
**Audit refactor : X/10** — <arguments>

## ♻️ Refactor — <date>
**Changé :**
**Pourquoi :**
**Risque :**
**Tests verts avant ET après :**

## 🚀 Validation — <date>
**Lancé en dev :**
**Lancé en prod :**
**DoD complète :**
**Statut final :**
