#!/bin/bash
# ============================================
# 🎵 SongSurf - Démarrage Automatique
# ============================================
# 
# Ce script démarre automatiquement :
#   ✅ Environnement virtuel Python
#   ✅ Serveur Flask (port 8080)
#   ✅ Dashboard web
#
# Usage: ./start.sh
# ============================================

# Couleurs
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# ============================================
# 1. Vérifier l'environnement virtuel
# ============================================

if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Environnement virtuel manquant${NC}"
    echo -e "${CYAN}ℹ️  Installation automatique...${NC}"
    echo ""
    ./install.sh
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Installation échouée${NC}"
        exit 1
    fi
    echo ""
    echo -e "${GREEN}✅ Installation terminée ! Démarrage...${NC}"
    echo ""
fi

# ============================================
# 2. Activer l'environnement virtuel
# ============================================

echo -e "${CYAN}▶ Activation de l'environnement virtuel...${NC}"
source venv/Scripts/activate

if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${RED}❌ Impossible d'activer l'environnement virtuel${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Environnement virtuel activé${NC}"

# ============================================
# 3. Configurer FFmpeg
# ============================================

echo -e "${CYAN}▶ Configuration de FFmpeg...${NC}"

FFMPEG_LOCAL_DIR="$HOME/.local/ffmpeg"

# Vérifier FFmpeg système
if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1 | awk '{print $3}')
    echo -e "${GREEN}✅ FFmpeg $FFMPEG_VERSION${NC}"
# Vérifier FFmpeg local
elif [ -d "$FFMPEG_LOCAL_DIR" ]; then
    FFMPEG_STATIC=$(find "$FFMPEG_LOCAL_DIR" -name "ffmpeg-*-static" -type d 2>/dev/null | head -n 1)
    
    if [ -n "$FFMPEG_STATIC" ] && [ -f "$FFMPEG_STATIC/ffmpeg" ]; then
        export PATH="$FFMPEG_STATIC:$PATH"
        FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1 | awk '{print $3}')
        echo -e "${GREEN}✅ FFmpeg $FFMPEG_VERSION (local)${NC}"
    else
        echo -e "${YELLOW}⚠️  FFmpeg non trouvé - Installation requise${NC}"
        echo -e "${CYAN}ℹ️  Exécutez: sudo apt install ffmpeg${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  FFmpeg non trouvé - Installation requise${NC}"
    echo -e "${CYAN}ℹ️  Exécutez: sudo apt install ffmpeg${NC}"
fi

# ============================================
# 4. Vérifier les dépendances Python
# ============================================

echo -e "${CYAN}▶ Vérification des dépendances...${NC}"

python3 << EOF
import sys
try:
    import flask
    import yt_dlp
    import mutagen
    from PIL import Image
    print("✅ Tous les modules Python sont disponibles")
except ImportError as e:
    print(f"❌ Module manquant: {e}")
    print("ℹ️  Exécutez './install.sh' pour installer les dépendances")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    deactivate
    exit 1
fi

# ============================================
# 5. Créer les dossiers nécessaires
# ============================================

cd ..
mkdir -p temp music
cd python-server

# ============================================
# 6. Afficher la bannière
# ============================================

clear
echo ""
echo -e "${PURPLE}============================================${NC}"
echo -e "${PURPLE}🎵 SongSurf - Serveur de Téléchargement${NC}"
echo -e "${PURPLE}============================================${NC}"
echo ""

# ============================================
# 7. Afficher les informations
# ============================================

echo -e "${GREEN}✅ Serveur prêt !${NC}"
echo ""
echo -e "${CYAN}🌐 Dashboard :${NC}"
echo -e "  ${GREEN}http://localhost:8080${NC}"
echo ""
echo -e "${CYAN}📱 Extension Chrome :${NC}"
echo "  1. Installez l'extension depuis chrome-extension/"
echo "  2. Allez sur YouTube Music"
echo "  3. Cliquez sur le widget SongSurf"
echo ""
echo -e "${CYAN}⏹️  Pour arrêter :${NC}"
echo "  Ctrl+C"
echo ""
echo -e "${PURPLE}============================================${NC}"
echo ""

# ============================================
# 8. Démarrer le serveur
# ============================================

echo -e "${CYAN}▶ Démarrage du serveur...${NC}"
echo ""

# Piège pour nettoyer à la sortie
trap 'echo -e "\n${YELLOW}⚠️  Arrêt du serveur...${NC}"; deactivate; exit 0' INT TERM

python app.py

# Désactiver l'environnement virtuel à la sortie
deactivate