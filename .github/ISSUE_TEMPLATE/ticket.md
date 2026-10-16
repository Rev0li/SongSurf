---
name: Ticket
about: Une tâche technique (une issue = une branche = une PR)
title: "[ID] Titre court"
labels: ""
---

## 🎯 Objectif
<!-- Ce qui doit exister à la fin, en 2-4 phrases. -->

**Fini quand** : <!-- critère vérifiable -->

## ❓ Questions à trancher avant de coder
<!-- ⭐ = recommandation. Réponses en commentaire, puis reportées ici. -->
1.

## ✅ Definition of Done
- [ ] Code implémenté
- [ ] Tests passent (unitaires + intégration)
- [ ] Sécurité vérifiée (si auth / secrets / RBAC concernés)
- [ ] Refactor si nécessaire (tests verts avant ET après)
- [ ] Lint + type-check OK
- [ ] Testé en dev
- [ ] Doc à jour
- [ ] PR validée et mergée (issue fermée)

---

<!--
WORKFLOW : issue → branche feat/<id> → commits `type(ID): …` → PR « [ID] titre » avec `Closes #n` → merge après validation.

PASSAGE DE MAIN : un commentaire par rôle, dans cet ordre, puis le label status:* correspondant.

### 🔨 Code — AAAA-MM-JJ          (label status:coded)
**Fait :**
**Décisions (& pourquoi) :**
**Fichiers :**
**Reste / questions pour le test :**

### 🧪 Test — AAAA-MM-JJ          (label status:tested)
**Couvert :**
**NON couvert (assumé) :**
**Sécurité vérifiée :**
**Bugs trouvés :**
**Audit refactor : X/10** — arguments

### ♻️ Refactor — AAAA-MM-JJ      (label status:refactored)
**Changé :**
**Pourquoi :**
**Risque :**
**Tests verts avant ET après :**

### 🚀 Validation — AAAA-MM-JJ    (merge de la PR → issue fermée)
**Lancé en dev :**
**Lancé en prod :**
**DoD complète :**
**Statut final :**

Repo public : jamais de secret, d'IP, de nom d'hôte interne, ni d'info de stage non anonymisée.
-->
