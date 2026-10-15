---
ticket: SSF-01
title: Sécurité : CORS, cookies, taille des requêtes, /api/status
status: todo          # todo → coded → tested → refactored → validated
branch: feat/ssf-01
updated: 2026-10-15
---

# SSF-01 — Sécurité : CORS, cookies, taille des requêtes, /api/status

## 🎯 Objectif
Corriger les 4 failles de l'audit avant toute nouveauté : CORS du watcher (S1), écriture des cookies YouTube par n'importe quel membre (S2), pas de `MAX_CONTENT_LENGTH` (S3), fuite de `last_completed`/`last_error` entre membres (S4).

**Fini quand** : Testé avec l'extension réelle sur le NAS ; `/security-review` lancé (ticket auth).

## ❓ Questions à trancher avant de coder
1. CORS : n'autoriser **que** l'ID de l'extension SongSurf ⭐, ou une liste configurable de plusieurs extensions ?
   → Réponse :
2. Cookies YouTube : réservés à l'admin ⭐ (un seul compte YouTube), ou cookies par utilisateur ?
   → Réponse :
3. Taille max des requêtes : 10 Mo ⭐ ?
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
