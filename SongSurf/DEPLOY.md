# 🚀 Déployer SongSurf sur un NAS Synology

## Pré-requis

- Synology DSM avec **Docker** installé (via le Centre de paquets)
- Accès SSH activé sur le NAS (Panneau de configuration → Terminal & SNMP → Activer SSH)
- Un client SSH (PowerShell, Terminal, ou PuTTY)

---

## Étape 1 — Copier le projet sur le NAS

### Option A : Depuis PowerShell (Windows)

```powershell
# Copier tout le projet sur le NAS via SCP
scp -r C:\Users\Molim\Music\MYTUNE\SongSurf utilisateur@IP_DU_NAS:/volume1/docker/songsurf
```

> Remplacez `utilisateur` par votre login DSM et `IP_DU_NAS` par l'IP locale (ex: `192.168.1.45`).

### Option B : Via File Station

1. Ouvrez **File Station** dans DSM
2. Naviguez vers `/docker/` (créez le dossier s'il n'existe pas)
3. Créez un dossier `songsurf`
4. Glissez-déposez les fichiers suivants depuis votre PC :

```
songsurf/
├── Dockerfile
├── docker-compose.yml
├── docker/
│   └── entrypoint.sh
└── python-server/
    ├── app.py
    ├── downloader.py
    ├── organizer.py
    ├── requirements.txt
    └── templates/
        ├── login.html
        └── dashboard.html
```

> ⚠️ Ne copiez **PAS** les dossiers `venv/`, `music/`, `temp/`, `__pycache__/`.

---

## Étape 2 — Configurer le mot de passe

Connectez-vous en SSH au NAS :

```bash
ssh utilisateur@IP_DU_NAS
```

Éditez le `docker-compose.yml` :

```bash
cd /volume1/docker/songsurf
sudo vi docker-compose.yml
```

> Si `vi` vous fait peur, utilisez `nano` (sinon installez-le via `sudo apt-get install nano` ou modifiez le fichier avant de le copier).

Modifiez ces 2 lignes :

```yaml
- SONGSURF_PASSWORD=VotreMotDePasseSecret
- FLASK_SECRET_KEY=UneChaineLongueEtAleatoire
```

**Pour générer une clé secrète Flask :**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copiez le résultat et collez-le comme valeur de `FLASK_SECRET_KEY`.

---

## Étape 3 — Construire et lancer

```bash
cd /volume1/docker/songsurf
sudo docker-compose up -d --build
```

La première fois, ça prend 2-3 minutes (téléchargement Python, FFmpeg, yt-dlp).

### Vérifier que ça tourne :

```bash
# Voir les logs
sudo docker-compose logs -f

# Tester le ping
curl http://localhost:8080/ping
```

Vous devriez voir :
```json
{"message":"SongSurf is running","status":"ok","timestamp":"..."}
```

---

## Étape 4 — Accéder au dashboard

Depuis votre navigateur sur le réseau local :

```
http://IP_DU_NAS:8080
```

Entrez le mot de passe défini à l'étape 2. C'est prêt ! 🎵

---

## Commandes utiles

| Action | Commande |
|---|---|
| Démarrer | `sudo docker-compose up -d` |
| Arrêter | `sudo docker-compose down` |
| Redémarrer | `sudo docker-compose restart` |
| Voir les logs | `sudo docker-compose logs -f` |
| Reconstruire | `sudo docker-compose build --no-cache` |
| Statut | `sudo docker ps` |
---

## Où sont les fichiers musique ?

Les MP3 téléchargés sont dans :

```
/volume1/docker/songsurf/data/music/
└── Artiste/
    └── Album/
        └── Titre.mp3
```

Ce dossier est persistant même si vous reconstruisez le conteneur.

---

## Étape suivante : HTTPS (reverse proxy + DDNS + certificat)

Le dashboard tourne en HTTP sur le port 8080. Pour y accéder depuis l'extérieur en HTTPS, il faut configurer :

1. **DDNS** — Pour avoir un nom de domaine qui pointe vers votre IP publique
   - DSM → Panneau de configuration → Accès externe → DDNS
   - Synology offre un DDNS gratuit en `*.synology.me`

2. **Certificat SSL** — Let's Encrypt gratuit
   - DSM → Panneau de configuration → Sécurité → Certificat
   - Ajouter → Obtenir auprès de Let's Encrypt
   - Renseignez votre domaine DDNS

3. **Reverse Proxy** — Pour rediriger HTTPS → HTTP:8080
   - DSM → Panneau de configuration → Portail de connexion → Avancé → Reverse Proxy
   - Créer une règle :

   | Champ | Valeur |
   |---|---|
   | Nom | SongSurf |
   | Source protocole | HTTPS |
   | Source nom d'hôte | `votrenom.synology.me` |
   | Source port | 443 |
   | Destination protocole | HTTP |
   | Destination nom d'hôte | `localhost` |
   | Destination port | 8080 |

4. **Redirection de port** — Sur votre box/routeur
   - Port externe 443 → IP du NAS, port 443

Après cette config, le dashboard sera accessible via :
```
https://votrenom.synology.me
```

---

## Sécurité en résumé

| Protection | Détail |
|---|---|
| 🔐 Mot de passe | Requis pour accéder au dashboard |
| 🛡️ Anti-bruteforce | 5 tentatives max, blocage 15 min par IP |
| 🔒 HTTPS | Via reverse proxy Synology + Let's Encrypt |
| 🏠 Sessions | Expiration après 7 jours d'inactivité |
| 👤 Container isolé | Utilisateur non-root dans Docker |
