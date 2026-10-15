---
ticket: SSF-07
title: Polish UI/UX : adaptation à MyCss
status: todo          # todo → coded → tested → refactored → validated
branch: feat/ssf-07
updated: 2026-10-15
---

# SSF-07 — Polish UI/UX : adaptation à MyCss

## 🎯 Objectif
Refonte graphique **par adaptation** : SongSurf adopte le design system MyCss (variables puis composants), puis passe de finition UI/UX (parcours Téléchargement, Métadonnées, mobile). Pas de refonte de zéro, pas de changement fonctionnel.

**Fini quand** : plus aucune couleur/espacement en dur hors MyCss ; clair et sombre OK ; mobile OK ; parcours validés par l'utilisateur.

## ❓ Questions à trancher avant de coder
1. Périmètre : variables MyCss seules (couleurs, espacements, arrondis, typo) ⭐, ou aussi les composants MyCss (boutons, cards, modales) ?
   → Réponse :
2. Intégration de MyCss : sous-module git (comme rev0auth) ⭐, paquet npm, ou copie des fichiers ?
   → Réponse :
3. Passe UX : liste des irritants validée par toi d'abord ⭐, ou maquettes proposées directement ?
   → Réponse :
4. Header commun : l'aligner déjà sur celui de rev0auth (préparation du site unifié) ?
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
