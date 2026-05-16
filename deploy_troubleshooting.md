# Déploiement NAS — Guide de dépannage

Problèmes rencontrés lors de la mise en place de `make deploy-nas` sur Synology DSM.
Chaque section = un problème réel résolu.

---

## 1. rsync — Permission denied (auth)

**Symptôme**
```
Permission denied, please try again.
rsync: connection unexpectedly closed (code 12)
```

**Cause** : Le dossier `~/.ssh/` n'existait pas sur le NAS — `ssh-copy-id` avait échoué silencieusement.

**Solution**
```bash
# Créer le dossier .ssh sur le NAS
ssh -p 22 rev0li08@192.168.1.45 "mkdir -p ~/.ssh && chmod 700 ~/.ssh"

# Copier la clé publique
cat ~/.ssh/nas_songsurf.pub | ssh -p 22 rev0li08@192.168.1.45 \
  "cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

---

## 2. rsync — Permission denied (service Synology)

**Symptôme** : SSH avec clé fonctionne (`ssh nas-songsurf "echo ok"` = ok) mais rsync échoue quand même avec "Permission denied".

**Cause** : Synology patche son binaire rsync pour vérifier que le service rsync DSM est activé, même en mode SSH.

**Solution** : DSM → Panneau de configuration → Services de fichiers → onglet **rsync** → cocher "Activer le service rsync" (port 22) → Apply.

---

## 3. docker-compose introuvable (PATH SSH non-interactif)

**Symptôme**
```
[compose-switch] Aucun moteur Compose trouvé.
```

**Cause** : `/usr/local/bin` n'est pas dans le PATH des sessions SSH non-interactives sur Synology. `docker-compose` est pourtant bien à `/usr/local/bin/docker-compose`.

**Solution** : Préfixer le PATH dans la commande SSH du Makefile :
```bash
PATH=/usr/local/bin:/var/packages/Docker/target/usr/bin:$PATH
```

---

## 4. Variables secrets non interpolées (docker-compose V1)

**Symptôme**
```
Missing mandatory value for "environment" option: WATCHER_FLASK_SECRET_KEY is required
```

**Cause** : Docker-compose V1 (`1.28.5`) ne charge pas `env_file` pour l'interpolation des variables dans `docker-compose.yml` — seulement pour les env vars du container. Le `${VAR:?message}` dans `environment:` nécessite que la variable soit dans le shell.

**Solution** : Sourcer `.env` et `.secrets` avant docker-compose avec `set -a` :
```bash
set -a && . ./.env && . ./.secrets && set +a && docker-compose ...
```
`set -a` exporte automatiquement toutes les variables sourcées vers les sous-processus.

---

## 5. docker introuvable (PATH SSH non-interactif)

**Symptôme**
```
sh: docker: command not found
```

**Cause** : Docker (installé via le package DSM "Docker") est dans `/var/packages/Docker/target/usr/bin/`, absent du PATH SSH.

**Solution** : Inclus dans le PATH du Makefile :
```bash
PATH=/usr/local/bin:/var/packages/Docker/target/usr/bin:$PATH
```

Vérification : `ssh nas-songsurf "PATH=/var/packages/Docker/target/usr/bin:\$PATH docker ps"`

---

## 6. Permission refusée sur le socket Docker

**Symptôme**
```
PermissionError: [Errno 13] Permission denied
docker.errors.DockerException: Error while fetching server API version
```

**Cause** : `/var/run/docker.sock` appartient à `root:root` (660). `rev0li08` n'est pas dans le groupe root.

**Solution** : Tâche planifiée DSM exécutée au démarrage en tant que `root` :

DSM → Panneau de configuration → Planificateur de tâches → Créer → Tâche déclenchée → Script défini par l'utilisateur

- **Utilisateur** : `root`
- **Événement** : Démarrage
- **Script** :
```bash
chown root:administrators /var/run/docker.sock
chmod 660 /var/run/docker.sock
```

`rev0li08` est dans le groupe `administrators` (gid=101) — ce changement lui donne accès au socket.
Exécuter la tâche manuellement après création pour l'appliquer sans reboot.

> Cette tâche est nécessaire à chaque redémarrage du NAS car `/var/run/` est recréé au boot.

---

## Commande finale fonctionnelle

```bash
# Depuis SongSurf/SongSurf/ sur la machine de dev
make deploy-nas

# Ou dry-run pour prévisualiser
make deploy-nas-dry
```

Le Makefile complet avec toutes les corrections est dans `Makefile` (section `deploy-nas`).

---

## Récapitulatif de la configuration NAS

| Élément | Valeur |
|---|---|
| Host | `192.168.1.45` |
| User | `rev0li08` |
| Port SSH | `22` |
| Clé SSH | `~/.ssh/nas_songsurf` |
| Alias SSH | `nas-songsurf` (dans `~/.ssh/config`) |
| Dossier deploy | `/volume1/docker/songsurf/` |
| docker-compose | `/usr/local/bin/docker-compose` (v1.28.5) |
| docker | `/var/packages/Docker/target/usr/bin/docker` |
| `.env` / `.secrets` | Sur le NAS uniquement — jamais dans git, copiés via rsync une fois |
