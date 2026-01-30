/**
 * Accessibility and Keyboard Navigation Enhancement
 *
 * This module provides comprehensive accessibility features for modals and offcanvas panels:
 * - Focus trapping and restoration
 * - Visible focus indicators
 * - Keyboard shortcuts and navigation
 * - ARIA labels and screen reader support
 * - Dynamic content announcements
 */

class AccessibilityManager {
    constructor() {
        this.focusHistory = [];
        this.currentTrapContainer = null;
        this.init();
    }

    init() {
        this.setupFocusManagement();
        this.setupKeyboardShortcuts();
        this.setupAriaSupport();
        this.setupScreenReaderAnnouncements();
    }

    /**
     * Focus Management for Modals and Panels
     * Implements focus trapping and restoration as per Requirements 10.1, 10.2
     */
    setupFocusManagement() {
        // Store original focus when modal/offcanvas opens
        document.addEventListener('show.bs.modal', (e) => {
            this.storeFocus();
            this.setupFocusTrap(e.target);
        });

        document.addEventListener('show.bs.offcanvas', (e) => {
            this.storeFocus();
            this.setupFocusTrap(e.target);
        });

        // Restore focus when modal/offcanvas closes
        document.addEventListener('hidden.bs.modal', (e) => {
            this.restoreFocus();
            this.removeFocusTrap();
        });

        document.addEventListener('hidden.bs.offcanvas', (e) => {
            this.restoreFocus();
            this.removeFocusTrap();
        });

        // Set initial focus when shown
        document.addEventListener('shown.bs.modal', (e) => {
            this.setInitialFocus(e.target);
        });

        document.addEventListener('shown.bs.offcanvas', (e) => {
            this.setInitialFocus(e.target);
        });
    }

    /**
     * Store the currently focused element
     */
    storeFocus() {
        const activeElement = document.activeElement;
        if (activeElement && activeElement !== document.body) {
            this.focusHistory.push(activeElement);
        }
    }

    /**
     * Restore focus to the previously focused element
     */
    restoreFocus() {
        if (this.focusHistory.length > 0) {
            const elementToFocus = this.focusHistory.pop();
            if (elementToFocus && typeof elementToFocus.focus === 'function') {
                // Use setTimeout to ensure the modal/offcanvas is fully hidden
                setTimeout(() => {
                    try {
                        elementToFocus.focus();
                    } catch (e) {
                        // Element might no longer be in DOM, focus body instead
                        document.body.focus();
                    }
                }, 100);
            }
        }
    }

    /**
     * Set up focus trapping within a container
     */
    setupFocusTrap(container) {
        this.currentTrapContainer = container;
        container.addEventListener('keydown', this.handleFocusTrap.bind(this));
    }

    /**
     * Remove focus trap
     */
    removeFocusTrap() {
        if (this.currentTrapContainer) {
            this.currentTrapContainer.removeEventListener('keydown', this.handleFocusTrap.bind(this));
            this.currentTrapContainer = null;
        }
    }

    /**
     * Handle focus trapping with Tab key
     */
    handleFocusTrap(e) {
        if (e.key !== 'Tab') return;

        const focusableElements = this.getFocusableElements(e.currentTarget);
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
            // Shift + Tab: moving backwards
            if (document.activeElement === firstElement) {
                e.preventDefault();
                lastElement.focus();
            }
        } else {
            // Tab: moving forwards
            if (document.activeElement === lastElement) {
                e.preventDefault();
                firstElement.focus();
            }
        }
    }

    /**
     * Get all focusable elements within a container
     */
    getFocusableElements(container) {
        const focusableSelectors = [
            'input:not([disabled]):not([tabindex="-1"])',
            'select:not([disabled]):not([tabindex="-1"])',
            'textarea:not([disabled]):not([tabindex="-1"])',
            'button:not([disabled]):not([tabindex="-1"])',
            'a[href]:not([tabindex="-1"])',
            '[tabindex]:not([tabindex="-1"])',
            '[contenteditable="true"]:not([tabindex="-1"])'
        ].join(', ');

        return Array.from(container.querySelectorAll(focusableSelectors))
            .filter(el => this.isVisible(el));
    }

    /**
     * Check if an element is visible
     */
    isVisible(element) {
        const style = window.getComputedStyle(element);
        return style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               element.offsetParent !== null;
    }

    /**
     * Set initial focus when modal/offcanvas is shown
     */
    setInitialFocus(container) {
        // Priority order for initial focus:
        // 1. Element with autofocus attribute
        // 2. First form input
        // 3. First button (excluding close button)
        // 4. Close button as fallback

        const autofocusElement = container.querySelector('[autofocus]');
        if (autofocusElement && this.isVisible(autofocusElement)) {
            autofocusElement.focus();
            return;
        }

        const firstInput = container.querySelector('input:not([type="hidden"]), select, textarea');
        if (firstInput && this.isVisible(firstInput)) {
            firstInput.focus();
            return;
        }

        const firstButton = container.querySelector('button:not(.btn-close)');
        if (firstButton && this.isVisible(firstButton)) {
            firstButton.focus();
            return;
        }

        const closeButton = container.querySelector('.btn-close');
        if (closeButton) {
            closeButton.focus();
        }
    }

    /**
     * Keyboard Shortcuts and Navigation
     * Implements Requirements 10.3, 10.5
     */
    setupKeyboardShortcuts() {
.handleEnterKey(e);
            }

            // Arrow keys for navigation in lists
            if (['ArrowUp', 'ArrowDown'].includes(e.key)) {
                this.handleArrowNavigation(e);
            }
        });
    }

    /**
     * Handle Escape key to close modals/panels
     */
    handleEscapeKey(e) {
        // Find the topmost modal or offcanvas
        const openModal = document.querySelector('.modal.show');
        const openOffcanvas = document.querySelector('.offcanvas.show');

        if (openModal) {
            const modalInstance = bootstrap.Modal.getInstance(openModal);
            if (modalInstance) {
                modalInstance.hide();
                e.preventDefault();
            }
        } else if (openOffcanvas) {
            const offcanvasInstance = bootstrap.Offcanvas.getInstance(openOffcanvas);
            if (offcanvasInstance) {
                offcanvasInstance.hide();
                e.preventDefault();
            }
        }
    }

    /**
     * Handle Ctrl+S save shortcut
     */
    handleSaveShortcut(e) {
        const activeContainer = document.querySelector('.modal.show, .offcanvas.show');
        if (activeContainer) {
            const saveButton = activeContainer.querySelector(
                'button[type="submit"], .btn-primary:not(.btn-close), button[data-action="save"]'
            );

            if (saveButton && !saveButton.disabled) {
                e.preventDefault();
                saveButton.click();
                this.announceToScreenReader('Form saved');
            }
        }
    }

    /**
     * Handle Enter key for form submission
     */
    handleEnterKey(e) {
        const target = e.target;

        // Don't interfere with textarea or contenteditable elements
        if (target.tagName === 'TEXTAREA' || target.contentEditable === 'true') {
            return;
        }

        // If we're in a modal or offcanvas form
        const container = target.closest('.modal, .offcanvas');
        if (container) {
            const form = target.closest('form');
            if (form) {
                const submitButton = form.querySelector('button[type="submit"], .btn-primary:not(.btn-close)');
                if (submitButton && !submitButton.disabled) {
                    e.preventDefault();
                    submitButton.click();
                }
            }
        }
    }

    /**
     * Handle arrow key navigation in lists
     */
    handleArrowNavigation(e) {
        const target = e.target;

        // Only handle if we're on a list item or focusable element in a list
        const listItem = target.closest('.list-group-item, .table-row, [role="listitem"]');
        if (!listItem) return;

        const container = listItem.closest('.list-group, .table, [role="list"]');
        if (!container) return;

        const allItems = Array.from(container.querySelectorAll('.list-group-item, .table-row, [role="listitem"]'));
        const currentIndex = allItems.indexOf(listItem);

        let nextIndex;
        if (e.key === 'ArrowDown') {
            nextIndex = currentIndex + 1;
        } else if (e.key === 'ArrowUp') {
            nextIndex = currentIndex - 1;
        }

        if (nextIndex >= 0 && nextIndex < allItems.length) {
            e.preventDefault();
            const nextItem = allItems[nextIndex];
            const focusableElement = nextItem.querySelector('a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])') || nextItem;
            focusableElement.focus();
        }
    }

    /**
     * ARIA Labels and Screen Reader Support
     * Implements Requirement 10.4
     */
    setupAriaSupport() {
        // Enhance existing elements with ARIA attributes
        this.enhanceInteractiveElements();

        // Set up dynamic content announcements
        this.setupDynamicAnnouncements();

        // Monitor for new content and enhance it
        this.observeNewContent();
    }

    /**
     * Enhance interactive elements with proper ARIA attributes
     */
    enhanceInteractiveElements() {
        // Enhance buttons without proper labels
        document.querySelectorAll('button:not([aria-label]):not([aria-labelledby])').forEach(button => {
            const text = button.textContent.trim();
            const icon = button.querySelector('i[class*="fa-"]');

            if (!text && icon) {
                // Button with only icon - add aria-label based on icon class
                const ariaLabel = this.getAriaLabelFromIcon(icon.className);
                if (ariaLabel) {
                    button.setAttribute('aria-label', ariaLabel);
                }
            }
        });

        // Enhance form controls
        document.querySelectorAll('input, select, textarea').forEach(control => {
            if (!control.getAttribute('aria-label') && !control.getAttribute('aria-labelledby')) {
                const label = control.closest('.form-group, .mb-3')?.querySelector('label');
                if (label && !label.getAttribute('for')) {
                    const id = control.id || `control_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                    control.id = id;
                    label.setAttribute('for', id);
                }
            }
        });

        // Enhance expandable elements
        document.querySelectorAll('[data-bs-toggle="collapse"]').forEach(toggle => {
            if (!toggle.getAttribute('aria-expanded')) {
                const target = document.querySelector(toggle.getAttribute('data-bs-target'));
                const isExpanded = target?.classList.contains('show') || false;
                toggle.setAttribute('aria-expanded', isExpanded.toString());
            }
        });

        // Enhance modal and offcanvas elements
        document.querySelectorAll('.modal, .offcanvas').forEach(container => {
            if (!container.getAttribute('aria-labelledby')) {
                const title = container.querySelector('.modal-title, .offcanvas-title');
                if (title) {
                    const titleId = title.id || `title_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                    title.id = titleId;
                    container.setAttribute('aria-labelledby', titleId);
                }
            }
        });
    }

    /**
     * Get appropriate ARIA label from Font Awesome icon class
     */
    getAriaLabelFromIcon(className) {
        const iconMap = {
            'fa-edit': 'Edit',
            'fa-pencil': 'Edit',
            'fa-trash': 'Delete',
            'fa-times': 'Close',
            'fa-plus': 'Add',
            'fa-save': 'Save',
            'fa-search': 'Search',
            'fa-filter': 'Filter',
            'fa-sort': 'Sort',
            'fa-eye': 'View',
            'fa-share': 'Share',
            'fa-download': 'Download',
            'fa-upload': 'Upload',
            'fa-print': 'Print',
            'fa-copy': 'Copy',
            'fa-check': 'Confirm',
            'fa-arrow-left': 'Go back',
            'fa-arrow-right': 'Go forward',
            'fa-chevron-up': 'Expand',
            'fa-chevron-down': 'Collapse',
            'fa-info': 'Information',
            'fa-warning': 'Warning',
            'fa-exclamation': 'Alert'
        };

        for (const [iconClass, label] of Object.entries(iconMap)) {
            if (className.includes(iconClass)) {
                return label;
            }
        }
        return null;
    }

    /**
     * Set up dynamic content announcements
     */
    setupDynamicAnnouncements() {
        // Create live region for announcements
        if (!document.getElementById('sr-live-region')) {
            const liveRegion = document.createElement('div');
            liveRegion.id = 'sr-live-region';
            liveRegion.setAttribute('aria-live', 'polite');
            liveRegion.setAttribute('aria-atomic', 'true');
            liveRegion.className = 'sr-only';
            document.body.appendChild(liveRegion);
        }

        // Monitor HTMX events for dynamic content changes
        document.body.addEventListener('htmx:afterSwap', (e) => {
            const target = e.detail.target;
            this.announceContentChange(target);
            this.enhanceNewContent(target);
        });

        // Monitor form submissions
        document.body.addEventListener('htmx:afterRequest', (e) => {
            if (e.detail.successful) {
                const xhr = e.detail.xhr;
                const triggerElement = e.detail.elt;

                if (triggerElement.tagName === 'FORM') {
                    this.announceToScreenReader('Form submitted successfully');
                } else if (triggerElement.closest('.modal, .offcanvas')) {
                    this.announceToScreenReader('Action completed');
                }
            } else {
                this.announceToScreenReader('An error occurred. Please try again.');
            }
        });

        // Monitor Bootstrap events
        document.addEventListener('shown.bs.modal', (e) => {
            const title = e.target.querySelector('.modal-title')?.textContent || 'Dialog';
            this.announceToScreenReader(`${title} opened`);
        });

        document.addEventListener('shown.bs.offcanvas', (e) => {
            const title = e.target.querySelector('.offcanvas-title')?.textContent || 'Panel';
            this.announceToScreenReader(`${title} opened`);
        });
    }

    /**
     * Announce content changes to screen readers
     */
    announceContentChange(target) {
        if (target.classList.contains('list-container') || target.closest('.list-container')) {
            this.announceToScreenReader('List updated');
        } else if (target.classList.contains('form-container') || target.closest('form')) {
            this.announceToScreenReader('Form updated');
        } else if (target.classList.contains('alert')) {
            const alertText = target.textContent.trim();
            this.announceToScreenReader(alertText);
        }
    }

    /**
     * Announce message to screen readers
     */
    announceToScreenReader(message) {
        const liveRegion = document.getElementById('sr-live-region');
        if (liveRegion) {
            liveRegion.textContent = message;

            // Clear after announcement to allow repeated messages
            setTimeout(() => {
                liveRegion.textContent = '';
            }, 1000);
        }
    }

    /**
     * Observe new content and enhance it with accessibility features
     */
    observeNewContent() {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        this.enhanceNewContent(node);
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    /**
     * Enhance newly added content with accessibility features
     */
    enhanceNewContent(container) {
        // Enhance interactive elements in the new content
        const buttons = container.querySelectorAll ? container.querySelectorAll('button:not([aria-label]):not([aria-labelledby])') : [];
        buttons.forEach(button => {
            const text = button.textContent.trim();
            const icon = button.querySelector('i[class*="fa-"]');

            if (!text && icon) {
                const ariaLabel = this.getAriaLabelFromIcon(icon.className);
                if (ariaLabel) {
                    button.setAttribute('aria-label', ariaLabel);
                }
            }
        });

        // Enhance form controls
        const controls = container.querySelectorAll ? container.querySelectorAll('input, select, textarea') : [];
        controls.forEach(control => {
            if (!control.getAttribute('aria-label') && !control.getAttribute('aria-labelledby')) {
                const label = control.closest('.form-group, .mb-3')?.querySelector('label');
                if (label && !label.getAttribute('for')) {
                    const id = control.id || `control_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                    control.id = id;
                    label.setAttribute('for', id);
                }
            }
        });
    }

    /**
     * Screen Reader Announcements Setup
     */
    setupScreenReaderAnnouncements() {
        // Announce loading states
        document.body.addEventListener('htmx:beforeRequest', (e) => {
            const trigger = e.detail.elt;
            if (trigger.closest('.modal, .offcanvas')) {
                this.announceToScreenReader('Loading...');
            }
        });

        // Announce validation errors
        document.addEventListener('invalid', (e) => {
            const field = e.target;
            const message = field.validationMessage || 'Please check this field';
            this.announceToScreenReader(`Validation error: ${message}`);
        }, true);

        // Announce successful operations
        document.body.addEventListener('htmx:afterSettle', (e) => {
            const successMessage = e.detail.target.querySelector('.alert-success');
            if (successMessage) {
                this.announceToScreenReader(successMessage.textContent.trim());
            }
        });
    }
}

// Initialize accessibility manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.accessibilityManager = new AccessibilityManager();
});

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AccessibilityManager;
}
