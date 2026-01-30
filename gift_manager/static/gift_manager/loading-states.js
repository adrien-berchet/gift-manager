/**
 * Loading States and Performance Feedback
 * Comprehensive loading indicators for all AJAX operations
 * Requirements: 8.1, 8.2, 8.3
 */

(function(window) {
    'use strict';

    // =========================================================================
    // Configuration
    // =========================================================================

    const config = {
        minLoadingDuration: 300, // Minimum time to show loading state
        skeletonCount: 3,        // Default number of skeleton items
        loadingText: {
            default: 'Loading...',
            saving: 'Saving...',
            deleting: 'Deleting...',
            submitting: 'Submitting...',
            processing: 'Processing...'
        }
    };

    // =========================================================================
    // Skeleton Screen Components
    // =========================================================================

    const skeletonTemplates = {
        listItem: `
            <div class="skeleton-list-item">
                <div class="skeleton skeleton-avatar"></div>
                <div class="skeleton-content">
                    <div class="skeleton skeleton-text"></div>
                    <div class="skeleton skeleton-text short"></div>
                </div>
                <div class="skeleton skeleton-actions">
                    <div class="skeleton skeleton-button"></div>
                    <div class="skeleton skeleton-button"></div>
                </div>
            </div>
        `,

        card: `
            <div class="skeleton-card">
                <div class="skeleton skeleton-header"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text medium"></div>
                <div class="skeleton skeleton-text short"></div>
                <div class="skeleton skeleton-footer">
                    <div class="skeleton skeleton-button"></div>
                    <div class="skeleton skeleton-button"></div>
                </div>
            </div>
        `,

        tableRow: `
            <tr class="skeleton-table-row">
                <td><div class="skeleton skeleton-cell"></div></td>
                <td><div class="skeleton skeleton-cell"></div></td>
                <td><div class="skeleton skeleton-cell short"></div></td>
                <td><div class="skeleton skeleton-cell"></div></td>
                <td><div class="skeleton skeleton-actions">
                    <div class="skeleton skeleton-button small"></div>
                    <div class="skeleton skeleton-button small"></div>
                </div></td>
            </tr>
        `,

        form: `
            <div class="skeleton-form">
                <div class="skeleton-form-group">
                    <div class="skeleton skeleton-label"></div>
                    <div class="skeleton skeleton-input"></div>
                </div>
                <div class="skeleton-form-group">
                    <div class="skeleton skeleton-label"></div>
                    <div class="skeleton skeleton-input"></div>
                </div>
                <div class="skeleton-form-group">
                    <div class="skeleton skeleton-label"></div>
                    <div class="skeleton skeleton-textarea"></div>
                </div>
                <div class="skeleton-form-actions">
                    <div class="skeleton skeleton-button"></div>
                    <div class="skeleton skeleton-button"></div>
                </div>
            </div>
        `,

        detail: `
            <div class="skeleton-detail">
                <div class="skeleton skeleton-title"></div>
                <div class="skeleton-detail-section">
                    <div class="skeleton skeleton-subtitle"></div>
                    <div class="skeleton skeleton-text"></div>
                    <div class="skeleton skeleton-text medium"></div>
                </div>
                <div class="skeleton-detail-section">
                    <div class="skeleton skeleton-subtitle"></div>
                    <div class="skeleton skeleton-text"></div>
                    <div class="skeleton skeleton-text short"></div>
                </div>
            </div>
        `
    };

    // =========================================================================
    // Loading State Management
    // =========================================================================

    class LoadingStateManager {
        constructor() {
            this.activeLoadings = new Map();
            this.init();
        }

        init() {
            this.setupHTMXIntegration();
            this.setupFormLoadingStates();
            this.setupButtonLoadingStates();
        }

        // HTMX Integration for automatic loading states
        setupHTMXIntegration() {
            // Before HTMX request
            document.body.addEventListener('htmx:beforeRequest', (e) => {
                const element = e.detail.elt;
                const target = e.detail.target;

                // Show loading state on the target element
                if (target && target !== element) {
                    this.showContentLoading(target);
                }

                // Show button loading state if triggered by button
                if (element.tagName === 'BUTTON' || element.tagName === 'A') {
                    this.showButtonLoading(element);
                }
            });

            // After HTMX request
            document.body.addEventListener('htmx:afterRequest', (e) => {
                const element = e.detail.elt;
                const target = e.detail.target;

                // Hide loading states
                if (target && target !== element) {
                    this.hideContentLoading(target);
                }

                if (element.tagName === 'BUTTON' || element.tagName === 'A') {
                    this.hideButtonLoading(element);
                }
            });

            // Handle HTMX errors
            document.body.addEventListener('htmx:responseError', (e) => {
                const element = e.detail.elt;
                const target = e.detail.target;

                // Hide loading states on error
                if (target) this.hideContentLoading(target);
                if (element) this.hideButtonLoading(element);
            });
        }

        // Form submission loading states
        setupFormLoadingStates() {
            document.body.addEventListener('htmx:beforeRequest', (e) => {
                const form = e.detail.elt.closest('form');
                if (form) {
                    const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
                    if (submitButton) {
                        this.showButtonLoading(submitButton, 'submitting');
                    }

                    // Disable all form controls
                    this.disableFormControls(form);
                }
            });
        }

        // Button loading states for non-HTMX buttons
        setupButtonLoadingStates() {
            document.addEventListener('click', (e) => {
                const button = e.target.closest('button, a');
                if (!button) return;

                // Skip if HTMX will handle it
                if (button.hasAttribute('hx-get') || button.hasAttribute('hx-post') ||
                    button.hasAttribute('hx-put') || button.hasAttribute('hx-delete')) return;

                // Show loading for buttons with data-loading attribute
                if (button.dataset.loading) {
                    this.showButtonLoading(button, button.dataset.loading);
                }
            });
        }

        // Show skeleton loading in content areas
        showContentLoading(element, type = 'listItem') {
            if (!element || element.dataset.loadingActive) return;

            element.dataset.loadingActive = 'true';
            element.dataset.originalContent = element.innerHTML;

            const skeletonCount = parseInt(element.dataset.skeletonCount) || config.skeletonCount;
            const skeletonType = element.dataset.skeletonType || type;

            let skeletonHTML = '';
            for (let i = 0; i < skeletonCount; i++) {
                skeletonHTML += skeletonTemplates[skeletonType] || skeletonTemplates.listItem;
            }

            element.innerHTML = `<div class="loading-skeleton">${skeletonHTML}</div>`;
            element.classList.add('is-loading');

            // Store loading start time for minimum duration
            this.activeLoadings.set(element, Date.now());
        }

        // Hide content loading
        hideContentLoading(element) {
            if (!element || !element.dataset.loadingActive) return;

            const loadingStartTime = this.activeLoadings.get(element);
            const elapsedTime = loadingStartTime ? Date.now() - loadingStartTime : 0;
            const remainingTime = Math.max(0, config.minLoadingDuration - elapsedTime);

            const hideLoading = () => {
                element.classList.remove('is-loading');
                delete element.dataset.loadingActive;

                // Restore original content if no new content was loaded
                if (element.innerHTML.includes('loading-skeleton') && element.dataset.originalContent) {
                    element.innerHTML = element.dataset.originalContent;
                }

                delete element.dataset.originalContent;
                this.activeLoadings.delete(element);
            };

            if (remainingTime > 0) {
                setTimeout(hideLoading, remainingTime);
            } else {
                hideLoading();
            }
        }

        // Show button loading state
        showButtonLoading(button, loadingType = 'default') {
            if (!button || button.dataset.loadingActive) return;

            button.dataset.loadingActive = 'true';
            button.dataset.originalText = button.innerHTML;
            button.dataset.originalDisabled = button.disabled;

            button.disabled = true;
            button.classList.add('loading');

            const loadingText = config.loadingText[loadingType] || config.loadingText.default;
            const icon = this.getLoadingIcon(loadingType);

            button.innerHTML = `${icon}<span class="loading-text">${loadingText}</span>`;

            // Store loading start time
            this.activeLoadings.set(button, Date.now());
        }

        // Hide button loading state
        hideButtonLoading(button) {
            if (!button || !button.dataset.loadingActive) return;

            const loadingStartTime = this.activeLoadings.get(button);
            const elapsedTime = loadingStartTime ? Date.now() - loadingStartTime : 0;
            const remainingTime = Math.max(0, config.minLoadingDuration - elapsedTime);

            const hideLoading = () => {
                button.classList.remove('loading');
                button.disabled = button.dataset.originalDisabled === 'true';
                button.innerHTML = button.dataset.originalText || button.innerHTML;

                delete button.dataset.loadingActive;
                delete button.dataset.originalText;
                delete button.dataset.originalDisabled;

                this.activeLoadings.delete(button);
            };

            if (remainingTime > 0) {
                setTimeout(hideLoading, remainingTime);
            } else {
                hideLoading();
            }
        }

        // Show overlay loading
        showOverlayLoading(element, options = {}) {
            if (!element || element.querySelector('.loading-overlay')) return;

            const { text = config.loadingText.default, spinner = true } = options;

            const overlay = document.createElement('div');
            overlay.className = 'loading-overlay';
            overlay.innerHTML = `
                <div class="loading-content">
                    ${spinner ? '<div class="loading-spinner"></div>' : ''}
                    <p class="loading-text">${text}</p>
                </div>
            `;

            element.style.position = 'relative';
            element.appendChild(overlay);
            element.classList.add('has-loading-overlay');

            // Animate in
            requestAnimationFrame(() => {
                overlay.classList.add('show');
            });
        }

        // Hide overlay loading
        hideOverlayLoading(element) {
            if (!element) return;

            const overlay = element.querySelector('.loading-overlay');
            if (overlay) {
                overlay.classList.remove('show');
                setTimeout(() => {
                    overlay.remove();
                    element.classList.remove('has-loading-overlay');
                }, 300);
            }
        }

        // Disable form controls during submission
        disableFormControls(form) {
            const controls = form.querySelectorAll('input, select, textarea, button');
            controls.forEach(control => {
                if (control.type !== 'submit') {
                    control.dataset.originalDisabled = control.disabled;
                    control.disabled = true;
                }
            });

            // Re-enable on page unload or after timeout
            const enableControls = () => {
                controls.forEach(control => {
                    if (control.type !== 'submit') {
                        control.disabled = control.dataset.originalDisabled === 'true';
                        delete control.dataset.originalDisabled;
                    }
                });
            };

            window.addEventListener('beforeunload', enableControls, { once: true });
            setTimeout(enableControls, 30000); // Fallback timeout
        }

        // Get appropriate loading icon for different operations
        getLoadingIcon(type) {
            const icons = {
                default: '<i class="fas fa-spinner fa-spin me-2"></i>',
                saving: '<i class="fas fa-save fa-pulse me-2"></i>',
                deleting: '<i class="fas fa-trash fa-pulse me-2"></i>',
                submitting: '<i class="fas fa-paper-plane fa-pulse me-2"></i>',
                processing: '<i class="fas fa-cog fa-spin me-2"></i>'
            };
            return icons[type] || icons.default;
        }

        // Public methods for manual control
        showLoading(element, type = 'overlay', options = {}) {
            switch (type) {
                case 'skeleton':
                    this.showContentLoading(element, options.skeletonType);
                    break;
                case 'button':
                    this.showButtonLoading(element, options.loadingType);
                    break;
                case 'overlay':
                default:
                    this.showOverlayLoading(element, options);
                    break;
            }
        }

        hideLoading(element, type = 'overlay') {
            switch (type) {
                case 'skeleton':
                    this.hideContentLoading(element);
                    break;
                case 'button':
                    this.hideButtonLoading(element);
                    break;
                case 'overlay':
                default:
                    this.hideOverlayLoading(element);
                    break;
            }
        }
    }

    // =========================================================================
    // Offcanvas Loading States
    // =========================================================================

    function showOffcanvasLoading(panelId, options = {}) {
        const panel = document.getElementById(panelId);
        if (!panel) return;

        const { skeletonType = 'form', text = config.loadingText.default } = options;
        const contentId = panelId === 'detailPanel' ? 'detailContent' : 'offcanvasContent';
        const content = document.getElementById(contentId);

        if (content) {
            content.innerHTML = `
                <div class="loading-state">
                    <div class="loading-spinner"></div>
                    <p class="loading-text mt-3">${text}</p>
                </div>
            `;
        }
    }

    function hideOffcanvasLoading(panelId) {
        // Loading is hidden when content is replaced
        // This function exists for API consistency
    }

    function showOffcanvasError(message, panelId) {
        const contentId = panelId === 'detailPanel' ? 'detailContent' : 'offcanvasContent';
        const content = document.getElementById(contentId);

        if (content) {
            content.innerHTML = `
                <div class="error-state">
                    <div class="alert alert-danger" role="alert">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        ${message}
                    </div>
                    <button type="button" class="btn btn-outline-secondary" onclick="history.back()">
                        <i class="fas fa-arrow-left me-2"></i>Go Back
                    </button>
                </div>
            `;
        }
    }

    // =========================================================================
    // Progress Indicators
    // =========================================================================

    class ProgressIndicator {
        constructor(container, options = {}) {
            this.container = container;
            this.options = {
                type: 'bar', // 'bar', 'circle', 'steps'
                showPercentage: true,
                showLabel: true,
                animated: true,
                ...options
            };
            this.progress = 0;
            this.create();
        }

        create() {
            this.element = document.createElement('div');
            this.element.className = `progress-indicator progress-${this.options.type}`;

            if (this.options.type === 'bar') {
                this.element.innerHTML = `
                    <div class="progress-label"></div>
                    <div class="progress">
                        <div class="progress-bar ${this.options.animated ? 'progress-bar-animated' : ''}"
                             role="progressbar" style="width: 0%"></div>
                    </div>
                    <div class="progress-percentage">0%</div>
                `;
            }

            this.container.appendChild(this.element);
        }

        update(progress, label = '') {
            this.progress = Math.max(0, Math.min(100, progress));

            if (this.options.type === 'bar') {
                const progressBar = this.element.querySelector('.progress-bar');
                const progressLabel = this.element.querySelector('.progress-label');
                const progressPercentage = this.element.querySelector('.progress-percentage');

                if (progressBar) {
                    progressBar.style.width = `${this.progress}%`;
                    progressBar.setAttribute('aria-valuenow', this.progress);
                }

                if (progressLabel && this.options.showLabel) {
                    progressLabel.textContent = label;
                }

                if (progressPercentage && this.options.showPercentage) {
                    progressPercentage.textContent = `${Math.round(this.progress)}%`;
                }
            }
        }

        complete(message = 'Complete!') {
            this.update(100, message);
            setTimeout(() => {
                this.element.classList.add('complete');
            }, 100);
        }

        remove() {
            if (this.element && this.element.parentNode) {
                this.element.remove();
            }
        }
    }

    // =========================================================================
    // Initialization and Public API
    // =========================================================================

    // Initialize loading state manager
    const loadingManager = new LoadingStateManager();

    // Global functions for backward compatibility and manual control
    window.showOffcanvasLoading = showOffcanvasLoading;
    window.hideOffcanvasLoading = hideOffcanvasLoading;
    window.showOffcanvasError = showOffcanvasError;

    // Public API
    window.LoadingStates = {
        // Core loading manager
        manager: loadingManager,

        // Content loading
        showContentLoading: (element, type) => loadingManager.showContentLoading(element, type),
        hideContentLoading: (element) => loadingManager.hideContentLoading(element),

        // Button loading
        showButtonLoading: (button, type) => loadingManager.showButtonLoading(button, type),
        hideButtonLoading: (button) => loadingManager.hideButtonLoading(button),

        // Overlay loading
        showOverlayLoading: (element, options) => loadingManager.showOverlayLoading(element, options),
        hideOverlayLoading: (element) => loadingManager.hideOverlayLoading(element),

        // Offcanvas loading
        showOffcanvasLoading,
        hideOffcanvasLoading,
        showOffcanvasError,

        // Progress indicators
        ProgressIndicator,

        // Generic loading control
        show: (element, type, options) => loadingManager.showLoading(element, type, options),
        hide: (element, type) => loadingManager.hideLoading(element, type),

        // Configuration
        config
    };

})(window);
