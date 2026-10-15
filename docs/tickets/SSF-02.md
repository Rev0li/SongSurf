---
ticket: SSF-02
title: Fiabilité de l'exploitation
status: todo          # todo → coded → tested → refactored → validated
branch: feat/ssf-02
updated: 2026-10-15
---

# SSF-02 — Fiabilité de l'exploitation

## 🎯 Objectif
Arrêt propre du conteneur (R1), healthcheck juste (R2), yt-dlp maîtrisé (R4), serveur HTTP de prod (R6), restes de code (R7 : `/data/plex_music`, `cancel_flag`).

**Fini quand** : `docker stop` < 2 s avec exit 0 ; conteneur « healthy » sur le NAS.

## ❓ Questions à trancher avant de coder
1. yt-dlp : version épinglée + `make bump-ytdlp` manuel ⭐, ou garder la mise à jour automatique au boot ?
   → Réponse :
2. Serveur HTTP : `waitress` ⭐, ou garder le serveur Flask ?
   → Réponse :
3. `cancel_flag` : supprimer maintenant ⭐ (réintroduit avec l'annulation F2), ou câbler l'annulation tout de suite ?
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
