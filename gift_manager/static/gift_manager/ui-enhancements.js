/**
 * UI Enhancements
 * Modern UI features: date pickers, form validation, loading states, and more
 */

(function(window) {
    'use strict';

    // =========================================================================
    // Configuration
    // =========================================================================

    const config = {
        flatpickr: {
            dateFormat: 'Y-m-d',
            altInput: true,
            altFormat: 'F j, Y',
            allowInput: true,
            animate: true
        },
        validation: {
            debounceMs: 300,
            showSuccessState: true
        },
        loading: {
            minDuration: 300 // Minimum loading display time
        }
    };

    // =========================================================================
    // Date Picker (Flatpickr)
    // =========================================================================

    function initDatePickers() {
        if (typeof flatpickr === 'undefined') {
            console.warn('Flatpickr not loaded, skipping date picker initialization');
            return;
        }

        const dateInputs = document.querySelectorAll('input[type="date"]');

        dateInputs.forEach(input => {
            // Skip if already initialized
            if (input._flatpickr) return;

            // Get locale from html lang attribute
            const locale = document.documentElement.lang || 'en';

            const fpConfig = {
                ...config.flatpickr,
                locale: locale === 'fr' ? 'fr' : 'default',
                onReady: function(selectedDates, dateStr, instance) {
                    // Add custom styling class
                    instance.calendarContainer.classList.add('modern-datepicker');
                }
            };

            flatpickr(input, fpConfig);
        });
    }

    // =========================================================================
    // Form Validation
    // =========================================================================

    function initFormValidation() {
        const forms = document.querySelectorAll('form:not(.no-validate)');

        forms.forEach(form => {
            // Skip if already initialized
            if (form.dataset.validationInit) return;
            form.dataset.validationInit = 'true';

            const inputs = form.querySelectorAll('input, select, textarea');

            inputs.forEach(input => {
                // Add validation on blur
                input.addEventListener('blur', () => validateField(input));

                // Add validation on input with debounce
                let debounceTimer;
                input.addEventListener('input', () => {
                    clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(() => {
                        validateField(input);
                    }, config.validation.debounceMs);
                });
            });

            // Validate all fields on submit
            form.addEventListener('submit', (e) => {
                let isValid = true;

                inputs.forEach(input => {
                    if (!validateField(input)) {
                        isValid = false;
                    }
                });

                if (!isValid) {
                    e.preventDefault();
                    // Focus first invalid field
                    const firstInvalid = form.querySelector('.is-invalid');
                    if (firstInvalid) {
                        firstInvalid.focus();
                    }
                }
            });
        });
    }

    function validateField(input) {
        // Skip hidden inputs
        if (input.type === 'hidden') return true;

        const value = input.value.trim();
        const isRequired = input.hasAttribute('required');
        let isValid = true;
        let errorMessage = '';

        // Remove existing validation states
        input.classList.remove('is-valid', 'is-invalid');
        removeValidationMessage(input);

        // Required validation
        if (isRequired && !value) {
            isValid = false;
            errorMessage = getTranslation('fieldRequired', 'This field is required');
        }

        // Email validation
        if (isValid && input.type === 'email' && value) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(value)) {
                isValid = false;
                errorMessage = getTranslation('invalidEmail', 'Please enter a valid email address');
            }
        }

        // Min length validation
        if (isValid && input.minLength > 0 && value.length < input.minLength) {
            isValid = false;
            errorMessage = getTranslation('minLength', 'Minimum {0} characters required').replace('{0}', input.minLength);
        }

        // Max length validation
        if (isValid && input.maxLength > 0 && value.length > input.maxLength) {
            isValid = false;
            errorMessage = getTranslation('maxLength', 'Maximum {0} characters allowed').replace('{0}', input.maxLength);
        }

        // Date validation
        if (isValid && input.type === 'date' && value) {
            const date = new Date(value);
            if (isNaN(date.getTime())) {
                isValid = false;
                errorMessage = getTranslation('invalidDate', 'Please enter a valid date');
            }
        }

        // Apply validation state
        if (!isValid) {
            input.classList.add('is-invalid');
            showValidationMessage(input, errorMessage, 'invalid');
        } else if (value && config.validation.showSuccessState) {
            input.classList.add('is-valid');
        }

        return isValid;
    }

    function showValidationMessage(input, message, type) {
        const wrapper = input.closest('.form-group') || input.parentElement;
        if (!wrapper) return;

        // Remove existing message
        removeValidationMessage(input);

        // Create message element
        const messageEl = document.createElement('div');
        messageEl.className = type === 'invalid' ? 'invalid-feedback' : 'valid-feedback';
        messageEl.textContent = message;
        messageEl.style.display = 'block';

        // Insert after input
        input.after(messageEl);
    }

    function removeValidationMessage(input) {
        const wrapper = input.closest('.form-group') || input.parentElement;
        if (!wrapper) return;

        const existingMessage = wrapper.querySelector('.invalid-feedback, .valid-feedback');
        if (existingMessage) {
            existingMessage.remove();
        }
    }

    // =========================================================================
    // Loading States
    // =========================================================================

    function showLoading(element, options = {}) {
        const { text = 'Loading...', overlay = true } = options;

        if (!element) return;

        // Add loading class
        element.classList.add('is-loading');

        if (overlay) {
            // Create overlay
            const loadingOverlay = document.createElement('div');
            loadingOverlay.className = 'loading-overlay';
            loadingOverlay.innerHTML = `
                <div class="loading-spinner">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">${text}</span>
                    </div>
                    <p class="loading-text mt-2">${text}</p>
                </div>
            `;

            element.style.position = 'relative';
            element.appendChild(loadingOverlay);
        }
    }

    function hideLoading(element) {
        if (!element) return;

        element.classList.remove('is-loading');

        const overlay = element.querySelector('.loading-overlay');
        if (overlay) {
            overlay.remove();
        }
    }

    function showButtonLoading(button) {
        if (!button) return;

        button.dataset.originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = `
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            ${getTranslation('loading', 'Loading...')}
        `;
    }

    function hideButtonLoading(button) {
        if (!button || !button.dataset.originalText) return;

        button.disabled = false;
        button.innerHTML = button.dataset.originalText;
        delete button.dataset.originalText;
    }

    // =========================================================================
    // Skeleton Screens
    // =========================================================================

    function createSkeleton(type, count = 1) {
        const skeletons = [];

        for (let i = 0; i < count; i++) {
            const skeleton = document.createElement('div');
            skeleton.className = 'skeleton-item';

            switch (type) {
                case 'card':
                    skeleton.innerHTML = `
                        <div class="skeleton-card">
                            <div class="skeleton skeleton-header"></div>
                            <div class="skeleton skeleton-text"></div>
                            <div class="skeleton skeleton-text short"></div>
                        </div>
                    `;
                    break;

                case 'table-row':
                    skeleton.innerHTML = `
                        <div class="skeleton-table-row">
                            <div class="skeleton skeleton-cell"></div>
                            <div class="skeleton skeleton-cell"></div>
                            <div class="skeleton skeleton-cell short"></div>
                        </div>
                    `;
                    break;

                case 'list':
                    skeleton.innerHTML = `
                        <div class="skeleton-list-item">
                            <div class="skeleton skeleton-avatar"></div>
                            <div class="skeleton-content">
                                <div class="skeleton skeleton-text"></div>
                                <div class="skeleton skeleton-text short"></div>
                            </div>
                        </div>
                    `;
                    break;

                default:
                    skeleton.innerHTML = `<div class="skeleton skeleton-text"></div>`;
            }

            skeletons.push(skeleton);
        }

        return skeletons;
    }

    function showSkeletonIn(container, type, count = 3) {
        if (!container) return;

        container.innerHTML = '';
        const skeletons = createSkeleton(type, count);
        skeletons.forEach(s => container.appendChild(s));
    }

    // =========================================================================
    // Mobile Table Enhancements
    // =========================================================================

    function enhanceMobileTables() {
        // Only on mobile
        if (window.innerWidth > 576) return;

        const tables = document.querySelectorAll('.gridjs-table');

        tables.forEach(table => {
            if (table.dataset.mobileEnhanced) return;
            table.dataset.mobileEnhanced = 'true';

            // Get headers
            const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());

            // Add data attributes to cells
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                cells.forEach((cell, index) => {
                    if (headers[index] && !cell.classList.contains('gridjs-td-hidden')) {
                        cell.setAttribute('data-label', headers[index]);
                    }
                });
            });
        });
    }

    // =========================================================================
    // View Toggle (Card/List View) with User Preferences
    // =========================================================================

    // User preferences (can be set from server-side template)
    const viewPreferences = {
        defaultDesktop: window.userViewPreferences?.desktop || 'list',
        defaultMobile: window.userViewPreferences?.mobile || 'card',
        mobileBreakpoint: 768
    };

    function isMobileView() {
        return window.innerWidth < viewPreferences.mobileBreakpoint;
    }

    function getDefaultView() {
        return isMobileView() ? viewPreferences.defaultMobile : viewPreferences.defaultDesktop;
    }

    function setView(container, view) {
        if (!container) return;

        // Update container data attribute
        container.setAttribute('data-view', view);

        // Update toggle buttons
        const toggleButtons = container.querySelectorAll('.view-toggle-btn');
        toggleButtons.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === view);
        });

        // Dispatch event for other components to react
        container.dispatchEvent(new CustomEvent('viewchange', {
            detail: { view },
            bubbles: true
        }));
    }

    function initViewToggle() {
        // Find all grid containers with view toggle
        const gridContainers = document.querySelectorAll('.grid-container');

        gridContainers.forEach(container => {
            // Skip if already initialized
            if (container.dataset.viewToggleInit) return;
            container.dataset.viewToggleInit = 'true';

            const gridId = container.id || 'grid-' + Math.random().toString(36).substr(2, 9);
            if (!container.id) container.id = gridId;

            // Get saved preference or use default
            const savedView = localStorage.getItem(`view-preference-${gridId}`);
            const initialView = savedView || getDefaultView();

            // Set initial view
            setView(container, initialView);

            // Find or create toggle container
            let toggleContainer = container.querySelector('.view-toggle');
            if (!toggleContainer) {
                // Look for a header element to insert toggle
                const header = container.previousElementSibling;
                if (header && header.classList.contains('page-header')) {
                    const actionsContainer = header.querySelector('.page-header-actions') || header;
                    toggleContainer = document.createElement('div');
                    toggleContainer.className = 'view-toggle';
                    toggleContainer.innerHTML = `
                        <button type="button" class="view-toggle-btn ${initialView === 'list' ? 'active' : ''}" data-view="list" title="${getTranslation('listView', 'List view')}">
                            <i class="fas fa-list"></i>
                            <span>${getTranslation('list', 'List')}</span>
                        </button>
                        <button type="button" class="view-toggle-btn ${initialView === 'card' ? 'active' : ''}" data-view="card" title="${getTranslation('cardView', 'Card view')}">
                            <i class="fas fa-th-large"></i>
                            <span>${getTranslation('cards', 'Cards')}</span>
                        </button>
                    `;
                    actionsContainer.appendChild(toggleContainer);
                }
            }

            if (!toggleContainer) return;

            // Handle toggle button clicks
            toggleContainer.querySelectorAll('.view-toggle-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const view = btn.dataset.view;

                    // Update view
                    setView(container, view);

                    // Save preference for this specific grid
                    localStorage.setItem(`view-preference-${gridId}`, view);
                });
            });
        });

        // Listen for screen size changes to update default if no preference saved
        let resizeTimeout;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                gridContainers.forEach(container => {
                    const gridId = container.id;
                    const savedView = localStorage.getItem(`view-preference-${gridId}`);

                    // Only apply default if no user preference saved
                    if (!savedView) {
                        setView(container, getDefaultView());
                    }
                });
            }, 250);
        });
    }

    function setUserViewPreferences(desktop, mobile) {
        viewPreferences.defaultDesktop = desktop || 'list';
        viewPreferences.defaultMobile = mobile || 'card';
    }

    // =========================================================================
    // Keyboard Shortcuts
    // =========================================================================

    const shortcuts = new Map();

    function registerShortcut(keys, callback, description = '') {
        shortcuts.set(keys.toLowerCase(), { callback, description });
    }

    function initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ignore if typing in an input
            if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
                return;
            }

            // Build key string
            let keyString = '';
            if (e.ctrlKey || e.metaKey) keyString += 'ctrl+';
            if (e.altKey) keyString += 'alt+';
            if (e.shiftKey) keyString += 'shift+';
            keyString += e.key.toLowerCase();

            const shortcut = shortcuts.get(keyString);
            if (shortcut) {
                e.preventDefault();
                shortcut.callback();
            }
        });

        // Register default shortcuts
        registerShortcut('?', showShortcutsHelp, 'Show keyboard shortcuts');
        registerShortcut('g h', () => navigateTo('home'), 'Go to home');
        registerShortcut('g g', () => navigateTo('gifts'), 'Go to gifts');
        registerShortcut('g p', () => navigateTo('persons'), 'Go to persons');
        registerShortcut('g e', () => navigateTo('events'), 'Go to events');
        registerShortcut('n', focusNewButton, 'Create new item');
    }

    function navigateTo(page) {
        const urls = {
            home: '/',
            gifts: '/gifts/',
            persons: '/persons/',
            events: '/events/',
            groups: '/person_groups/'
        };

        if (urls[page]) {
            window.location.href = urls[page];
        }
    }

    function focusNewButton() {
        const newBtn = document.querySelector('a[href*="create"], button[type="submit"]');
        if (newBtn) {
            newBtn.focus();
        }
    }

    function showShortcutsHelp() {
        // Create modal if doesn't exist
        let modal = document.getElementById('shortcutsModal');
        if (!modal) {
            const shortcuts_list = Array.from(shortcuts.entries())
                .map(([key, { description }]) => `
                    <div class="shortcut-item">
                        <kbd>${key}</kbd>
                        <span>${description}</span>
                    </div>
                `)
                .join('');

            const modalHtml = `
                <div class="modal fade" id="shortcutsModal" tabindex="-1">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">
                                    <i class="fas fa-keyboard me-2"></i>${getTranslation('keyboardShortcuts', 'Keyboard Shortcuts')}
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <div class="shortcuts-list">
                                    ${shortcuts_list}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            document.body.insertAdjacentHTML('beforeend', modalHtml);
            modal = document.getElementById('shortcutsModal');
        }

        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }

    // =========================================================================
    // Improved Notifications
    // =========================================================================

    function showNotification(message, type = 'success', options = {}) {
        const { duration = null, icon = null, action = null } = options;

        // Use existing notification system if available
        if (typeof window.showNotification === 'function' && window.showNotification !== showNotification) {
            return window.showNotification(message, type, duration);
        }

        // Create container if needed
        let container = document.getElementById('notifications-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notifications-container';
            container.className = 'notifications-container';
            document.body.appendChild(container);
        }

        // Determine icon based on type
        const icons = {
            success: 'fa-check-circle',
            info: 'fa-info-circle',
            warning: 'fa-exclamation-triangle',
            danger: 'fa-times-circle',
            error: 'fa-times-circle'
        };

        const actualIcon = icon || icons[type] || icons.info;

        // Create notification
        const notification = document.createElement('div');
        notification.className = `notification notification-${type} animate-slide-in`;
        notification.innerHTML = `
            <div class="notification-icon">
                <i class="fas ${actualIcon}"></i>
            </div>
            <div class="notification-content">
                <div class="notification-message">${message}</div>
                ${action ? `<a href="${action.url}" class="notification-action">${action.text}</a>` : ''}
            </div>
            <button type="button" class="notification-close" aria-label="Close">
                <i class="fas fa-times"></i>
            </button>
        `;

        container.appendChild(notification);

        // Animate in
        requestAnimationFrame(() => {
            notification.classList.add('show');
        });

        // Close button
        notification.querySelector('.notification-close').addEventListener('click', () => {
            dismissNotification(notification);
        });

        // Auto dismiss
        const autoDuration = duration || (type === 'danger' ? 10000 : type === 'warning' ? 8000 : 5000);
        setTimeout(() => dismissNotification(notification), autoDuration);
    }

    function dismissNotification(notification) {
        notification.classList.remove('show');
        notification.classList.add('hide');
        setTimeout(() => notification.remove(), 300);
    }

    // =========================================================================
    // Utilities
    // =========================================================================

    function getTranslation(key, defaultValue) {
        // Check for translations object
        if (window.uiTranslations && window.uiTranslations[key]) {
            return window.uiTranslations[key];
        }
        return defaultValue;
    }

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

    // =========================================================================
    // Initialization
    // =========================================================================

    function init() {
        // Initialize all components
        initDatePickers();
        initFormValidation();
        initViewToggle();
        initKeyboardShortcuts();
        enhanceMobileTables();

        // Re-enhance tables on window resize
        window.addEventListener('resize', debounce(enhanceMobileTables, 250));

        // Re-initialize after HTMX swaps
        document.body.addEventListener('htmx:afterSwap', () => {
            initDatePickers();
            initFormValidation();
            enhanceMobileTables();
        });

        // Re-initialize after Grid.js renders
        document.body.addEventListener('gridjs:ready', () => {
            enhanceMobileTables();
        });
    }

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // =========================================================================
    // Public API
    // =========================================================================

    window.UIEnhancements = {
        // Date pickers
        initDatePickers,

        // Form validation
        initFormValidation,
        validateField,

        // Loading states
        showLoading,
        hideLoading,
        showButtonLoading,
        hideButtonLoading,

        // Skeleton screens
        createSkeleton,
        showSkeletonIn,

        // Mobile
        enhanceMobileTables,

        // View toggle
        initViewToggle,
        setView,
        setUserViewPreferences,
        getDefaultView,
        isMobileView,

        // Keyboard shortcuts
        registerShortcut,
        showShortcutsHelp,

        // Notifications
        showNotification,
        dismissNotification,

        // Utilities
        getTranslation,
        debounce,

        // Re-initialize
        init
    };

})(window);
