---
ticket: SSF-06
title: Qualité : CI, tests, doc
status: todo          # todo → coded → tested → refactored → validated
branch: feat/ssf-06
updated: 2026-10-15
---

# SSF-06 — Qualité : CI, tests, doc

## 🎯 Objectif
Mettre en place la CI et les deps de dev (M4), un minimum de tests frontend (M5), et resynchroniser la doc (`ARCHITECTURE`, `API_OR_MODULES`, `TEST_PLAN`, `CLAUDE.md`) avec le code refactoré.

**Fini quand** : CI verte ; les 3 tests watcher tournent ; docs alignées sur le code.

## ❓ Questions à trancher avant de coder
1. CI GitHub Actions (pytest + ruff + build frontend) ⭐, ou juste un `make check` local ?
   → Réponse :
2. Tests frontend : `svelte-check` seul ⭐ pour la V1, ou Vitest dès maintenant ?
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
