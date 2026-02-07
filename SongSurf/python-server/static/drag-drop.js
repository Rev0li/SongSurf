/**
 * drag-drop.js - Drag & Drop pour déplacer les chansons
 */

let draggedSong = null;

// Initialiser le drag & drop après le rendu de l'arbre
function initDragAndDrop() {
    console.log('🎯 Initialisation du Drag & Drop');
    
    // Rendre toutes les chansons draggables
    document.querySelectorAll('.song-line[draggable="true"]').forEach(songEl => {
        songEl.addEventListener('dragstart', handleDragStart);
        songEl.addEventListener('dragend', handleDragEnd);
        
        // Double-click pour renommer
        songEl.addEventListener('dblclick', handleRename);
    });
    
    // Rendre tous les albums droppable (ligne + zone complète)
    document.querySelectorAll('.tree-item').forEach(treeItem => {
        const albumLine = treeItem.querySelector('.album-line');
        if (albumLine) {
            // Toute la zone de l'album est droppable
            treeItem.addEventListener('dragover', handleDragOver);
            treeItem.addEventListener('dragleave', handleDragLeave);
            treeItem.addEventListener('drop', handleDrop);
            
            // Stocker les données de l'album sur le conteneur
            treeItem.dataset.artist = albumLine.dataset.artist;
            treeItem.dataset.album = albumLine.dataset.album;
        }
    });
}

function handleDragStart(e) {
    draggedSong = {
        path: e.currentTarget.dataset.songPath,
        title: e.currentTarget.dataset.songTitle
    };
    
    e.currentTarget.style.opacity = '0.4';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', e.currentTarget.innerHTML);
    
    console.log('🎵 Drag start:', draggedSong.title);
}

function handleDragEnd(e) {
    e.currentTarget.style.opacity = '1';
    
    // Nettoyer toutes les classes drag-over
    document.querySelectorAll('.drag-over').forEach(el => {
        el.classList.remove('drag-over');
    });
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    
    e.stopPropagation(); // Empêcher la propagation
    e.dataTransfer.dropEffect = 'move';
    
    // Ajouter la classe drag-over à toute la zone de l'album
    const dropZone = e.currentTarget;
    if (!dropZone.classList.contains('drag-over')) {
        dropZone.classList.add('drag-over');
    }
    
    return false;
}

function handleDragLeave(e) {
    // Ne retirer la classe que si on quitte vraiment la zone (pas juste un enfant)
    const dropZone = e.currentTarget;
    const rect = dropZone.getBoundingClientRect();
    
    if (
        e.clientX < rect.left ||
        e.clientX >= rect.right ||
        e.clientY < rect.top ||
        e.clientY >= rect.bottom
    ) {
        dropZone.classList.remove('drag-over');
    }
}

async function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }
    
    e.preventDefault();
    
    // Récupérer l'album cible
    const targetArtist = e.currentTarget.dataset.artist;
    const targetAlbum = e.currentTarget.dataset.album;
    
    if (!draggedSong || !targetArtist || !targetAlbum) {
        console.error('❌ Données manquantes');
        return false;
    }
    
    // Vérifier si c'est le même dossier (illogique)
    const sourcePath = draggedSong.path;
    const targetPath = `${targetArtist}/${targetAlbum}/`;
    
    if (sourcePath.startsWith(targetPath)) {
        console.log('⚠️ Impossible de déplacer dans le même dossier');
        showNotification('⚠️ La chanson est déjà dans cet album', 'warning');
        handleDragLeave(e);
        return false;
    }
    
    console.log(`📦 Drop: ${draggedSong.title} → ${targetArtist}/${targetAlbum}`);
    
    // Confirmation avec popup personnalisée
    const confirmed = await showConfirmDialog(
        e.clientX, 
        e.clientY,
        `Déplacer "${draggedSong.title}" vers:`,
        `${targetArtist} / ${targetAlbum}`
    );
    
    if (!confirmed) {
        handleDragLeave(e);
        return false;
    }
    
    try {
        // Appeler l'API pour déplacer le fichier
        const response = await fetch(`${API_BASE}/api/move-song`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                song_path: draggedSong.path,
                target_artist: targetArtist,
                target_album: targetAlbum
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            console.log(`✅ "${draggedSong.title}" déplacé avec succès !`);
            console.log('🗑️ Dossiers vides supprimés automatiquement');
            
            // Recharger la bibliothèque
            await loadLibrary();
        } else {
            console.error(`❌ Erreur: ${result.error}`);
            // Afficher l'erreur à l'utilisateur
            showNotification(`❌ Erreur: ${result.error}`, 'error');
        }
        
    } catch (error) {
        console.error('❌ Erreur:', error);
        showNotification('❌ Erreur lors du déplacement', 'error');
    }
    
    // Nettoyer la classe drag-over
    e.currentTarget.classList.remove('drag-over');
    
    return false;
}

// Renommer une chanson (double-click)
async function handleRename(e) {
    e.stopPropagation();
    
    const songPath = e.currentTarget.dataset.songPath;
    const currentTitle = e.currentTarget.dataset.songTitle;
    
    // Popup de renommage
    const newTitle = await showRenameDialog(e.clientX, e.clientY, currentTitle);
    
    if (!newTitle || newTitle === currentTitle) {
        return;
    }
    
    console.log(`✏️ Rename: "${currentTitle}" → "${newTitle}"`);
    
    // Appeler l'API pour renommer
    renameSong(songPath, newTitle);
}

async function renameSong(songPath, newTitle) {
    try {
        const response = await fetch(`${API_BASE}/api/rename-song`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                song_path: songPath,
                new_title: newTitle
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            console.log(`✅ Chanson renommée: "${newTitle}"`);
            
            // Recharger la bibliothèque
            await loadLibrary();
        } else {
            console.error(`❌ Erreur: ${result.error}`);
            showNotification(`❌ ${result.error}`, 'error');
        }
        
    } catch (error) {
        console.error('❌ Erreur:', error);
        showNotification('❌ Erreur lors du renommage', 'error');
    }
}

// Popup de confirmation personnalisée
function showConfirmDialog(x, y, title, subtitle) {
    return new Promise((resolve) => {
        // Créer l'overlay
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 10000;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.2s ease;
        `;
        
        // Créer la popup
        const dialog = document.createElement('div');
        dialog.style.cssText = `
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 16px;
            padding: 24px;
            min-width: 400px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        `;
        
        dialog.innerHTML = `
            <div style="margin-bottom: 20px;">
                <div style="font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 8px;">
                    ${title}
                </div>
                <div style="font-size: 14px; color: #a0a0a0;">
                    ${subtitle}
                </div>
            </div>
            <div style="display: flex; gap: 12px; justify-content: flex-end;">
                <button id="cancel-btn" style="
                    padding: 10px 20px;
                    background: #2a2a2a;
                    border: 1px solid #444;
                    border-radius: 8px;
                    color: #fff;
                    font-size: 14px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s;
                ">Annuler</button>
                <button id="confirm-btn" style="
                    padding: 10px 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border: none;
                    border-radius: 8px;
                    color: white;
                    font-size: 14px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                ">Confirmer</button>
            </div>
        `;
        
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
        
        // Ajouter les animations CSS
        const style = document.createElement('style');
        style.textContent = `
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes slideUp {
                from { transform: translateY(20px); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
        
        // Event listeners
        const confirmBtn = dialog.querySelector('#confirm-btn');
        const cancelBtn = dialog.querySelector('#cancel-btn');
        
        confirmBtn.addEventListener('mouseenter', () => {
            confirmBtn.style.transform = 'translateY(-2px)';
            confirmBtn.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.4)';
        });
        confirmBtn.addEventListener('mouseleave', () => {
            confirmBtn.style.transform = 'translateY(0)';
            confirmBtn.style.boxShadow = 'none';
        });
        
        cancelBtn.addEventListener('mouseenter', () => {
            cancelBtn.style.background = '#333';
        });
        cancelBtn.addEventListener('mouseleave', () => {
            cancelBtn.style.background = '#2a2a2a';
        });
        
        confirmBtn.addEventListener('click', () => {
            overlay.remove();
            style.remove();
            resolve(true);
        });
        
        cancelBtn.addEventListener('click', () => {
            overlay.remove();
            style.remove();
            resolve(false);
        });
        
        // ESC pour annuler
        const handleEsc = (e) => {
            if (e.key === 'Escape') {
                overlay.remove();
                style.remove();
                resolve(false);
                document.removeEventListener('keydown', handleEsc);
            }
        };
        document.addEventListener('keydown', handleEsc);
    });
}

// Popup de renommage
function showRenameDialog(x, y, currentTitle) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 10000;
            display: flex;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.2s ease;
        `;
        
        const dialog = document.createElement('div');
        dialog.style.cssText = `
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 16px;
            padding: 24px;
            min-width: 400px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        `;
        
        dialog.innerHTML = `
            <div style="margin-bottom: 20px;">
                <div style="font-size: 18px; font-weight: 600; color: #fff; margin-bottom: 8px;">
                    ✏️ Renommer la chanson
                </div>
                <input type="text" id="rename-input" value="${currentTitle}" style="
                    width: 100%;
                    padding: 12px;
                    background: #2a2a2a;
                    border: 1px solid #444;
                    border-radius: 8px;
                    color: #fff;
                    font-size: 14px;
                    margin-top: 12px;
                ">
            </div>
            <div style="display: flex; gap: 12px; justify-content: flex-end;">
                <button id="cancel-btn" style="
                    padding: 10px 20px;
                    background: #2a2a2a;
                    border: 1px solid #444;
                    border-radius: 8px;
                    color: #fff;
                    font-size: 14px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s;
                ">Annuler</button>
                <button id="confirm-btn" style="
                    padding: 10px 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border: none;
                    border-radius: 8px;
                    color: white;
                    font-size: 14px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                ">Renommer</button>
            </div>
        `;
        
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
        
        const input = dialog.querySelector('#rename-input');
        const confirmBtn = dialog.querySelector('#confirm-btn');
        const cancelBtn = dialog.querySelector('#cancel-btn');
        
        // Focus et sélection
        setTimeout(() => {
            input.focus();
            input.select();
        }, 100);
        
        // Enter pour confirmer
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                overlay.remove();
                resolve(input.value.trim());
            }
        });
        
        confirmBtn.addEventListener('click', () => {
            overlay.remove();
            resolve(input.value.trim());
        });
        
        cancelBtn.addEventListener('click', () => {
            overlay.remove();
            resolve(null);
        });
        
        // ESC pour annuler
        const handleEsc = (e) => {
            if (e.key === 'Escape') {
                overlay.remove();
                resolve(null);
                document.removeEventListener('keydown', handleEsc);
            }
        };
        document.addEventListener('keydown', handleEsc);
    });
}

// Notification discrète (pour les erreurs/warnings)
function showNotification(message, type = 'info') {
    const colors = {
        'error': '#ff3b30',
        'warning': '#ff9500',
        'success': '#34c759',
        'info': '#007aff'
    };
    
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${colors[type] || colors.info};
        color: white;
        padding: 16px 24px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        z-index: 10000;
        font-size: 14px;
        font-weight: 600;
        animation: slideInRight 0.3s ease-out;
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Supprimer après 3 secondes
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Exporter pour utilisation dans dashboard.js
window.initDragAndDrop = initDragAndDrop;
