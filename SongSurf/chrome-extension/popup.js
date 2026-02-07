/**
 * popup.js - Popup de l'extension GrabSong V3
 */

const PYTHON_SERVER = 'http://localhost:5000';

// Vérifier le statut du serveur
async function checkServerStatus() {
  const indicator = document.getElementById('server-indicator');
  const status = document.getElementById('server-status');
  
  try {
    const response = await fetch(`${PYTHON_SERVER}/ping`);
    
    if (response.ok) {
      indicator.classList.add('online');
      indicator.classList.remove('offline');
      status.textContent = 'En ligne';
    } else {
      throw new Error('Server error');
    }
  } catch (error) {
    indicator.classList.add('offline');
    indicator.classList.remove('online');
    status.textContent = 'Hors ligne';
  }
}

// Vérifier au chargement
checkServerStatus();

// Vérifier toutes les 5 secondes
setInterval(checkServerStatus, 5000);
