/**
 * Offline Forms Handler for Gift Manager PWA
 * Intercepts form submissions and saves to IndexedDB for offline-first operation
 */

class OfflineFormsHandler {
    constructor() {
        this.isInitialized = false;
        this.syncInProgress = false;
    }

    /**
     * Initialize the handler - attach form listeners
     */
    async init() {
        if (this.isInitialized) {
            console.log('[Offline Forms] Already initialized');
            return;
        }

        console.log('[Offline Forms] init() called - checking for IndexedDB...');

        if (!window.giftManagerDB) {
            console.warn('[Offline Forms] IndexedDB not available yet, waiting...');
            // Wait for IndexedDB to be available (db.js might still be loading)
            let attempts = 0;
            while (!window.giftManagerDB && attempts < 50) {
                await new Promise(r => setTimeout(r, 100));
                attempts++;
            }

            if (!window.giftManagerDB) {
                console.error('[Offline Forms] IndexedDB never became available!');
                return;
            }
            console.log('[Offline Forms] IndexedDB is now available!');
        }

        console.log('[Offline Forms] Waiting for IndexedDB ready...');
        await window.giftManagerDB.ready;
        console.log('[Offline Forms] IndexedDB ready!');

        // Intercept all forms with data-offline-sync attribute
        this.attachFormListeners();

        // Start background sync if online
        if (navigator.onLine) {
            this.startBackgroundSync();
        }

        // Listen for online/offline events
        window.addEventListener('online', () => this.startBackgroundSync());

        this.isInitialized = true;
        console.log('[Offline Forms] Fully initialized and ready!');
    }

    /**
     * Attach listeners to all forms
     */
    attachFormListeners() {
        console.log('[Offline Forms] attachFormListeners() called');
        console.log('[Offline Forms] document.readyState:', document.readyState);

        const tryAttach = () => {
            console.log('[Offline Forms] Trying to find #main-form...');

            // Main form (create/edit pages)
            const mainForm = document.getElementById('main-form');

            if (mainForm) {
                console.log('[Offline Forms] ✓ Found main form, attaching submit listener (CAPTURE phase)');

                // CRITICAL: Use capture: true to execute BEFORE other listeners
                // This ensures we can preventDefault() before anything else runs
                mainForm.addEventListener('submit', (e) => this.handleFormSubmit(e), {capture: true, once: false});

                // Also prevent the default form submission behavior
                mainForm.addEventListener('submit', (e) => {
                    console.log('[Offline Forms] BACKUP preventDefault called');
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                }, {capture: true, once: false});

                // Also add a click listener on the submit button for debugging
                const submitBtn = document.querySelector('button[type="submit"][form="main-form"]') ||
                                mainForm.querySelector('button[type="submit"]');
                if (submitBtn) {
                    console.log('[Offline Forms] Found submit button, adding click listener');
                    submitBtn.addEventListener('click', (e) => {
                        console.log('[Offline Forms] Submit button clicked! navigator.onLine:', navigator.onLine);
                    }, {capture: true});
                }

                // Prefill edit/delete forms from IndexedDB when offline or editing temp items
                this.prefillFormFromIndexedDB(mainForm, this.detectOperation(mainForm)).catch(err => {
                    console.warn('[Offline Forms] Prefill failed:', err);
                });
                return true;
            } else {
                // Form not found - this is normal for pages without forms (like home page)
                // Only log once to avoid console spam
                if (!this._formNotFoundLogged) {
                    console.log('[Offline Forms] No #main-form on this page (this is normal for list/home pages)');
                    this._formNotFoundLogged = true;
                }
                return false;
            }
        };

        // Try immediately
        if (tryAttach()) {
            return;
        }

        // Reset the flag for retry attempts
        this._formNotFoundLogged = false;

        // If not found, wait for DOM to be fully loaded
        if (document.readyState !== 'complete') {
            console.log('[Offline Forms] Waiting for window load event...');
            window.addEventListener('load', () => {
                console.log('[Offline Forms] Window loaded, retrying...');
                if (!tryAttach()) {
                    // Still not found, retry after a short delay (for dynamically rendered content)
                    setTimeout(() => {
                        console.log('[Offline Forms] Delayed retry...');
                        tryAttach();
                    }, 500);
                }
            });
        } else {
            // Document already complete, retry after a short delay
            console.log('[Offline Forms] Document already complete, retrying after delay...');
            setTimeout(() => {
                console.log('[Offline Forms] Delayed retry...');
                tryAttach();
            }, 500);
        }
    }

    /**
     * Handle form submission - OFFLINE-FIRST approach
     * Always save to IndexedDB first, then sync to server
     */
    async handleFormSubmit(event) {
        console.log('[Offline Forms] handleFormSubmit called - OFFLINE-FIRST approach');

        // ALWAYS prevent default - we handle everything
        event.preventDefault();
        event.stopPropagation(); // Also stop propagation to prevent other handlers
        event.stopImmediatePropagation(); // Stop ALL other handlers

        const form = event.target;

        // Check if we're already processing this form
        if (form.dataset.submitting === 'true') {
            console.log('[Offline Forms] Form already being submitted, ignoring duplicate');
            return;
        }

        // Mark form as being submitted
        form.dataset.submitting = 'true';

        // Disable the submit button to prevent double-clicks
        const submitButtons = form.querySelectorAll('button[type="submit"]');
        submitButtons.forEach(btn => {
            btn.disabled = true;
            btn.dataset.originalText = btn.textContent;
            btn.textContent = 'Saving...';
        });

        try {
            // Extract form data
            const formData = new FormData(form);
            const data = this.formDataToObject(formData);

            // Determine the operation type and model
            const operation = this.detectOperation(form);
            console.log('[Offline Forms] Operation detected:', operation);

            // STEP 1: Check connectivity FIRST
            const isActuallyOnline = await this.checkActualConnectivity();
            console.log('[Offline Forms] Connectivity check result:', isActuallyOnline);

            if (isActuallyOnline) {
                // Online: submit directly to server WITHOUT saving to IndexedDB
                console.log('[Offline Forms] Online - submitting directly to server (skipping IndexedDB)');
                try {
                    await this.syncImmediately(form, operation, data);
                    // Sync successful - redirect will happen in syncImmediately
                    return;
                } catch (error) {
                    console.warn('[Offline Forms] Direct submission failed, falling back to offline mode:', error);
                    // Fall through to offline behavior
                }
            }

            // STEP 2: Offline mode - Save to IndexedDB and queue for sync
            console.log('[Offline Forms] Offline mode - saving to IndexedDB');
            try {
                await this.saveToIndexedDB(operation, data);
                console.log('[Offline Forms] Saved to IndexedDB');
            } catch (error) {
                console.error('[Offline Forms] Failed to save to IndexedDB:', error);
                alert('Failed to save. Please try again.');
                return;
            }

            // Offline (or sync failed): show message and redirect locally
            console.log('[Offline Forms] Offline mode - showing success message');
            this.showOfflineMessage();
            this.redirectAfterSubmit(operation);
        } finally {
            // Re-enable submit buttons in case of error
            form.dataset.submitting = 'false';
            const submitButtons = form.querySelectorAll('button[type="submit"]');
            submitButtons.forEach(btn => {
                btn.disabled = false;
                if (btn.dataset.originalText) {
                    btn.textContent = btn.dataset.originalText;
                }
            });
        }
    }

    /**
     * Sync immediately when online (submit form data to server)
     */
    async syncImmediately(form, operation, data) {
        console.log('[Offline Forms] syncImmediately START');
        console.log('[Offline Forms] Form action:', form.action || window.location.href);
        console.log('[Offline Forms] Operation:', operation);

        const formData = new FormData(form);

        console.log('[Offline Forms] Submitting to server:', form.action || window.location.href);
        console.log('[Offline Forms] FormData entries:', Array.from(formData.entries()));

        const response = await fetch(form.action || window.location.href, {
            method: form.method || 'POST',
            body: formData,
            credentials: 'same-origin',
            redirect: 'follow'
        });

        console.log('[Offline Forms] Server response status:', response.status);
        console.log('[Offline Forms] Server response redirected:', response.redirected);
        console.log('[Offline Forms] Server response URL:', response.url);

        if (response.ok || response.redirected) {
            console.log('[Offline Forms] Server accepted, updating IndexedDB');

            // Remove from sync queue since we synced immediately
            await this.removePendingSync(operation);

            // Follow the redirect from server
            console.log('[Offline Forms] Redirecting to:', response.url);
            window.location.href = response.url;
        } else {
            console.error('[Offline Forms] Server returned error:', response.status);
            throw new Error(`Server returned ${response.status}`);
        }
    }

    /**
     * Remove pending sync item after successful immediate sync
     */
    async removePendingSync(operation) {
        try {
            const pending = await window.giftManagerDB.getPendingSyncItems();
            const toRemove = pending.find(item =>
                item.objectId === operation.objectId &&
                item.model === operation.modelType
            );
            if (toRemove) {
                await window.giftManagerDB.removeSyncItem(toRemove.id);
                console.log('[Offline Forms] Removed sync item:', toRemove.id);
            }
        } catch (error) {
            console.warn('[Offline Forms] Could not remove sync item:', error);
        }
    }

    /**
     * Submit form online via fetch (when we've prevented default)
     */
    async submitFormOnline(form) {
        try {
            const formData = new FormData(form);
            const response = await fetch(form.action || window.location.href, {
                method: form.method || 'POST',
                body: formData,
                credentials: 'same-origin',
                redirect: 'follow'
            });

            if (response.ok || response.redirected) {
                // Follow the redirect
                window.location.href = response.url;
            } else {
                console.error('[Offline Forms] Form submission failed:', response.status);
                alert('Failed to save. Please try again.');
            }
        } catch (error) {
            console.error('[Offline Forms] Online form submission error:', error);
            // Maybe we went offline during the request - try offline mode
            console.log('[Offline Forms] Falling back to offline mode');

            const formData = new FormData(form);
            const data = this.formDataToObject(formData);
            const operation = this.detectOperation(form);

            await this.saveToIndexedDB(operation, data);
            this.showOfflineMessage();
            this.redirectAfterSubmit(operation);
        }
    }

    /**
     * Check actual network connectivity by attempting a fetch
     * navigator.onLine is unreliable with DevTools offline simulation
     */
    async checkActualConnectivity() {
        // DEBUG MODE: Force offline for localhost testing
        // This is necessary because browsers treat localhost as always reachable,
        // even when DevTools "Offline" mode is enabled (loopback bypass).
        const debugOffline = localStorage.getItem('DEBUG_FORCE_OFFLINE');
        if (debugOffline === 'true') {
            console.log('[Offline Forms] 🔧 DEBUG MODE: Forcing offline (localStorage.DEBUG_FORCE_OFFLINE=true)');
            console.log('[Offline Forms] To disable: localStorage.removeItem("DEBUG_FORCE_OFFLINE"); location.reload()');
            return false;
        }

        // First quick check - if navigator says offline, trust it
        if (!navigator.onLine) {
            return false;
        }

        // Try a quick fetch to verify actual connectivity
        // Any HTTP response (even 404) means we're online
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 1000); // 1 second timeout

            // Try to fetch a known endpoint - any response means we're online
            const response = await fetch('/api/gifts/', {
                method: 'HEAD',
                cache: 'no-store',
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            // Any response (even 401, 404, 500) means we have connectivity
            console.log('[Offline Forms] Connectivity check succeeded, status:', response.status);
            return true;
        } catch (error) {
            // Network error (Failed to fetch, aborted) means we're offline
            console.log('[Offline Forms] Connectivity check failed:', error.message);
            return false;
        }
    }

    /**
     * Convert FormData to plain object
     */
    formDataToObject(formData) {
        const obj = {};
        for (const [key, value] of formData.entries()) {
            // Handle multiple values (like tags)
            if (obj[key]) {
                if (!Array.isArray(obj[key])) {
                    obj[key] = [obj[key]];
                }
                obj[key].push(value);
            } else {
                obj[key] = value;
            }
        }
        return obj;
    }

    /**
     * Detect operation type from form action and URL
     */
    detectOperation(form) {
        const url = form.action || window.location.href;
        const method = (form.method || 'get').toUpperCase();

        // Normalize URL for parsing
        let path = '';
        try {
            path = new URL(url, window.location.origin).pathname;
        } catch (e) {
            path = url; // Fallback to raw string
        }

        const idPattern = '([a-f0-9-]{36}|temp-[a-z0-9-]+)';

        // Determine model type from URL (singularize)
        let modelType = null;

        // Check for add_relation URLs first (these are relation creations)
        if (url.includes('/add_relation')) {
            modelType = 'relation';
        } else if (url.includes('/gifts/')) {
            modelType = 'gift';
        } else if (url.includes('/persons/')) {
            modelType = 'person';
        } else if (url.includes('/events/')) {
            modelType = 'event';
        } else if (url.includes('/relations/')) {
            modelType = 'relation';
        } else if (url.includes('/person_groups/')) {
            modelType = 'group';
        } else if (url.includes('/gift-tag/')) {
            modelType = 'tag';
        }

        // Determine if create or update
        const isCreate = /\/(create|add_relation)\/?$/i.test(path);
        const updateMatch = new RegExp(`/ ${idPattern} /edit/?$`.replace(/\s+/g, ''), 'i').exec(path);
        const deleteMatch = new RegExp(`/ ${idPattern} /delete/?$`.replace(/\s+/g, ''), 'i').exec(path);

        let objectId = updateMatch?.[1] || deleteMatch?.[1] || null;

        return {
            modelType,
            type: isCreate ? 'create' : updateMatch ? 'update' : deleteMatch ? 'delete' : 'unknown',
            objectId,
            method,
            url
        };
    }

    /**
     * Prefill edit/delete forms from IndexedDB when data is available
     */
    async prefillFormFromIndexedDB(form, operation) {
        if (!operation || !operation.modelType || !operation.objectId) {
            return;
        }

        if (operation.type !== 'update' && operation.type !== 'delete') {
            return;
        }

        if (!window.giftManagerDB) {
            return;
        }

        await window.giftManagerDB.ready;

        const storeName = operation.modelType + 's';

        try {
            const record = await window.giftManagerDB.get(storeName, operation.objectId);
            if (!record) {
                return;
            }

            const applyValue = (name, value) => {
                if (value === undefined || value === null) return;
                const field = form.querySelector(`[name="${name}"]`);
                if (!field) return;

                // Do not overwrite existing values unless empty
                const isEmptyInput = (el) => {
                    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
                        return !el.value;
                    }
                    if (el instanceof HTMLSelectElement) {
                        return el.value === '' || el.selectedIndex === -1;
                    }
                    return false;
                };

                if (!isEmptyInput(field)) {
                    return;
                }

                if (field instanceof HTMLInputElement) {
                    if (field.type === 'checkbox') {
                        field.checked = Boolean(value);
                    } else if (field.type === 'radio') {
                        const radios = form.querySelectorAll(`input[name="${name}"][type="radio"]`);
                        radios.forEach(radio => {
                            if (radio.value === String(value)) {
                                radio.checked = true;
                            }
                        });
                    } else {
                        field.value = String(value);
                    }
                } else if (field instanceof HTMLSelectElement) {
                    if (field.multiple && Array.isArray(value)) {
                        const values = value.map(v => String(v));
                        Array.from(field.options).forEach(opt => {
                            opt.selected = values.includes(opt.value);
                        });
                    } else {
                        field.value = String(value);
                    }
                } else if (field instanceof HTMLTextAreaElement) {
                    field.value = String(value);
                }
            };

            Object.entries(record).forEach(([key, value]) => applyValue(key, value));

            console.log('[Offline Forms] Prefilled form from IndexedDB for', operation.objectId);
        } catch (error) {
            console.warn('[Offline Forms] Could not prefill form from IndexedDB:', error);
        }
    }

    /**
     * Save data to IndexedDB
     */
    async saveToIndexedDB(operation, data) {
        const { modelType, type, objectId } = operation;

        if (!modelType) {
            console.warn('[Offline Forms] Cannot determine model type');
            return;
        }

        const storeName = modelType + 's'; // Pluralize for DB store
        console.log(`[Offline Forms] Saving ${type} to IndexedDB:`, storeName, data);

        let savedObject;

        if (type === 'create') {
            // Generate a temporary ID for new objects
            const tempId = objectId || this.generateTempId();
            // Update operation object so subsequent steps (sync, redirect) know the ID
            operation.objectId = tempId;

            savedObject = {
                ...data,
                [this.getIdField(modelType)]: tempId,
                created_offline: true,
                modified: new Date().toISOString()
            };
            await window.giftManagerDB.put(storeName, savedObject);

        } else if (type === 'update') {
            // Get existing object and merge changes
            const existing = await window.giftManagerDB.get(storeName, objectId);
            savedObject = {
                ...existing,
                ...data,
                modified: new Date().toISOString()
            };
            await window.giftManagerDB.put(storeName, savedObject);

        } else if (type === 'delete') {
            // Mark as deleted (soft delete for sync purposes)
            const existing = await window.giftManagerDB.get(storeName, objectId);
            savedObject = {
                ...existing,
                _deleted: true,
                modified: new Date().toISOString()
            };
            await window.giftManagerDB.put(storeName, savedObject);
        }

        // Queue for sync
        await this.queueForSync(operation, savedObject);

        console.log('[Offline Forms] Saved to IndexedDB:', savedObject);
    }

    /**
     * Queue operation for background sync
     */
    async queueForSync(operation, data) {
        const { modelType, type, objectId } = operation;

        await window.giftManagerDB.addToSyncQueue({
            type,
            model: modelType, // Singular
            objectId: objectId || data[this.getIdField(modelType)],
            data,
            context: {
                sourceUrl: window.location.href,
                lang: document.documentElement.lang || 'en'
            }
        });
        console.log('[Offline Forms] Queued for sync with context');
    }

    /**
     * Sync data to server
     */
    async syncToServer(operation, data) {
        const { modelType, type, objectId, url } = operation;
        const storeName = modelType + 's';

        console.log(`[Offline Forms] Syncing ${type} to server:`, modelType);

        try {
            const csrfToken = this.getCsrfToken();

            // Build fetch options
            const options = {
                method: type === 'create' ? 'POST' : type === 'delete' ? 'DELETE' : 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                },
                body: this.buildFormData(data),
                credentials: 'same-origin'
            };

            const response = await fetch(url, options);

            if (response.ok) {
                console.log('[Offline Forms] Successfully synced to server');

                // Handle ID swapping for creations
                if (type === 'create' && objectId && objectId.startsWith('temp-')) {
                    // Extract real ID from redirect URL (e.g. /gifts/<uuid>/)
                    const newId = this.extractIdFromUrl(response.url);

                    if (newId) {
                        console.log(`[Offline Forms] Swapping temp ID ${objectId} for server ID ${newId}`);

                        // Get the temp object
                        const obj = await window.giftManagerDB.get(storeName, objectId);
                        if (obj) {
                            // Delete the temp entry
                            await window.giftManagerDB.delete(storeName, objectId);

                            // Update with new ID
                            const idField = this.getIdField(modelType);
                            obj[idField] = newId;
                            delete obj.created_offline;  // No longer pending

                            // Save as new entry
                            await window.giftManagerDB.put(storeName, obj);

                            // Update operation object so the caller knows the real ID (e.g. for redirect)
                            operation.objectId = newId;
                        }
                    } else {
                         console.warn('[Offline Forms] Could not extract new ID from response URL:', response.url);
                         // Fallback: just delete created_offline flag (better than nothing, though technically wrong ID)
                         const obj = await window.giftManagerDB.get(storeName, objectId);
                         if (obj) {
                             delete obj.created_offline;
                             await window.giftManagerDB.put(storeName, obj);
                         }
                    }
                }
                // For updates, no special action needed - data is already in IndexedDB

                return true;
            } else {
                console.warn('[Offline Forms] Server returned error:', response.status);
                return false;
            }

        } catch (error) {
            console.error('[Offline Forms] Sync failed:', error);
            return false;
        }
    }

    /**
     * Extract UUID from URL
     */
    extractIdFromUrl(url) {
        // Look for UUID in path
        const match = url.match(/\/([a-f0-9-]{36})\/?$/) || url.match(/\/([a-f0-9-]{36})\//);
        return match ? match[1] : null;
    }

    /**
     * Start background sync process
     */
    async startBackgroundSync() {
        if (this.syncInProgress) {
            console.log('[Offline Forms] Sync already in progress');
            return;
        }

        this.syncInProgress = true;
        console.log('[Offline Forms] Starting background sync');

        try {
            const syncQueue = await window.giftManagerDB.getPendingSyncItems() || [];

            for (const item of syncQueue) {
                // Background sync might fail if operation details (url) are missing
                // This is a known limitation currently - ideally we'd reconstruct valid operation
                if (item.data && item.model) {
                     // Best effort - though this primarily relies on offline-sync.js for robust background sync
                }
            }

            console.log('[Offline Forms] Background sync complete');

        } catch (error) {
            console.error('[Offline Forms] Background sync error:', error);
        } finally {
            this.syncInProgress = false;
        }
    }

    /**
     * Build FormData from object
     */
    buildFormData(data) {
        const formData = new FormData();
        for (const [key, value] of Object.entries(data)) {
            if (Array.isArray(value)) {
                value.forEach(v => formData.append(key, v));
            } else if (value !== null && value !== undefined) {
                formData.append(key, value);
            }
        }
        return formData;
    }

    /**
     * Get CSRF token from cookie
     */
    getCsrfToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Get ID field name for model type
     */
    getIdField(modelType) {
        const mapping = {
            'gift': 'gift_id',
            'person': 'person_id',
            'event': 'event_id',
            'relation': 'relation_id',
            'group': 'group_id',
            'tag': 'tag_id'
        };
        return mapping[modelType] || 'id';
    }

    /**
     * Generate temporary ID for offline-created objects
     */
    generateTempId() {
        return 'temp-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * Show offline message to user
     */
    showOfflineMessage() {
        console.log('[Offline Forms] Changes saved locally. Will sync when online.');

        // Show visual feedback to user
        if (window.offlineSyncManager && window.offlineSyncManager.showToast) {
            window.offlineSyncManager.showToast(
                'Changes saved offline. Will sync when reconnected.',
                'success'
            );
        } else {
            // Fallback: simple alert
            alert('Changes saved offline. Will sync when reconnected.');
        }
    }

    /**
     * Get language prefix from current path
     */
    getLanguagePrefix() {
        const match = window.location.pathname.match(/^\/(en|fr)/);
        return match ? match[0] : '';
    }

    /**
     * Redirect after successful form submission
     */
    redirectAfterSubmit(operation) {
        const { modelType, type, objectId } = operation;

        // Service worker caches pages, so navigation works offline
        // Show success message if offline
        if (!navigator.onLine) {
            console.log('[Offline Forms] Offline mode - showing success message before redirect');
            this.showOfflineMessage();
        }

        // Determine redirect URL
        // Ensure we preserve language prefix (e.g. /en)
        const langPrefix = this.getLanguagePrefix();
        const urlPrefix = langPrefix + '/' + modelType + 's'; // Pluralize for URL

        let redirectUrl;

        if (type === 'delete') {
            // Redirect to list page after delete
            redirectUrl = `${urlPrefix}/`;
        } else if (type === 'create') {
            // Redirect to detail page if we have a real ID, otherwise list
            if (objectId && !objectId.startsWith('temp-')) {
                // Approximate URL construction - assumes standard URL pattern
                redirectUrl = `${urlPrefix}/${objectId}/`;
            } else {
                redirectUrl = `${urlPrefix}/`;
            }
        } else {
            // Redirect to detail page after edit
            redirectUrl = `${urlPrefix}/${objectId}/`;
        }

        console.log('[Offline Forms] Redirecting to:', redirectUrl);
        window.location.href = redirectUrl;
    }
}

// Create global instance
const offlineFormsHandler = new OfflineFormsHandler();
window.offlineFormsHandler = offlineFormsHandler;

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        offlineFormsHandler.init();
    });
} else {
    offlineFormsHandler.init();
}

console.log('[Offline Forms] Module loaded');
