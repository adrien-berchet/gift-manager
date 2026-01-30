/**
 * Mobile Responsive Enhancements for Modern UX Interface
 * Handles dynamic mobile behavior, keyboard detection, and touch interactions
 */

(function() {
    'use strict';

    // Mobile detection and state management
    const MobileResponsive = {
        isMobile: false,
        isTablet: false,
        isKeyboardVisible: false,
        orientation: 'portrait',

        init: function() {
            this.detectDevice();
            this.setupEventListeners();
            this.handleInitialState();
        },

        detectDevice: function() {
            const width = window.innerWidth;
            const height = window.innerHeight;

            this.isMobile = width <= 768;
            this.isTablet = width > 768 && width <= 1024;
            this.orientation = width > height ? 'landscape' : 'portrait';

            // Update CSS classes
            document.body.classList.toggle('is-mobile', this.isMobile);
            document.body.classList.toggle('is-tablet', this.isTablet);
            document.body.classList.toggle('is-landscape', this.orientation === 'landscape');
        },

        setupEventListeners: function() {
            // Window resize handler
            let resizeTimeout;
            window.addEventListener('resize', () => {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(() => {
                    this.detectDevice();
                    this.handleResize();
                }, 100);
            });

            // Orientation change handler
            window.addEventListener('orientationchange', () => {
                setTimeout(() => {
                    this.detectDevice();
                    this.handleOrientationChange();
                }, 100);
            });

            // Virtual keyboard detection
            this.setupKeyboardDetection();

            // Modal and offcanvas event listeners
            this.setupModalHandlers();
            this.setupOffcanvasHandlers();
        },

        setupKeyboardDetection: function() {
            if (!this.isMobile) return;

            let initialViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;

            const handleViewportChange = () => {
                if (!window.visualViewport) return;

                const currentHeight = window.visualViewport.height;
                const heightDifference = initialViewportHeight - currentHeight;

                // Keyboard is likely visible if viewport height decreased significantly
                const wasKeyboardVisible = this.isKeyboardVisible;
                this.isKeyboardVisible = heightDifference > 150;

                if (wasKeyboardVisible !== this.isKeyboardVisible) {
                    this.handleKeyboardToggle();
                }
            };

            if (window.visualViewport) {
                window.visualViewport.addEventListener('resize', handleViewportChange);
            } else {
                // Fallback for older browsers
                window.addEventListener('resize', handleViewportChange);
            }

            // Focus/blur detection for form elements
            document.addEventListener('focusin', (e) => {
                if (this.isMobile && this.isFormElement(e.target)) {
                    setTimeout(() => {
                        this.isKeyboardVisible = true;
                        this.handleKeyboardToggle();
                    }, 300);
                }
            });

            document.addEventListener('focusout', (e) => {
                if (this.isMobile && this.isFormElement(e.target)) {
                    setTimeout(() => {
                        this.isKeyboardVisible = false;
                        this.handleKeyboardToggle();
                    }, 300);
                }
            });
        },

        isFormElement: function(element) {
            const formElements = ['INPUT', 'TEXTAREA', 'SELECT'];
            return formElements.includes(element.tagName) &&
                   element.type !== 'button' &&
                   element.type !== 'submit' &&
                   element.type !== 'reset';
        },

        handleKeyboardToggle: function() {
            document.body.classList.toggle('keyboard-visible', this.isKeyboardVisible);

            // Adjust modals and offcanvas when keyboard is visible
            const modals = document.querySelectorAll('.modal.show .modal-dialog');
            const offcanvas = document.querySelectorAll('.offcanvas.show');

            modals.forEach(modal => {
                modal.classList.toggle('keyboard-visible', this.isKeyboardVisible);
            });

            offcanvas.forEach(panel => {
                panel.classList.toggle('keyboard-visible', this.isKeyboardVisible);
            });

            // Scroll focused element into view
            if (this.isKeyboardVisible) {
                const focusedElement = document.activeElement;
                if (focusedElement && this.isFormElement(focusedElement)) {
                    setTimeout(() => {
                        focusedElement.scrollIntoView({
                            behavior: 'smooth',
                            block: 'center'
                        });
                    }, 100);
                }
            }
        },

        setupModalHandlers: function() {
            // Enhanced modal behavior for mobile
            document.addEventListener('show.bs.modal', (e) => {
                if (this.isMobile) {
                    this.handleModalShow(e.target);
                }
            });

            document.addEventListener('hide.bs.modal', (e) => {
                if (this.isMobile) {
                    this.handleModalHide(e.target);
                }
            });
        },

        setupOffcanvasHandlers: function() {
            // Enhanced offcanvas behavior for mobile
            document.addEventListener('show.bs.offcanvas', (e) => {
                if (this.isMobile) {
                    this.handleOffcanvasShow(e.target);
                }
            });

            document.addEventListener('hide.bs.offcanvas', (e) => {
                if (this.isMobile) {
                    this.handleOffcanvasHide(e.target);
                }
            });
        },

        handleModalShow: function(modal) {
            // Prevent body scroll on mobile
            document.body.style.overflow = 'hidden';

            // Add mobile-specific classes
            modal.classList.add('mobile-modal');

            // Adjust modal position if keyboard is visible
            if (this.isKeyboardVisible) {
                modal.querySelector('.modal-dialog').classList.add('keyboard-visible');
            }

            // Focus management
            setTimeout(() => {
                const firstFocusable = modal.querySelector('input, select, textarea, button:not(.btn-close)');
                if (firstFocusable) {
                    firstFocusable.focus();
                }
            }, 100);
        },

        handleModalHide: function(modal) {
            // Restore body scroll
            document.body.style.overflow = '';

            // Remove mobile-specific classes
            modal.classList.remove('mobile-modal');
            modal.querySelector('.modal-dialog')?.classList.remove('keyboard-visible');
        },

        handleOffcanvasShow: function(offcanvas) {
            // Add mobile-specific behavior
            offcanvas.classList.add('mobile-offcanvas');

            // Prevent body scroll
            document.body.style.overflow = 'hidden';

            // Handle keyboard visibility
            if (this.isKeyboardVisible) {
                offcanvas.classList.add('keyboard-visible');
            }

            // Focus management
            setTimeout(() => {
                const firstFocusable = offcanvas.querySelector('input, select, textarea, button:not(.btn-close)');
                if (firstFocusable) {
                    firstFocusable.focus();
                }
            }, 100);
        },

        handleOffcanvasHide: function(offcanvas) {
            // Restore body scroll
            document.body.style.overflow = '';

            // Remove mobile-specific classes
            offcanvas.classList.remove('mobile-offcanvas', 'keyboard-visible');
        },

        handleInitialState: function() {
            // Set initial mobile classes
            this.detectDevice();

            // Handle any open modals or offcanvas on page load
            const openModals = document.querySelectorAll('.modal.show');
            const openOffcanvas = document.querySelectorAll('.offcanvas.show');

            openModals.forEach(modal => this.handleModalShow(modal));
            openOffcanvas.forEach(panel => this.handleOffcanvasShow(panel));
        },

        handleResize: function() {
            // Update offcanvas width on resize
            const offcanvasPanels = document.querySelectorAll('.offcanvas-end');
            offcanvasPanels.forEach(panel => {
                if (this.isMobile) {
                    panel.style.width = '100%';
                } else {
                    panel.style.width = '';
                }
            });

            // Update modal positioning
            const modals = document.querySelectorAll('.modal.show');
            modals.forEach(modal => {
                const dialog = modal.querySelector('.modal-dialog');
                if (this.isMobile) {
                    dialog.style.margin = '8px';
                    dialog.style.maxWidth = 'calc(100vw - 16px)';
                } else {
                    dialog.style.margin = '';
                    dialog.style.maxWidth = '';
                }
            });
        },

        handleOrientationChange: function() {
            // Handle orientation-specific adjustments
            const modals = document.querySelectorAll('.modal.show');
            const offcanvas = document.querySelectorAll('.offcanvas.show');

            // Adjust heights and spacing for landscape mode
            if (this.orientation === 'landscape' && this.isMobile) {
                modals.forEach(modal => {
                    const header = modal.querySelector('.modal-header');
                    const footer = modal.querySelector('.modal-footer');
                    if (header) header.style.minHeight = '48px';
                    if (footer) footer.style.padding = '8px 16px';
                });

                offcanvas.forEach(panel => {
                    const header = panel.querySelector('.offcanvas-header');
                    if (header) header.style.minHeight = '48px';
                });
            } else {
                // Reset to default
                modals.forEach(modal => {
                    const header = modal.querySelector('.modal-header');
                    const footer = modal.querySelector('.modal-footer');
                    if (header) header.style.minHeight = '';
                    if (footer) footer.style.padding = '';
                });

                offcanvas.forEach(panel => {
                    const header = panel.querySelector('.offcanvas-header');
                    if (header) header.style.minHeight = '';
                });
            }
        },

        // Utility methods
        scrollToElement: function(element, offset = 0) {
            if (!element) return;

            const elementTop = element.offsetTop - offset;
            const container = element.closest('.modal-body, .offcanvas-body') || window;

            if (container === window) {
                window.scrollTo({
                    top: elementTop,
                    behavior: 'smooth'
                });
            } else {
                container.scrollTo({
                    top: elementTop,
                    behavior: 'smooth'
                });
            }
        },

        // Public API
        isMobileDevice: function() {
            return this.isMobile;
        },

        isKeyboardOpen: function() {
            return this.isKeyboardVisible;
        },

        getCurrentOrientation: function() {
            return this.orientation;
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => MobileResponsive.init());
    } else {
        MobileResponsive.init();
    }

    // Expose to global scope for external access
    window.MobileResponsive = MobileResponsive;

    // Enhanced touch event handling for better mobile experience
    const TouchEnhancements = {
        init: function() {
            this.setupTouchFeedback();
            this.setupSwipeGestures();
        },

        setupTouchFeedback: function() {
            // Add visual feedback for touch interactions
            document.addEventListener('touchstart', (e) => {
                const target = e.target.closest('button, .btn, [role="button"], a');
                if (target && !target.disabled) {
                    target.classList.add('touch-active');
                }
            });

            document.addEventListener('touchend', (e) => {
                const target = e.target.closest('button, .btn, [role="button"], a');
                if (target) {
                    setTimeout(() => {
                        target.classList.remove('touch-active');
                    }, 150);
                }
            });

            document.addEventListener('touchcancel', (e) => {
                const target = e.target.closest('button, .btn, [role="button"], a');
                if (target) {
                    target.classList.remove('touch-active');
                }
            });
        },

        setupSwipeGestures: function() {
            // Basic swipe gesture detection for closing modals/offcanvas
            let startX, startY, startTime;

            document.addEventListener('touchstart', (e) => {
                const touch = e.touches[0];
                startX = touch.clientX;
                startY = touch.clientY;
                startTime = Date.now();
            });

            document.addEventListener('touchend', (e) => {
                if (!startX || !startY) return;

                const touch = e.changedTouches[0];
                const endX = touch.clientX;
                const endY = touch.clientY;
                const endTime = Date.now();

                const deltaX = endX - startX;
                const deltaY = endY - startY;
                const deltaTime = endTime - startTime;

                // Check if it's a swipe (fast movement)
                if (deltaTime < 300 && Math.abs(deltaX) > 50) {
                    const target = e.target.closest('.offcanvas, .modal');

                    if (target) {
                        // Swipe right to close offcanvas from left
                        if (deltaX > 0 && target.classList.contains('offcanvas-start')) {
                            const offcanvasInstance = bootstrap.Offcanvas.getInstance(target);
                            if (offcanvasInstance) offcanvasInstance.hide();
                        }

                        // Swipe left to close offcanvas from right
                        if (deltaX < 0 && target.classList.contains('offcanvas-end')) {
                            const offcanvasInstance = bootstrap.Offcanvas.getInstance(target);
                            if (offcanvasInstance) offcanvasInstance.hide();
                        }
                    }
                }

                // Reset
                startX = startY = null;
            });
        }
    };

    // Initialize touch enhancements
    TouchEnhancements.init();

})();
