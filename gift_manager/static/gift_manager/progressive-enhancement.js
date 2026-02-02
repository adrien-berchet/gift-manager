/**
 * Progressive Enhancement Fallbacks
 * Ensures all functionality works without JavaScript and provides graceful degradation
 * Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
 */

(function(window) {
    'use strict';

    /**
     * Configuration for progressive enhancement
     */
    const PROGRESSIVE_CONFIG = {
        // Feature detection timeouts
        timeouts: {
            jsLoad: 3000,      // 3 seconds to detect JS features
            ajaxTest: 2000,    // 2 seconds to test AJAX
            cssLoad: 1000      // 1 second to detect CSS features
        },

        // Fallback URLs for non-JS navigation
        fallbackUrls: {
            create: '?no_js=1',
            edit: '?no_js=1',
            delete: '?no_js=1&confirm=1'
        },

        // CSS classes for progressive enhancement
        classes: {
            jsEnabled: 'js-enabled',
            jsDisabled: 'js-disabled',
            ajaxEnabled: 'ajax-enabled',
            ajaxDisabled: 'ajax-disabled',
            fallbackMode: 'fallback-mode'
        }
    };

    /**
     * Feature detection utility
     */
    class FeatureDetector {
        constructor() {
            this.features = {
                javascript: true, // We're running JS, so this is true
                ajax: false,
                fetch: false,
                htmx: false,
                css3: false,
                localStorage: false,
                sessionStorage: false,
                history: false
            };

            this.detectFeatures();
        }

        /**
         * Detect available browser features
         */
        detectFeatures() {
            // AJAX support
            this.features.ajax = !!(window.XMLHttpRequest || window.ActiveXObject);

            // Fetch API support
            this.features.fetch = typeof fetch !== 'undefined';

            // HTMX support
            this.features.htmx = typeof htmx !== 'undefined';

            // CSS3 support
            this.features.css3 = this.detectCSS3();

            // Storage support
            this.features.localStorage = this.detectStorage('localStorage');
            this.features.sessionStorage = this.detectStorage('sessionStorage');

            // History API support
            this.features.history = !!(window.history && window.history.pushState);
        }

        /**
         * Detect CSS3 support
         */
        detectCSS3() {
            const testElement = document.createElement('div');
            const css3Properties = [
                'transform',
                'transition',
                'borderRadius',
                'boxShadow',
                'opacity'
            ];

            return css3Properties.some(prop => {
                return testElement.style[prop] !== undefined;
            });
        }

        /**
         * Detect storage support
         */
        detectStorage(type) {
            try {
                const storage = window[type];
                const testKey = '__test__';
                storage.setItem(testKey, 'test');
                storage.removeItem(testKey);
                return true;
            } catch (e) {
                return false;
            }
        }

        /**
         * Get feature support status
         */
        isSupported(feature) {
            return this.features[feature] || false;
        }

        /**
         * Get all features
         */
        getAllFeatures() {
            return { ...this.features };
        }
    }

    /**
     * Progressive enhancement manager
     */
    class ProgressiveEnhancement {
        constructor() {
            this.detector = new FeatureDetector();
            this.fallbacksEnabled = false;
            this.init();
        }

        /**
         * Initialize progressive enhancement
         */
        init() {
            this.addBodyClasses();
            this.setupFallbacks();
            this.enhanceExistingElements();
            this.setupGracefulDegradation();
            this.monitorConnectivity();

            console.log('[ProgressiveEnhancement] Initialized with features:', this.detector.getAllFeatures());
        }

        /**
         * Add CSS classes based on feature support
         */
        addBodyClasses() {
            const body = document.body;
            const features = this.detector.getAllFeatures();

            // Add JavaScript enabled class
            body.classList.add(PROGRESSIVE_CONFIG.classes.jsEnabled);
            body.classList.remove(PROGRESSIVE_CONFIG.classes.jsDisabled);

            // Add feature-specific classes
            Object.keys(features).forEach(feature => {
                const
           this.setupFormFallbacks();
            this.setupNavigationFallbacks();
            this.setupModalFallbacks();
            this.setupSearchFallbacks();
        }

        /**
         * Setup form fallbacks for non-AJAX environments
         */
        setupFormFallbacks() {
            // Handle forms that would normally use AJAX
            const ajaxForms = document.querySelectorAll('form[hx-post], form[data-ajax]');

            ajaxForms.forEach(form => {
                // Add hidden field to indicate non-JS submission
                if (!form.querySelector('input[name="no_js"]')) {
                    const hiddenField = document.createElement('input');
                    hiddenField.type = 'hidden';
                    hiddenField.name = 'no_js';
                    hiddenField.value = '1';
                    form.appendChild(hiddenField);
                }

                // Ensure form has proper action URL
                if (!form.action || form.action === window.location.href) {
                    const hxPost = form.getAttribute('hx-post');
                    if (hxPost) {
                        form.action = hxPost;
                    }
                }

                // Remove HTMX attributes if HTMX is not available
                if (!this.detector.isSupported('htmx')) {
                    this.removeHTMXAttributes(form);
                }
            });
        }

        /**
         * Setup navigation fallbacks
         */
        setupNavigationFallbacks() {
            // Convert AJAX navigation links to regular links
            const ajaxLinks = document.querySelectorAll('a[hx-get], a[data-ajax]');

            ajaxLinks.forEach(link => {
                // Ensure link has proper href
                if (!link.href || link.href === '#') {
                    const hxGet = link.getAttribute('hx-get');
                    if (hxGet) {
                        link.href = hxGet + PROGRESSIVE_CONFIG.fallbackUrls.edit;
                    }
                }

                // Remove HTMX attributes if not supported
                if (!this.detector.isSupported('htmx')) {
                    this.removeHTMXAttributes(link);
                }
            });

            // Handle quick action buttons
            this.setupQuickActionFallbacks();
        }

        /**
         * Setup quick action button fallbacks
         */
        setupQuickActionFallbacks() {
            const quickActions = document.querySelectorAll('[data-action]');

            quickActions.forEach(button => {
                const action = button.dataset.action;
                const entityId = button.dataset.entityId;

                // Ensure button has proper href or form action
                if (button.tagName === 'A' && (!button.href || button.href === '#')) {
                    button.href = this.getActionUrl(action, entityId);
                }

                // Add click handler for graceful degradation
                button.addEventListener('click', (e) => {
                    if (!this.detector.isSupported('htmx') || this.fallbacksEnabled) {
                        // Let the browser handle navigation normally
                        return true;
                    }
                });
            });
        }

        /**
         * Get fallback URL for actions
         */
        getActionUrl(action, entityId) {
            const baseUrl = window.location.pathname;
            const entityPath = baseUrl.replace(/\/$/, '');

            switch (action) {
                case 'edit':
                    return `${entityPath}/${entityId}/edit/${PROGRESSIVE_CONFIG.fallbackUrls.edit}`;
                case 'delete':
                    return `${entityPath}/${entityId}/delete/${PROGRESSIVE_CONFIG.fallbackUrls.delete}`;
                case 'detail':
                    return `${entityPath}/${entityId}/`;
                default:
                    return baseUrl;
            }
        }

        /**
         * Setup modal fallbacks
         */
        setupModalFallbacks() {
            // Convert modal triggers to regular links
            const modalTriggers = document.querySelectorAll('[data-bs-toggle="modal"]');

            modalTriggers.forEach(trigger => {
                if (!this.detector.isSupported('css3')) {
                    // Remove modal attributes and convert to regular link
                    trigger.removeAttribute('data-bs-toggle');
                    trigger.removeAttribute('data-bs-target');

                    // Add fallback URL
                    if (trigger.tagName === 'A' && trigger.dataset.action) {
                        const entityId = trigger.dataset.entityId;
                        trigger.href = this.getActionUrl(trigger.dataset.action, entityId);
                    }
                }
            });

            // Handle offcanvas fallbacks
            const offcanvasTriggers = document.querySelectorAll('[data-bs-toggle="offcanvas"]');

            offcanvasTriggers.forEach(trigger => {
                if (!this.detector.isSupported('css3')) {
                    trigger.removeAttribute('data-bs-toggle');
                    trigger.removeAttribute('data-bs-target');

                    if (trigger.tagName === 'A' && trigger.dataset.action) {
                        const entityId = trigger.dataset.entityId;
                        trigger.href = this.getActionUrl(trigger.dataset.action, entityId);
                    }
                }
            });
        }

        /**
         * Setup search fallbacks
         */
        setupSearchFallbacks() {
            const searchInputs = document.querySelectorAll('[data-search-target]');

            searchInputs.forEach(input => {
                const form = input.closest('form');
                if (form) {
                    // Ensure form has proper action for non-AJAX search
                    if (!form.action) {
                        form.action = window.location.pathname;
                    }

                    // Add search parameter name
                    if (!input.name) {
                        input.name = 'search';
                    }

                    // Remove real-time search if AJAX not supported
                    if (!this.detector.isSupported('ajax')) {
                        input.removeAttribute('data-search-target');

                        // Add submit button if not present
                        if (!form.querySelector('button[type="submit"], input[type="submit"]')) {
                            const submitBtn = document.createElement('button');
                            submitBtn.type = 'submit';
                            submitBtn.className = 'btn btn-primary';
                            submitBtn.textContent = 'Search';
                            input.parentNode.appendChild(submitBtn);
                        }
                    }
                }
            });
        }

        /**
         * Enhance existing elements with progressive enhancement
         */
        enhanceExistingElements() {
            // Add noscript alternatives
            this.addNoScriptAlternatives();

            // Enhance forms with better UX when JS is available
            this.enhanceFormsWithJS();

            // Add loading states only if supported
            if (this.detector.isSupported('css3')) {
                this.enableLoadingStates();
            }
        }

        /**
         * Add noscript alternatives for critical functionality
         */
        addNoScriptAlternatives() {
            // Add noscript message if not already present
            if (!document.querySelector('noscript.js-warning')) {
                const noscript = document.createElement('noscript');
                noscript.className = 'js-warning';
                noscript.innerHTML = `
                    <div class="alert alert-warning" role="alert">
                        <strong>JavaScript is disabled.</strong>
                        Some features may not work as expected, but all core functionality remains available.
                    </div>
                `;
                document.body.insertBefore(noscript, document.body.firstChild);
            }

            // Add fallback navigation for complex interactions
            const complexElements = document.querySelectorAll('.requires-js');
            complexElements.forEach(element => {
                if (!element.querySelector('.js-fallback')) {
                    const fallback = document.createElement('div');
                    fallback.className = 'js-fallback alert alert-info';
                    fallback.innerHTML = `
                        <p>This feature requires JavaScript. Please enable JavaScript or use the alternative links below:</p>
                        <a href="${window.location.pathname}" class="btn btn-primary">Refresh Page</a>
                    `;
                    element.appendChild(fallback);
                }
            });
        }

        /**
         * Enhance forms when JavaScript is available
         */
        enhanceFormsWithJS() {
            if (!this.detector.isSupported('ajax')) return;

            const forms = document.querySelectorAll('form');
            forms.forEach(form => {
                // Add client-side validation hints
                const requiredFields = form.querySelectorAll('[required]');
                requiredFields.forEach(field => {
                    if (!field.getAttribute('aria-describedby')) {
                        const helpId = `${field.id || field.name}-help`;
                        field.setAttribute('aria-describedby', helpId);

                        const helpText = document.createElement('small');
                        helpText.id = helpId;
                        helpText.className = 'form-text text-muted';
                        helpText.textContent = 'This field is required.';
                        field.parentNode.appendChild(helpText);
                    }
                });
            });
        }

        /**
         * Enable loading states only if CSS3 is supported
         */
        enableLoadingStates() {
            // This will be handled by the loading-states.js file
            // We just ensure it's only enabled when CSS3 is available
            document.body.classList.add('loading-states-enabled');
        }

        /**
         * Setup graceful degradation for when features fail
         */
        setupGracefulDegradation() {
            // Monitor for AJAX failures
            if (this.detector.isSupported('ajax')) {
                this.setupAjaxFallback();
            }

            // Monitor for CSS failures
            this.setupCSSFallback();

            // Setup timeout fallbacks
            this.setupTimeoutFallbacks();
        }

        /**
         * Setup AJAX fallback mechanisms
         */
        setupAjaxFallback() {
            let ajaxFailureCount = 0;
            const maxFailures = 3;

            // Listen for HTMX errors
            document.addEventListener('htmx:sendError', () => {
                ajaxFailureCount++;
                if (ajaxFailureCount >= maxFailures) {
                    this.enableFallbackMode('AJAX failures detected');
                }
            });

            document.addEventListener('htmx:responseError', () => {
                ajaxFailureCount++;
                if (ajaxFailureCount >= maxFailures) {
                    this.enableFallbackMode('AJAX response errors detected');
                }
            });

            // Test AJAX connectivity periodically
            setInterval(() => {
                this.testAjaxConnectivity();
            }, 30000); // Every 30 seconds
        }

        /**
         * Test AJAX connectivity
         */
        async testAjaxConnectivity() {
            if (!this.detector.isSupported('fetch')) return;

            try {
                const response = await fetch(window.location.href, {
                    method: 'HEAD',
                    cache: 'no-cache'
                });

                if (!response.ok) {
                    this.enableFallbackMode('Network connectivity issues');
                }
            } catch (error) {
                console.warn('[ProgressiveEnhancement] AJAX connectivity test failed:', error);
                this.enableFallbackMode('Network connectivity lost');
            }
        }

        /**
         * Setup CSS fallback mechanisms
         */
        setupCSSFallback() {
            // Test if critical CSS loaded
            setTimeout(() => {
                const testElement = document.createElement('div');
                testElement.className = 'test-css-load';
                testElement.style.position = 'absolute';
                testElement.style.left = '-9999px';
                document.body.appendChild(testElement);

                const computedStyle = window.getComputedStyle(testElement);
                const cssLoaded = computedStyle.position === 'absolute';

                document.body.removeChild(testElement);

                if (!cssLoaded) {
                    this.enableFallbackMode('CSS loading issues detected');
                }
            }, PROGRESSIVE_CONFIG.timeouts.cssLoad);
        }

        /**
         * Setup timeout fallbacks
         */
        setupTimeoutFallbacks() {
            // Fallback for slow-loading JavaScript features
            setTimeout(() => {
                if (typeof htmx === 'undefined' && document.querySelector('[hx-get], [hx-post]')) {
                    console.warn('[ProgressiveEnhancement] HTMX not loaded, enabling fallbacks');
                    this.enableFallbackMode('HTMX loading timeout');
                }
            }, PROGRESSIVE_CONFIG.timeouts.jsLoad);
        }

        /**
         * Enable fallback mode
         */
        enableFallbackMode(reason) {
            if (this.fallbacksEnabled) return;

            console.warn(`[ProgressiveEnhancement] Enabling fallback mode: ${reason}`);
            this.fallbacksEnabled = true;

            // Add fallback mode class
            document.body.classList.add(PROGRESSIVE_CONFIG.classes.fallbackMode);

            // Remove HTMX attributes from all elements
            this.removeAllHTMXAttributes();

            // Show fallback message
            this.showFallbackMessage(reason);

            // Disable enhanced features
            this.disableEnhancedFeatures();
        }

        /**
         * Remove HTMX attributes from element
         */
        removeHTMXAttributes(element) {
            const htmxAttributes = [
                'hx-get', 'hx-post', 'hx-put', 'hx-delete',
                'hx-target', 'hx-swap', 'hx-trigger',
                'hx-include', 'hx-indicator', 'hx-confirm'
            ];

            htmxAttributes.forEach(attr => {
                element.removeAttribute(attr);
            });
        }

        /**
         * Remove all HTMX attributes from document
         */
        removeAllHTMXAttributes() {
            const htmxElements = document.querySelectorAll('[hx-get], [hx-post], [hx-put], [hx-delete]');
            htmxElements.forEach(element => {
                this.removeHTMXAttributes(element);
            });
        }

        /**
         * Show fallback message to user
         */
        showFallbackMessage(reason) {
            const existingMessage = document.querySelector('.fallback-message');
            if (existingMessage) return;

            const message = document.createElement('div');
            message.className = 'alert alert-info fallback-message';
            message.innerHTML = `
                <strong>Enhanced features temporarily unavailable.</strong>
                The application is running in compatibility mode. All functionality remains available.
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;

            const container = document.querySelector('.container') || document.body;
            container.insertBefore(message, container.firstChild);
        }

        /**
         * Disable enhanced features
         */
        disableEnhancedFeatures() {
            // Disable real-time search
            const searchInputs = document.querySelectorAll('[data-search-target]');
            searchInputs.forEach(input => {
                input.removeAttribute('data-search-target');
            });

            // Disable inline editing
            const inlineEditable = document.querySelectorAll('[data-inline-edit]');
            inlineEditable.forEach(element => {
                element.removeAttribute('data-inline-edit');
            });

            // Disable dynamic filters
            const dynamicFilters = document.querySelectorAll('[data-dynamic-filter]');
            dynamicFilters.forEach(filter => {
                filter.removeAttribute('data-dynamic-filter');
            });
        }

        /**
         * Monitor network connectivity
         */
        monitorConnectivity() {
            if ('navigator' in window && 'onLine' in navigator) {
                window.addEventListener('online', () => {
                    console.log('[ProgressiveEnhancement] Network connectivity restored');
                    // Could re-enable features here if desired
                });

                window.addEventListener('offline', () => {
                    console.log('[ProgressiveEnhancement] Network connectivity lost');
                    this.enableFallbackMode('Network connectivity lost');
                });
            }
        }

        /**
         * Get current enhancement status
         */
        getStatus() {
            return {
                features: this.detector.getAllFeatures(),
                fallbacksEnabled: this.fallbacksEnabled,
                enhancementsActive: !this.fallbacksEnabled
            };
        }
    }

    /**
     * Initialize progressive enhancement when DOM is ready
     */
    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                window.ProgressiveEnhancement = new ProgressiveEnhancement();
            });
        } else {
            window.ProgressiveEnhancement = new ProgressiveEnhancement();
        }
    }

    // Auto-initialize
    init();

    // Expose classes for external use
    window.FeatureDetector = FeatureDetector;
    window.PROGRESSIVE_CONFIG = PROGRESSIVE_CONFIG;

})(window);
