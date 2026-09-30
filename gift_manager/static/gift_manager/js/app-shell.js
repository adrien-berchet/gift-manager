/**
 * Application shell: navbar offset, offcanvas/modal coordination, toasts,
 * HTMX form handling and the delete confirmation flow.
 */
(function () {
    const config = window.GiftManager || {};
    const i18n = config.i18n || {};
    const getCookie = config.getCookie;

    // Dynamically adjust body padding to match navbar height
    function adjustBodyPadding() {
        const navbar = document.querySelector('.navbar');
        if (navbar) {
            const navbarHeight = navbar.offsetHeight;
            document.body.style.paddingTop = navbarHeight + 'px';
        }
    }

    // Adjust on page load
    document.addEventListener('DOMContentLoaded', adjustBodyPadding);

    // Adjust on window resize for responsive navbar
    window.addEventListener('resize', adjustBodyPadding);

    // Modern UX Interface Event System
    (function() {
        // Global event handlers for modal and offcanvas coordination

        // Modal event handlers
        document.addEventListener('modal:show', function(e) {
            const modal = new bootstrap.Modal(document.getElementById('confirmModal'));
            modal.show();
        });

        document.addEventListener('modal:close', function(e) {
            const modal = bootstrap.Modal.getInstance(document.getElementById('confirmModal'));
            if (modal) modal.hide();
        });

        // Offcanvas event handlers
        let lastOffcanvasCloseAt = 0;
        let lastListUpdateAt = 0;

        document.addEventListener('offcanvas:show', function(e) {
            const target = e.detail?.target || 'editPanel';
            const offcanvas = bootstrap.Offcanvas.getOrCreateInstance(document.getElementById(target));
            offcanvas.show();
        });

        document.addEventListener('offcanvas:close', function(e) {
            lastOffcanvasCloseAt = Date.now();
            const target = e.detail?.target || 'editPanel';
            const panel = document.getElementById(target);
            if (!panel) return;
            panel.dataset.skipUnsavedPrompt = 'true';
            if (window.UnsavedChanges?.clearUnsavedChanges) {
                window.UnsavedChanges.clearUnsavedChanges();
            }
            resetPanelLoadingState(target);
            const offcanvas = bootstrap.Offcanvas.getOrCreateInstance(panel);
            if (offcanvas) {
                panel.addEventListener('hidden.bs.offcanvas', function() {
                    delete panel.dataset.skipUnsavedPrompt;
                }, { once: true });
                offcanvas.hide();
            }
        });

        // List update event handler
        document.addEventListener('list:update', function(e) {
            lastListUpdateAt = Date.now();
            // Trigger HTMX refresh of list containers
            const listContainers = document.querySelectorAll('[data-list-container]');
            listContainers.forEach(container => {
                htmx.trigger(container, 'refresh');
            });
        });

        // Notification system
        document.addEventListener('showNotification', function(e) {
            const data = e.detail;
            showNotification(data.message, data.type || 'info');
        });

        function escapeNotificationHtml(text) {
            const div = document.createElement('div');
            div.textContent = String(text || '');
            return div.innerHTML;
        }

        // Global notification function
        window.showNotification = function(message, type = 'info') {
            // Create toast notification
            const toastContainer = document.getElementById('toastContainer') || createToastContainer();

            const toastId = 'toast-' + Date.now();
            const iconClass = {
                'success': 'fas fa-check-circle text-success',
                'error': 'fas fa-exclamation-circle text-danger',
                'warning': 'fas fa-exclamation-triangle text-warning',
                'info': 'fas fa-info-circle text-info'
            }[type] || 'fas fa-info-circle text-info';

            const toastHtml = `
                <div id="${toastId}" class="toast align-items-center border-0" role="alert" aria-live="assertive" aria-atomic="true">
                    <div class="d-flex">
                        <div class="toast-body d-flex align-items-center">
                            <i class="${iconClass} me-2"></i>
                            ${escapeNotificationHtml(message)}
                        </div>
                        <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                    </div>
                </div>
            `;

            toastContainer.insertAdjacentHTML('beforeend', toastHtml);
            const toastElement = document.getElementById(toastId);
            const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
            toast.show();

            // Remove toast element after it's hidden
            toastElement.addEventListener('hidden.bs.toast', function() {
                toastElement.remove();
            });
        };

        function createToastContainer() {
            const container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1055';
            document.body.appendChild(container);
            return container;
        }

        function isManagedForm(elt) {
            return elt && elt.tagName === 'FORM' && elt.dataset.formType;
        }

        function focusFirstFormError(container) {
            if (!container) return;
            const focusTarget = container.querySelector(
                '.form-error-summary, .is-invalid, .invalid-feedback, .errorlist, [aria-invalid="true"]'
            );

            if (focusTarget) {
                if (!focusTarget.hasAttribute('tabindex')) {
                    focusTarget.setAttribute('tabindex', '-1');
                }
                focusTarget.focus({ preventScroll: true });
                focusTarget.scrollIntoView({ block: 'nearest' });
            }
        }

        function restoreLoadingState(trigger) {
            if (trigger && trigger.tagName === 'BUTTON' && trigger.dataset.originalText) {
                trigger.disabled = false;
                trigger.innerHTML = trigger.dataset.originalText;
                delete trigger.dataset.originalText;
            }
        }

        function resetPanelLoadingState(target) {
            const panel = document.getElementById(target);
            const loadingId = target === 'detailPanel' ? 'detailLoading' : 'offcanvasLoading';
            const contentId = target === 'detailPanel' ? 'detailContent' : 'offcanvasContent';
            const loading = document.getElementById(loadingId);
            const content = document.getElementById(contentId);

            if (panel) {
                panel.classList.remove('is-saving');
            }
            if (loading) {
                loading.classList.add('d-none');
            }
            if (content) {
                content.classList.remove('d-none');
            }
        }

        function parseHxTriggerEvents(headerValue) {
            if (!headerValue) return {};

            const trimmed = headerValue.trim();
            if (trimmed.startsWith('{')) {
                try {
                    return JSON.parse(trimmed);
                } catch (error) {
                    console.error('Could not parse HX-Trigger header:', error);
                    return {};
                }
            }

            return trimmed
                .split(',')
                .map((eventName) => eventName.trim())
                .filter(Boolean)
                .reduce((events, eventName) => {
                    events[eventName] = {};
                    return events;
                }, {});
        }

        function dispatchManagedFormTriggerFallback(xhr) {
            const events = parseHxTriggerEvents(xhr.getResponseHeader('HX-Trigger'));
            const hasOffcanvasClose = Object.prototype.hasOwnProperty.call(events, 'offcanvas:close');
            const hasListUpdate = Object.prototype.hasOwnProperty.call(events, 'list:update');

            if (!hasOffcanvasClose && !hasListUpdate) return;

            window.setTimeout(function() {
                const nativeEventWindowMs = 250;
                const now = Date.now();

                if (hasOffcanvasClose && now - lastOffcanvasCloseAt > nativeEventWindowMs) {
                    document.dispatchEvent(new CustomEvent('offcanvas:close', {
                        detail: events['offcanvas:close'] || {}
                    }));
                }

                if (hasListUpdate && now - lastListUpdateAt > nativeEventWindowMs) {
                    document.dispatchEvent(new CustomEvent('list:update', {
                        detail: events['list:update'] || {}
                    }));
                }
            }, 50);
        }

        // Backwards-compatible entry point for older partials. Current form partials use HX-Trigger.
        window.handleFormResponse = function(event) {
            const xhr = event.detail.xhr;
            const target = event.detail.target;

            if (xhr.status >= 200 && xhr.status < 300) {
                return;
            }

            if (xhr.status === 400 || xhr.status === 422) {
                focusFirstFormError(target);
            } else if (xhr.status === 403) {
                // Permission denied
                showNotification('You do not have permission to perform this action', 'error');

            } else if (xhr.status >= 500) {
                // Server error
                showNotification('A server error occurred. Please try again.', 'error');

            } else {
                // Other error
                showNotification('An error occurred. Please try again.', 'error');
            }
        };

        document.body.addEventListener('htmx:beforeSwap', function(e) {
            const xhr = e.detail.xhr;
            const elt = e.detail.elt;

            if (isManagedForm(elt) && (xhr.status === 400 || xhr.status === 422)) {
                e.detail.shouldSwap = true;
                e.detail.isError = false;
            }
        });

        // Handle form submissions with HTMX
        document.body.addEventListener('htmx:afterRequest', function(e) {
            const xhr = e.detail.xhr;
            const elt = e.detail.elt;

            // Check if this is a form submission (not a permission update)
            const isFormSubmission = isManagedForm(elt);
            const isPermissionUpdate = elt && elt.classList && elt.classList.contains('permission-select');

            if (isPermissionUpdate) {
                // Don't process as form submission
                return;
            }

            if (isFormSubmission) {
                if (xhr.status >= 500) {
                    // Server error
                    showNotification('A server error occurred. Please try again.', 'error');
                } else if (e.detail.successful) {
                    dispatchManagedFormTriggerFallback(xhr);
                }
            }

            // Remove loading states from buttons
            restoreLoadingState(e.detail.elt);
        });

        document.body.addEventListener('htmx:afterSwap', function(e) {
            const xhr = e.detail.xhr;
            if (xhr && (xhr.status === 400 || xhr.status === 422) && isManagedForm(e.detail.elt)) {
                // outerHTML swaps leave target pointing at the detached old form.
                focusFirstFormError(e.detail.elt);
            }
        });

        // Enhanced HTMX configuration for modern UX
        document.body.addEventListener('htmx:beforeRequest', function(e) {
            // Add loading states to buttons and forms
            const trigger = e.detail.elt;
            if (trigger.tagName === 'BUTTON') {
                trigger.disabled = true;
                const originalText = trigger.innerHTML;
                trigger.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>' + (trigger.dataset.loadingText || 'Loading...');
                trigger.dataset.originalText = originalText;
            }
        });

        // HTMX natively processes HX-Trigger headers and dispatches events.
        // No custom beforeSwap/afterSettle dispatch needed.

        // Initialize tooltips for quick action buttons
        function initializeTooltips() {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }

        // Initialize tooltips on page load
        document.addEventListener('DOMContentLoaded', initializeTooltips);

        // Re-initialize tooltips after HTMX updates
        document.body.addEventListener('htmx:afterSwap', initializeTooltips);

        // Delete confirmation: the single code path used by buttons, grids, the
        // detail panel and swipe actions (via GiftManager.confirmDelete).
        const deleteConfirmation = (function() {
            const modalEl = document.getElementById('confirmModal');
            const titleEl = document.getElementById('confirmModalLabel');
            const defaultTitle = titleEl ? titleEl.textContent : '';
            let lastTrigger = null;
            let deleteInFlight = false;
            let actionLabel = i18n.confirm;

            function confirmButton() {
                return document.getElementById('confirmAction');
            }

            function setButtonLabel(btn, label) {
                btn.disabled = false;
                btn.textContent = label;
                btn.className = 'btn btn-danger';
            }

            function resetModal() {
                deleteInFlight = false;
                const btn = confirmButton();
                if (btn) {
                    setButtonLabel(btn, i18n.confirm);
                }
                if (titleEl) {
                    titleEl.textContent = defaultTitle;
                }
                if (window.GridUtils && window.GridUtils.resetDeleteButtonStates) {
                    window.GridUtils.resetDeleteButtonStates();
                }
            }

            function hideDetailPanel(trigger) {
                const detailPanel = document.getElementById('detailPanel');
                if (detailPanel && trigger && detailPanel.contains(trigger)) {
                    const detailModal = bootstrap.Modal.getInstance(detailPanel);
                    if (detailModal) detailModal.hide();
                }
            }

            function failWith(status) {
                deleteInFlight = false;
                const btn = confirmButton();
                if (btn) {
                    setButtonLabel(btn, actionLabel);
                }
                showNotification(status === 403 ? i18n.deleteForbidden : i18n.deleteFailed, 'error');
            }

            function submitDelete(btn) {
                const form = document.getElementById('deleteForm');
                if (!form) {
                    console.error('Delete form not found');
                    failWith(0);
                    return;
                }
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>' + i18n.deleting;
                if (typeof htmx === 'undefined') {
                    form.submit();
                    return;
                }
                deleteInFlight = true;
                htmx.ajax('POST', form.action, {
                    values: new FormData(form),
                    swap: 'none',
                    headers: { 'HX-Request': 'true' }
                }).catch(function(error) {
                    console.error('HTMX request failed:', error);
                    failWith(0);
                });
            }

            // Failed delete requests re-enable the button instead of leaving a spinner.
            ['htmx:responseError', 'htmx:sendError'].forEach(function(eventName) {
                document.body.addEventListener(eventName, function(e) {
                    if (deleteInFlight) failWith(e.detail.xhr ? e.detail.xhr.status : 0);
                });
            });

            if (modalEl) {
                modalEl.addEventListener('hidden.bs.modal', function() {
                    resetModal();
                    if (lastTrigger && lastTrigger.isConnected) {
                        lastTrigger.focus({ preventScroll: true });
                    }
                    lastTrigger = null;
                });
            }

            /**
             * Load the delete confirmation for `url` into the shared confirm modal.
             * Always resolves; failures are reported with a toast.
             */
            function open(url, trigger) {
                if (!url) return Promise.resolve();
                lastTrigger = trigger || null;
                hideDetailPanel(trigger);
                return fetch(url, {
                    headers: {
                        'HX-Request': 'true',
                        'X-CSRFToken': getCookie('csrftoken')
                    }
                })
                .then(function(response) {
                    if (!response.ok) {
                        const error = new Error('HTTP ' + response.status);
                        error.status = response.status;
                        throw error;
                    }
                    return response.text();
                })
                .then(function(html) {
                    const body = document.getElementById('modalBody');
                    body.innerHTML = html;
                    // Each confirmation partial may name its own title and action button.
                    const meta = body.querySelector('[data-confirm-title], [data-confirm-label]');
                    actionLabel = (meta && meta.dataset.confirmLabel) || i18n.confirm;
                    if (titleEl) titleEl.textContent = (meta && meta.dataset.confirmTitle) || defaultTitle;
                    const btn = confirmButton();
                    if (btn) {
                        setButtonLabel(btn, actionLabel);
                        btn.onclick = function(e) {
                            e.preventDefault();
                            submitDelete(btn);
                        };
                    }
                    bootstrap.Modal.getOrCreateInstance(modalEl).show();
                })
                .catch(function(error) {
                    console.error('Error loading delete confirmation:', error);
                    showNotification(
                        error.status === 403 ? i18n.deleteForbidden : i18n.confirmationLoadFailed,
                        'error'
                    );
                });
            }

            return { open: open };
        })();
        window.GiftManager = window.GiftManager || {};
        window.GiftManager.confirmDelete = deleteConfirmation.open;

        document.addEventListener('click', function(e) {
            const button = e.target.closest('[data-action="delete"]');
            if (!button) return;
            e.preventDefault();
            deleteConfirmation.open(button.getAttribute('href') || button.dataset.deleteUrl, button);
        });

        // Clean up stale offcanvas state after fully hidden (only if Bootstrap missed cleanup)
        document.querySelectorAll('.offcanvas').forEach(function(offcanvasEl) {
            offcanvasEl.addEventListener('hidden.bs.offcanvas', function() {
                // Clean up is-loading class from content containers
                // (loading-states.js HTMX integration adds it but may not remove it
                // when form submission returns empty response and offcanvas closes)
                var contentContainers = offcanvasEl.querySelectorAll('.is-loading');
                contentContainers.forEach(function(el) {
                    el.classList.remove('is-loading');
                    delete el.dataset.loadingActive;
                });

                // Wait for Bootstrap to finish its own cleanup, then fix any leftovers
                setTimeout(function() {
                    if (!document.querySelector('.offcanvas.show')) {
                        document.querySelectorAll('.offcanvas-backdrop').forEach(function(backdrop) {
                            backdrop.remove();
                        });
                        document.body.classList.remove('offcanvas-open');
                        document.body.style.overflow = '';
                        document.body.style.paddingRight = '';
                    }
                }, 50);
            });
        });

        function processPanelForms(container) {
            htmx.process(container);

            const htmxForms = container.querySelectorAll('form[hx-post], form[hx-get]');
            htmxForms.forEach(form => {
                htmx.process(form);
            });

            if (window.FormInitializer) {
                const forms = container.querySelectorAll('form[data-form-type]');
                forms.forEach(form => {
                    window.FormInitializer.initForm(form);
                });
            }
        }

        function loadFormInPanel(formUrl, target = 'editPanel', options = {}) {
            if (!formUrl) return;

            if (!options.skipUnsavedCheck && window.UnsavedChanges?.confirmPanelReplacement) {
                const canLoad = window.UnsavedChanges.confirmPanelReplacement(target, function() {
                    loadFormInPanel(formUrl, target, { skipUnsavedCheck: true });
                });
                if (!canLoad) return;
            }

            showOffcanvasLoading(target);

            const panel = document.getElementById(target);
            const offcanvas = bootstrap.Offcanvas.getOrCreateInstance(panel);
            offcanvas.show();

            fetch(formUrl, {
                headers: {
                    'HX-Request': 'true',
                    'X-CSRFToken': getCookie('csrftoken')
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                return response.text();
            })
            .then(html => {
                const targetBody = target === 'detailPanel' ? 'detailContent' : 'offcanvasContent';
                const container = document.getElementById(targetBody);
                container.innerHTML = html;
                processPanelForms(container);
            })
            .catch(error => {
                console.error('Error loading form:', error);
                const errorMessage = error.message.includes('403')
                    ? 'You do not have permission to perform this action.'
                    : 'Error loading form. Please try again.';
                showOffcanvasError(errorMessage, target);
            });
        }

        // Ask for a reaction rating right after a gift plan is marked given or abandoned
        document.addEventListener('reaction:prompt', function(e) {
            const promptUrl = e.detail && e.detail.url;
            if (promptUrl) {
                loadFormInPanel(promptUrl, 'editPanel');
            }
        });

        // Handle edit/create buttons
        document.addEventListener('click', function(e) {
            if (e.target.matches('[data-action="edit"]') || e.target.closest('[data-action="edit"]')) {
                e.preventDefault();
                const button = e.target.matches('[data-action="edit"]') ? e.target : e.target.closest('[data-action="edit"]');
                const editUrl = button.getAttribute('href') || button.dataset.editUrl;
                const target = button.dataset.target || 'editPanel';

                loadFormInPanel(editUrl, target);
            }
        });

        // Handle create buttons
        document.addEventListener('click', function(e) {
            if (e.target.matches('[data-action="create"]') || e.target.closest('[data-action="create"]')) {
                e.preventDefault();
                const button = e.target.matches('[data-action="create"]') ? e.target : e.target.closest('[data-action="create"]');
                const createUrl = button.getAttribute('href') || button.dataset.createUrl;

                loadFormInPanel(createUrl, 'editPanel');
            }
        });

        // Handle detail view buttons
        document.addEventListener('click', function(e) {
            if (e.target.matches('[data-action="detail"]') || e.target.closest('[data-action="detail"]')) {
                e.preventDefault();
                const button = e.target.matches('[data-action="detail"]') ? e.target : e.target.closest('[data-action="detail"]');
                const detailUrl = button.getAttribute('href') || button.dataset.detailUrl;

                if (detailUrl) {
                    // Show loading state
                    showOffcanvasLoading('detailPanel');

                    // Show the panel first (reuse existing instance to avoid state corruption)
                    const modalInstance = bootstrap.Modal.getOrCreateInstance(document.getElementById('detailPanel'));
                    modalInstance.show();

                    // Load detail content
                    fetch(detailUrl, {
                        headers: {
                            'HX-Request': 'true',
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    })
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        return response.text();
                    })
                    .then(html => {
                        document.getElementById('detailContent').innerHTML = html;
                        hideOffcanvasLoading('detailPanel');
                    })
                    .catch(error => {
                        console.error('Error loading details:', error);
                        const errorMessage = error.message.includes('403')
                            ? 'You do not have permission to perform this action.'
                            : 'Error loading details. Please try again.';
                        showOffcanvasError(errorMessage, 'detailPanel');
                    });
                }
            }
        });


        // Helper functions for offcanvas loading states
        function showOffcanvasLoading(target) {
            const targetBody = target === 'detailPanel' ? 'detailContent' : 'offcanvasContent';
            const content = document.getElementById(targetBody);
            if (content) {
                content.innerHTML = `
                    <div class="loading-state">
                        <div class="loading-spinner"></div>
                        <p class="mt-3 text-muted">Loading...</p>
                    </div>
                `;
            }
        }

        function hideOffcanvasLoading(target) {
            // Loading is hidden when content is replaced
        }

        function showOffcanvasError(message, target) {
            const targetBody = target === 'detailPanel' ? 'detailContent' : 'offcanvasContent';
            const content = document.getElementById(targetBody);
            if (content) {
                content.innerHTML = `
                    <div class="error-state">
                        <div class="alert alert-danger" role="alert">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            ${message}
                        </div>
                    </div>
                `;
            }
        }

    })();
})();
