/* ExpenSOS static/script.js — global helpers */

// Keyboard: Escape closes any open modal
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        const modal = document.querySelector('[id$="Modal"][style*="flex"]');
        if (modal) modal.style.display = 'none';
    }
});
