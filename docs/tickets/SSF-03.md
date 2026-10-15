---
ticket: SSF-03
title: État persistant + équité multi-utilisateur
status: todo          # todo → coded → tested → refactored → validated
branch: feat/ssf-03
updated: 2026-10-15
---

# SSF-03 — État persistant + équité multi-utilisateur

## 🎯 Objectif
La file, le quota et l'état ZIP survivent aux redémarrages (R3) ; export ZIP non bloquant (R5) ; quota par utilisateur (E1) ; file équitable entre membres (E2).

**Fini quand** : Un redémarrage en plein batch reprend la file ; deux membres en parallèle avancent tous les deux.

## ❓ Questions à trancher avant de coder
1. Persistance : SQLite dans `/data` ⭐, PostgreSQL de rev0auth (plus de couplage, contraire à la vision), ou rester en mémoire ?
   → Réponse :
2. Quota journalier : par utilisateur ⭐, admin illimité ?
   → Réponse :
3. File : round-robin entre utilisateurs ⭐, ou FIFO avec priorité admin ?
   → Réponse :
4. ZIP : génération en arrière-plan + polling ⭐, ou seulement `ZIP_STORED` pour l'instant ?
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
