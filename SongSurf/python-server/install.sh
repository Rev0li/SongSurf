#!/bin/bash
# ============================================
# 🎵 SongSurf - Installation Automatique
# ============================================
# 
# Ce script installe tout automatiquement :
#   ✅ Environnement virtuel Python
#   ✅ Toutes les dépendances
#   ✅ FFmpeg (si nécessaire)
#   ✅ Dossiers de travail
#
# Usage: ./install.sh
# ============================================

set -e  # Arrêter en cas d'erreur

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Fonction d'affichage
print_header() {
    echo -e "${PURPLE}============================================${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}============================================${NC}"
}

print_step() {
    echo -e "${CYAN}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ============================================
# DÉBUT DE L'INSTALLATION
# ============================================

clear
print_header "🎵 SongSurf - Installation Automatique"

# S'assurer que le script s'exécute depuis son dossier (pour trouver requirements.txt, venv, etc.)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { print_error "Impossible de changer de répertoire vers $SCRIPT_DIR"; exit 1; }

# ============================================
# 1. Vérifier Python
# ============================================

print_step "Vérification de Python..."

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 n'est pas installé"
    echo ""
    print_info "Installation automatique..."
    
    # Détecter l'OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt update && sudo apt install -y python3 python3-venv python3-pip
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install python3
    else
        print_error "OS non supporté. Installez Python 3 manuellement."
        exit 1
    fi
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
print_success "Python $PYTHON_VERSION détecté"

# ============================================
# 2. Vérifier FFmpeg
# ============================================

print_step "Vérification de FFmpeg..."

# Fonction pour installer FFmpeg localement (sans sudo)
install_ffmpeg_local() {
    print_info "Installation locale de FFmpeg (sans sudo)..."
    
    INSTALL_DIR="$HOME/.local/ffmpeg"
    
    # Vérifier si FFmpeg local existe déjà
    if [ -d "$INSTALL_DIR" ]; then
        EXISTING_FFMPEG=$(find "$INSTALL_DIR" -maxdepth 2 -type f -name "ffmpeg" 2>/dev/null | head -n 1)
        if [ -n "$EXISTING_FFMPEG" ] && [ -x "$EXISTING_FFMPEG" ]; then
            FFMPEG_VERSION=$("$EXISTING_FFMPEG" -version 2>&1 | head -n1 | awk '{print $3}')
            print_success "FFmpeg $FFMPEG_VERSION déjà installé localement"
            print_info "Emplacement: $EXISTING_FFMPEG"
            return 0
        fi
    fi
    
    mkdir -p "$INSTALL_DIR"
    
    # Sauvegarder le répertoire courant
    CURRENT_DIR=$(pwd)
    
    # Détecter l'architecture
    ARCH=$(uname -m)
    if [ "$ARCH" = "x86_64" ]; then
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else
        print_error "Architecture non supportée: $ARCH"
        return 1
    fi
    
    print_info "Téléchargement de FFmpeg..."
    cd "$INSTALL_DIR"
    
    if command -v wget &> /dev/null; then
        wget -q --show-progress "$FFMPEG_URL" -O ffmpeg.tar.xz
    elif command -v curl &> /dev/null; then
        curl -L "$FFMPEG_URL" -o ffmpeg.tar.xz
    else
        print_error "wget ou curl requis pour télécharger FFmpeg"
        cd "$CURRENT_DIR"  # Restaurer le répertoire
        return 1
    fi
    
    print_info "Extraction..."
    tar -xf ffmpeg.tar.xz 2>/dev/null
    rm -f ffmpeg.tar.xz
    
    # Trouver le dossier extrait
    FFMPEG_DIR=$(find . -maxdepth 1 -type d -name "ffmpeg-*-static" | head -n 1)
    
    if [ -z "$FFMPEG_DIR" ]; then
        print_error "Erreur lors de l'extraction"
        cd "$CURRENT_DIR"  # Restaurer le répertoire
        return 1
    fi
    
    # Restaurer le répertoire courant AVANT de vérifier
    cd "$CURRENT_DIR"
    
    if [ -f "$INSTALL_DIR/$FFMPEG_DIR/ffmpeg" ]; then
        FFMPEG_VERSION=$("$INSTALL_DIR/$FFMPEG_DIR/ffmpeg" -version 2>&1 | head -n1 | awk '{print $3}')
        print_success "FFmpeg $FFMPEG_VERSION installé localement"
        print_info "Emplacement: $INSTALL_DIR/$FFMPEG_DIR"
        return 0
    else
        print_error "FFmpeg non trouvé après extraction"
        return 1
    fi
}

# Vérifier si FFmpeg est déjà installé
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1 | awk '{print $3}')
    print_success "FFmpeg $FFMPEG_VERSION détecté (système)"
else
    print_warning "FFmpeg n'est pas installé"
    echo ""
    
    # Détecter l'OS
    OS="unknown"
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
    fi
    
    print_info "OS détecté: $OS"
    echo ""
    
    # Proposer les options d'installation
    echo -e "${CYAN}Options d'installation FFmpeg:${NC}"
    echo "  1. Installation système (avec sudo) - Recommandé"
    echo "  2. Installation locale (sans sudo) - Pour école/entreprise"
    echo "  3. Ignorer (installer manuellement plus tard)"
    echo ""
    read -p "Choisissez une option (1/2/3): " -n 1 -r FFMPEG_CHOICE
    echo ""
    echo ""
    
    case $FFMPEG_CHOICE in
        1)
            print_step "Installation système de FFmpeg..."
            
            if [ "$OS" = "linux" ]; then
                # Détecter la distribution
                if [ -f /etc/debian_version ]; then
                    sudo apt update && sudo apt install -y ffmpeg
                elif [ -f /etc/redhat-release ]; then
                    sudo yum install -y ffmpeg || sudo dnf install -y ffmpeg
                elif [ -f /etc/arch-release ]; then
                    sudo pacman -S --noconfirm ffmpeg
                else
                    print_warning "Distribution non reconnue"
                    sudo apt install -y ffmpeg || print_error "Installation échouée"
                fi
            elif [ "$OS" = "macos" ]; then
                if command -v brew &> /dev/null; then
                    brew install ffmpeg
                else
                    print_error "Homebrew non installé. Installez-le depuis: https://brew.sh"
                    exit 1
                fi
            else
                print_error "OS non supporté pour l'installation automatique"
                exit 1
            fi
            
            # Vérifier l'installation
            if command -v ffmpeg &> /dev/null; then
                FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1 | awk '{print $3}')
                print_success "FFmpeg $FFMPEG_VERSION installé"
            else
                print_error "Installation échouée"
                exit 1
            fi
            ;;
        2)
            install_ffmpeg_local
            if [ $? -ne 0 ]; then
                print_error "Installation locale échouée"
                exit 1
            fi
            ;;
        3)
            print_warning "FFmpeg non installé"
            print_info "La conversion MP3 ne fonctionnera pas"
            print_info "Installez FFmpeg manuellement:"
            echo "  - Linux: sudo apt install ffmpeg"
            echo "  - macOS: brew install ffmpeg"
            echo "  - Ou relancez ce script plus tard"
            echo ""
            ;;
        *)
            print_error "Option invalide"
            exit 1
            ;;
    esac
fi

# ============================================
# 3. Créer l'environnement virtuel
# ============================================

print_step "Création de l'environnement virtuel..."

if [ -d "venv" ]; then
    print_info "Environnement virtuel existant détecté"
    print_step "Suppression et recréation..."
    rm -rf venv
fi

python3 -m venv venv
print_success "Environnement virtuel créé"

# ============================================
# 4. Activer l'environnement virtuel
# ============================================

print_step "Activation de l'environnement virtuel..."


source venv/Scripts/activate
if [ -z "$VIRTUAL_ENV" ]; then
    print_error "Impossible d'activer l'environnement virtuel"
    exit 1
fi

print_success "Environnement virtuel activé"

# ============================================
# 5. Mettre à jour pip
# ============================================

print_step "Mise à jour de pip..."

# Utiliser python -m pip pour éviter les conflits (surtout sur Windows)
python -m pip install --upgrade pip --quiet 2>&1 | grep -v "^\[notice\]" || true

# Attendre un peu pour que pip soit bien mis à jour
sleep 1

PIP_VERSION=$(pip --version | awk '{print $2}')
print_success "pip $PIP_VERSION"

# ============================================
# 6. Installer les dépendances
# ============================================

print_step "Installation des dépendances..."

# Vérifier que requirements.txt existe dans le répertoire courant
if [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
    print_error "Le fichier requirements.txt est introuvable dans $SCRIPT_DIR"
    print_info "Contenu du répertoire:"
    ls -la "$SCRIPT_DIR"
    exit 1
fi

echo ""
print_info "Dépendances à installer:"
cat "$SCRIPT_DIR/requirements.txt" | grep -v '^#' | grep -v '^$' | sed 's/^/  - /'
echo ""

pip install -r "$SCRIPT_DIR/requirements.txt"

print_success "Dépendances installées"

# ============================================
# 7. Vérifier les installations
# ============================================

print_step "Vérification des installations..."

echo ""
print_info "Packages installés:"
pip list | grep -E "(flask|yt-dlp|mutagen|Pillow)" | sed 's/^/  /'
echo ""

# ============================================
# 8. Créer les dossiers nécessaires
# ============================================

print_step "Création des dossiers..."

cd "$SCRIPT_DIR/.."

mkdir -p temp
mkdir -p music

print_success "Dossiers créés (temp/, music/)"

# ============================================
# 9. Test du serveur
# ============================================

print_step "Test de l'importation des modules..."

cd "$SCRIPT_DIR"

python3 << EOF
try:
    import flask
    import yt_dlp
    import mutagen
    from PIL import Image
    print("✅ Tous les modules sont importables")
except ImportError as e:
    print(f"❌ Erreur d'importation: {e}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    print_success "Tous les modules fonctionnent"
else
    print_error "Certains modules ne fonctionnent pas"
    exit 1
fi

# ============================================
# INSTALLATION TERMINÉE
# ============================================

echo ""
print_header "✅ Installation terminée avec succès !"

echo ""
print_info "🚀 Pour démarrer SongSurf:"
echo -e "  ${GREEN}./start.sh${NC}"
echo ""

print_info "📱 Ensuite:"
echo "  1. Installez l'extension Chrome"
echo "  2. Allez sur YouTube Music"
echo "  3. Cliquez sur le widget SongSurf"
echo "  4. Téléchargez vos musiques !"
echo ""

print_info "🌐 Dashboard:"
echo "  http://localhost:8080"
echo ""

print_success "Installation terminée ! Prêt à télécharger de la musique ! 🎵"
echo ""
