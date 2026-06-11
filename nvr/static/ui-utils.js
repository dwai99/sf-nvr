/**
 * SF-NVR UI Utilities
 * Common UI components and helpers
 */

/**
 * Tooltip System
 * Automatically adds tooltips to elements with data-tooltip attribute
 */
function initTooltips() {
    // Create tooltip element
    let tooltip = document.getElementById('ui-tooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = 'ui-tooltip';
        tooltip.style.cssText = `
            position: fixed;
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
            z-index: 10001;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s;
            max-width: 300px;
            line-height: 1.4;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        `;
        document.body.appendChild(tooltip);
    }

    // Add event listeners to all elements with data-tooltip
    document.querySelectorAll('[data-tooltip]').forEach(element => {
        if (element.hasAttribute('data-tooltip-initialized')) return;
        element.setAttribute('data-tooltip-initialized', 'true');

        element.addEventListener('mouseenter', (e) => {
            const text = element.getAttribute('data-tooltip');
            if (!text) return;

            tooltip.textContent = text;
            tooltip.style.opacity = '1';

            // Position tooltip
            positionTooltip(tooltip, element);
        });

        element.addEventListener('mouseleave', () => {
            tooltip.style.opacity = '0';
        });

        element.addEventListener('mousemove', (e) => {
            if (tooltip.style.opacity === '1') {
                positionTooltip(tooltip, element, e);
            }
        });
    });
}

/**
 * Position tooltip near element
 */
function positionTooltip(tooltip, element, mouseEvent = null) {
    const rect = element.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();

    let top, left;

    if (mouseEvent) {
        // Follow mouse
        left = mouseEvent.clientX + 10;
        top = mouseEvent.clientY + 10;
    } else {
        // Position below element
        left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
        top = rect.bottom + 10;
    }

    // Keep tooltip on screen
    if (left + tooltipRect.width > window.innerWidth) {
        left = window.innerWidth - tooltipRect.width - 10;
    }
    if (left < 10) {
        left = 10;
    }
    if (top + tooltipRect.height > window.innerHeight) {
        top = rect.top - tooltipRect.height - 10;
    }

    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
}

/**
 * Keyboard Shortcuts Manager
 */
class KeyboardShortcuts {
    constructor() {
        this.shortcuts = new Map();
        this.enabled = true;
        this.init();
    }

    init() {
        document.addEventListener('keydown', (e) => {
            if (!this.enabled) return;

            // Don't trigger shortcuts when typing in inputs
            if (e.target.matches('input, textarea, select')) return;

            const key = this.getKeyCombo(e);
            const handler = this.shortcuts.get(key);

            if (handler) {
                e.preventDefault();
                handler(e);
            }
        });
    }

    getKeyCombo(e) {
        const parts = [];
        if (e.ctrlKey) parts.push('ctrl');
        if (e.altKey) parts.push('alt');
        if (e.shiftKey) parts.push('shift');
        if (e.metaKey) parts.push('meta');
        parts.push(e.key.toLowerCase());
        return parts.join('+');
    }

    register(key, description, handler) {
        this.shortcuts.set(key.toLowerCase(), handler);
        // Store description for help dialog
        if (!this.descriptions) this.descriptions = new Map();
        this.descriptions.set(key.toLowerCase(), description);
    }

    unregister(key) {
        this.shortcuts.delete(key.toLowerCase());
        if (this.descriptions) {
            this.descriptions.delete(key.toLowerCase());
        }
    }

    disable() {
        this.enabled = false;
    }

    enable() {
        this.enabled = true;
    }

    showHelp() {
        if (!this.descriptions || this.descriptions.size === 0) return;

        const shortcuts = Array.from(this.descriptions.entries());
        const html = `
            <div style="max-height: 500px; overflow-y: auto;">
                <h3 style="margin-bottom: 20px; color: #4a9eff;">Keyboard Shortcuts</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    ${shortcuts.map(([key, desc]) => `
                        <tr style="border-bottom: 1px solid #333;">
                            <td style="padding: 12px; font-family: monospace; color: #4a9eff;">
                                ${this.formatKey(key)}
                            </td>
                            <td style="padding: 12px; color: #e0e0e0;">
                                ${desc}
                            </td>
                        </tr>
                    `).join('')}
                </table>
            </div>
        `;

        showModal('Keyboard Shortcuts', html);
    }

    formatKey(key) {
        return key
            .split('+')
            .map(k => k.charAt(0).toUpperCase() + k.slice(1))
            .join(' + ');
    }
}

// Global shortcuts instance
const shortcuts = new KeyboardShortcuts();

// Register ? key to show help
shortcuts.register('?', 'Show keyboard shortcuts', () => {
    shortcuts.showHelp();
});

/**
 * Modal Dialog System
 */
function showModal(title, content, options = {}) {
    // Remove existing modal
    hideModal();

    const modal = document.createElement('div');
    modal.id = 'ui-modal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.8);
        z-index: 10002;
        display: flex;
        align-items: center;
        justify-content: center;
        animation: fadeIn 0.2s ease-out;
    `;

    const dialog = document.createElement('div');
    dialog.style.cssText = `
        background: #2a2a2a;
        border-radius: 12px;
        max-width: ${options.maxWidth || '600px'};
        max-height: 80vh;
        width: 90%;
        box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        animation: slideUp 0.3s ease-out;
    `;

    const header = document.createElement('div');
    header.style.cssText = `
        padding: 20px;
        border-bottom: 1px solid #333;
        display: flex;
        justify-content: space-between;
        align-items: center;
    `;

    const titleEl = document.createElement('h2');
    titleEl.textContent = title;
    titleEl.style.cssText = 'color: #4a9eff; margin: 0;';

    const closeBtn = document.createElement('button');
    closeBtn.textContent = '×';
    closeBtn.style.cssText = `
        background: none;
        border: none;
        color: #888;
        font-size: 32px;
        cursor: pointer;
        padding: 0;
        width: 32px;
        height: 32px;
        line-height: 1;
    `;
    closeBtn.onclick = hideModal;

    header.appendChild(titleEl);
    header.appendChild(closeBtn);

    const body = document.createElement('div');
    body.style.cssText = `
        padding: 20px;
        color: #e0e0e0;
        overflow-y: auto;
        max-height: calc(80vh - 140px);
    `;
    body.innerHTML = content;

    const footer = document.createElement('div');
    footer.style.cssText = `
        padding: 20px;
        border-top: 1px solid #333;
        text-align: right;
    `;

    if (options.buttons) {
        options.buttons.forEach(btn => {
            const button = document.createElement('button');
            button.textContent = btn.text;
            button.className = `btn ${btn.primary ? 'btn-primary' : 'btn-secondary'}`;
            button.onclick = () => {
                if (btn.onClick) btn.onClick();
                if (btn.closeOnClick !== false) hideModal();
            };
            footer.appendChild(button);
        });
    } else {
        const closeButton = document.createElement('button');
        closeButton.textContent = 'Close';
        closeButton.className = 'btn btn-primary';
        closeButton.onclick = hideModal;
        footer.appendChild(closeButton);
    }

    dialog.appendChild(header);
    dialog.appendChild(body);
    dialog.appendChild(footer);
    modal.appendChild(dialog);

    // Close on background click
    modal.onclick = (e) => {
        if (e.target === modal) hideModal();
    };

    // Close on Escape key
    const escHandler = (e) => {
        if (e.key === 'Escape') {
            hideModal();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);

    document.body.appendChild(modal);
}

function hideModal() {
    const modal = document.getElementById('ui-modal');
    if (modal) {
        modal.remove();
    }
}

/**
 * Format duration in seconds to human-readable time
 */
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

/**
 * Debounce function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Add CSS animations
if (!document.getElementById('ui-utils-styles')) {
    const style = document.createElement('style');
    style.id = 'ui-utils-styles';
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        @keyframes slideUp {
            from {
                transform: translateY(50px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .btn {
            padding: 0.6rem 1.2rem;
            border: none;
            border-radius: 6px;
            font-size: 0.95em;
            cursor: pointer;
            transition: all 0.2s;
            font-weight: 500;
            margin-left: 8px;
        }

        .btn-primary {
            background: #4a9eff;
            color: white;
        }

        .btn-primary:hover {
            background: #3a8eef;
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: #333;
            color: #e0e0e0;
        }

        .btn-secondary:hover {
            background: #444;
        }
    `;
    document.head.appendChild(style);
}

// Auto-initialize tooltips when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTooltips);
} else {
    initTooltips();
}

// Re-initialize tooltips periodically for dynamically added elements
setInterval(initTooltips, 2000);
