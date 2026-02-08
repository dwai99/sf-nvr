/**
 * SF-NVR Toast Notification System
 *
 * Usage:
 *   showNotification('Message', 'success');
 *   showNotification('Error occurred', 'error');
 *   showNotification('Processing...', 'info');
 *   showNotification('Warning!', 'warning');
 */

// Initialize notification container
function initNotifications() {
    if (document.getElementById('notification-container')) {
        return; // Already initialized
    }

    const container = document.createElement('div');
    container.id = 'notification-container';
    container.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        gap: 10px;
        max-width: 400px;
        pointer-events: none;
    `;
    document.body.appendChild(container);
}

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - Type: 'success', 'error', 'warning', 'info'
 * @param {number} duration - Duration in milliseconds (0 = permanent)
 */
function showNotification(message, type = 'info', duration = 4000) {
    initNotifications();

    const container = document.getElementById('notification-container');
    const notification = document.createElement('div');

    // Type-specific styling
    const styles = {
        success: {
            bg: '#2ecc71',
            icon: '✓',
            border: '#27ae60'
        },
        error: {
            bg: '#e74c3c',
            icon: '✕',
            border: '#c0392b'
        },
        warning: {
            bg: '#f39c12',
            icon: '⚠',
            border: '#d68910'
        },
        info: {
            bg: '#4a9eff',
            icon: 'ℹ',
            border: '#3a8eef'
        }
    };

    const style = styles[type] || styles.info;

    notification.className = 'toast-notification';
    notification.style.cssText = `
        background: ${style.bg};
        color: white;
        padding: 16px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 300px;
        animation: slideIn 0.3s ease-out;
        cursor: pointer;
        border-left: 4px solid ${style.border};
        font-size: 14px;
        line-height: 1.4;
        pointer-events: auto;
    `;

    notification.innerHTML = `
        <span style="font-size: 20px; font-weight: bold;">${style.icon}</span>
        <span style="flex: 1;">${escapeHtml(message)}</span>
        <span style="font-size: 18px; opacity: 0.8;">×</span>
    `;

    // Close on click
    notification.onclick = () => removeNotification(notification);

    container.appendChild(notification);

    // Auto-remove after duration
    if (duration > 0) {
        setTimeout(() => removeNotification(notification), duration);
    }

    return notification;
}

/**
 * Remove a notification with animation
 */
function removeNotification(notification) {
    notification.style.animation = 'slideOut 0.3s ease-out';
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 300);
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show a loading notification (with spinner)
 * Returns an object with dismiss() method
 */
function showLoading(message = 'Loading...') {
    initNotifications();

    const container = document.getElementById('notification-container');
    const notification = document.createElement('div');

    notification.className = 'toast-notification loading';
    notification.style.cssText = `
        background: #34495e;
        color: white;
        padding: 16px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 300px;
        animation: slideIn 0.3s ease-out;
        border-left: 4px solid #4a9eff;
        pointer-events: auto;
    `;

    notification.innerHTML = `
        <div class="spinner" style="
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        "></div>
        <span style="flex: 1;">${escapeHtml(message)}</span>
    `;

    container.appendChild(notification);

    return {
        dismiss: () => removeNotification(notification),
        update: (newMessage) => {
            const span = notification.querySelector('span');
            if (span) span.textContent = newMessage;
        }
    };
}

// Add CSS animations
if (!document.getElementById('notification-styles')) {
    const style = document.createElement('style');
    style.id = 'notification-styles';
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(400px);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(400px);
                opacity: 0;
            }
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .toast-notification:hover {
            opacity: 0.95;
        }
    `;
    document.head.appendChild(style);
}

// Initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNotifications);
} else {
    initNotifications();
}
