# Déploiement SongSurf → NAS

## Méthode actuelle — `make deploy-nas`

Une commande depuis ta machine de dev. Rien à faire sur le NAS.

```bash
cd SongSurf/SongSurf
make deploy-nas
```

Ce que ça fait en une étape :
1. `rsync` — synchronise les fichiers vers `~/songsurf/` sur le NAS (exclut `data/`, `logs/`, `.env`, `.secrets`)
2. `ssh` — relance `watcher` et `songsurf` avec rebuild Docker

### Override des variables (optionnel)

```bash
make deploy-nas NAS_USER=rev0li08 NAS_HOST=192.168.1.45 NAS_DIR=/volume1/docker/songsurf
```

Par défaut : `NAS_USER=rev0li08`, `NAS_HOST=192.168.1.45`, `NAS_PORT=22`, `NAS_DIR=/volume1/docker/songsurf`.
Pour les fixer durablement, les ajouter dans `.env` ou les exporter en shell.

### Prérequis (première fois)

```bash
# 1. Créer les dossiers data sur le NAS
ssh revoli@100.121.1.89 "mkdir -p ~/songsurf/data/music ~/songsurf/data/music_guest ~/songsurf/data/temp ~/songsurf/logs && chmod 777 ~/songsurf/data"

# 2. Copier .env et .secrets (une seule fois — jamais dans git)
scp .env     revoli@100.121.1.89:~/songsurf/.env
scp .secrets revoli@100.121.1.89:~/songsurf/.secrets
```

`.env` et `.secrets` restent sur le NAS entre les déploiements.

---

## Plus tard — CI/CD automatique

Quand le projet bougera plus souvent : self-hosted GitHub Actions runner sur le NAS.
- Le runner tourne sur le NAS et fait une connexion **sortante** vers GitHub
- Aucun port entrant, aucun Tailscale, aucun SSH exposé
- Sur `git push main` → GitHub envoie le job → runner exécute `make deploy-nas` localement

À documenter quand le besoin se présente.
