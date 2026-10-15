---
ticket: SSF-05
title: Refactor frontend
status: todo          # todo → coded → tested → refactored → validated
branch: feat/ssf-05
updated: 2026-10-15
---

# SSF-05 — Refactor frontend

## 🎯 Objectif
Découper `routes/metadata/+page.svelte` (2 194 lignes) en composants + store (M2) ; mettre la stack à jour (M3 : Node 20 en fin de vie, Svelte 4).

**Fini quand** : Aucun composant > ~400 lignes ; `svelte-check` à 0 erreur ; aucun changement visuel.

## ❓ Questions à trancher avant de coder
1. Ordre : découper en Svelte 4 puis migrer en Svelte 5 ⭐, ou tout d'un coup ?
   → Réponse :
2. Passer à Node 22 LTS ⭐ ?
   → Réponse :
3. Pendant le découpage, préparer déjà le terrain MyCss (variables CSS centralisées, aucune valeur en dur) ⭐ ? L'adaptation graphique elle-même est SSF-07.
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
