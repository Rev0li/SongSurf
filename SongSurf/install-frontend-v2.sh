#!/bin/bash
# install-frontend-v2.sh
# Script d'installation automatique pour SongSurf Frontend V2

set -e  # Arrêter en cas d'erreur

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonctions utilitaires
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Banner
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🎵  SongSurf Frontend V2 — Installation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Vérifications préalables
log_info "Vérification de l'environnement..."

if [ ! -f "docker-compose.yml" ]; then
    log_error "Erreur : docker-compose.yml introuvable."
    log_error "Ce script doit être exécuté dans le dossier racine de SongSurf."
    exit 1
fi

if [ ! -d "server" ]; then
    log_error "Erreur : dossier server introuvable."
    exit 1
fi

log_success "Environnement OK"

# Étape 1 : Créer la structure
log_info "Création de la structure frontend..."

mkdir -p static/css/pages
mkdir -p static/js/pages
mkdir -p templates/pages

log_success "Structure créée"

# Étape 2 : Copier les fichiers (à adapter selon votre méthode de transfert)
log_info "Copie des fichiers frontend..."

# Option A : Si les fichiers sont dans un dossier local SongSurf/
if [ -d "../SongSurf" ]; then
    log_info "Fichiers source détectés dans ../SongSurf"
    
    # CSS
    cp ../SongSurf/static/css/design-system.css static/css/
    cp ../SongSurf/static/css/components.css static/css/
    cp ../SongSurf/static/css/layouts.css static/css/
    cp ../SongSurf/static/css/pages/dashboard.css static/css/pages/
    
    # JS
    cp ../SongSurf/static/js/api.js static/js/
    cp ../SongSurf/static/js/pages/dashboard-admin.js static/js/pages/
    
    # Templates
    cp ../SongSurf/templates/base.html templates/
    cp ../SongSurf/templates/pages/login.html templates/pages/
    cp ../SongSurf/templates/pages/dashboard-admin.html templates/pages/
    
    log_success "Fichiers frontend copiés"
else
    log_warning "Dossier ../SongSurf non trouvé."
    log_info "Veuillez copier manuellement les fichiers ou adapter le script."
    exit 1
fi

# Étape 3 : Vérifier docker-compose.yml
log_info "Vérification de docker-compose.yml..."

if grep -q "./static:/app/static" docker-compose.yml; then
    log_success "Volume static déjà configuré dans docker-compose.yml"
else
    log_warning "Le volume static n'est pas configuré dans docker-compose.yml"
    log_info "Ajout automatique du volume..."
    
    # Backup
    cp docker-compose.yml docker-compose.yml.backup
    
    # Ajouter le volume (méthode simple : insertion après server/templates)
    sed -i '/server\/templates:\/app\/templates/a\      - ./static:/app/static' docker-compose.yml
    
    log_success "Volume static ajouté (backup créé : docker-compose.yml.backup)"
fi

# Étape 4 : Modifications backend
log_info "Application des modifications backend..."

# Backup
cp server/organizer.py server/organizer.py.backup
cp server/templates/guest_dashboard.html server/templates/guest_dashboard.html.backup

log_warning "Les modifications backend doivent être appliquées MANUELLEMENT."
log_info "Consultez METADATA_CHEATSHEET.md pour les instructions détaillées."
log_info "Fichiers backupés :"
log_info "  - server/organizer.py.backup"
log_info "  - server/templates/guest_dashboard.html.backup"

# Étape 5 : Rebuild
log_info "Rebuild du container (cela peut prendre quelques minutes)..."

docker-compose down
docker-compose build --no-cache

log_success "Build terminé"

# Étape 6 : Démarrage
log_info "Démarrage des containers..."

docker-compose up -d

log_success "Containers démarrés"

# Attendre que le serveur soit prêt
log_info "Attente du démarrage du serveur (15s)..."
sleep 15

# Étape 7 : Tests
log_info "Vérification de l'installation..."

# Test 1 : Serveur répond
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 | grep -q "200\|302"; then
    log_success "Serveur accessible sur http://localhost:8080"
else
    log_warning "Le serveur ne répond pas encore. Vérifiez les logs : docker-compose logs -f"
fi

# Test 2 : Fichiers CSS accessibles
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/static/css/design-system.css | grep -q "200"; then
    log_success "Fichiers CSS accessibles"
else
    log_warning "Fichiers CSS non accessibles. Vérifiez le montage du volume static."
fi

# Résumé
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Installation terminée !"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_success "Frontend V2 installé avec succès"
echo ""
log_info "Prochaines étapes :"
echo "  1. Appliquer les modifications backend (voir METADATA_CHEATSHEET.md)"
echo "  2. Redémarrer le container : docker-compose restart songsurf"
echo "  3. Accéder au dashboard : http://localhost:8080"
echo ""
log_info "Fichiers de backup créés :"
echo "  - docker-compose.yml.backup"
echo "  - server/organizer.py.backup"
echo "  - server/templates/guest_dashboard.html.backup"
echo ""
log_info "Documentation :"
echo "  - README.md : Architecture complète"
echo "  - INSTALL.md : Installation manuelle détaillée"
echo "  - METADATA_CHEATSHEET.md : Modifications backend"
echo "  - CHANGELOG.md : Récapitulatif des changements"
echo ""
log_warning "N'oubliez pas d'appliquer les modifications backend pour les bugs et métadonnées !"
echo ""
