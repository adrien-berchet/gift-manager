/**
 * Offline Sync Manager for Gift Manager PWA
 * Handles form submissions and data synchronization when offline
 */

class OfflineSyncManager {
    constructor() {
        this.isOnline = this.checkOnlineStatus();
        this.setupEventListeners();
        this.updateConnectionStatus();
        console.log('[Offline Sync] Manager initialized');
    }

    /**
     * Check online status using multiple methods
     * @returns {boolean}
     */
    checkOnlineStatus() {
        // Use navigator.onLine as a quick first check
        // Note: This can be unreliable with DevTools offline simulation
        return navigator.onLine;
    }

    /**
     * Check actual network connectivity by attempting a fetch
     * navigator.onLine is unreliable with DevTools offline simulation
     * @returns {Promise<boolean>}
     */
    async checkActualConnectivity() {
        // DEBUG MODE: Force offline for localhost testing
        const debugOffline = localStorage.getItem('DEBUG_FORCE_OFFLINE');
        if (debugOffline === 'true') {
            console.log('[Offline Sync] 🔧 DEBUG MODE: Forcing offline (localStorage.DEBUG_FORCE_OFFLINE=true)');
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
            const timeoutId = setTimeout(() => controller.abort(), 2000); // 2 second timeout

            // Use the auth status endpoint for connectivity check (lightweight and always available)
            const lang = document.documentElement.lang || 'en';
            const response = await fetch(`/${lang}/api/auth/status/`, {
                method: 'GET',
                cache: 'no-store',
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            // Any response (even 401, 404, 500) means we have connectivity
            console.log('[Offline Sync] Connectivity check succeeded, status:', response.status);
            return true;
        } catch (error) {
            // Network error (Failed to fetch, aborted) means we're offline
            console.log('[Offline Sync] Connectivity check failed:', error.message);
            return false;
        }
    }

    /**
     * Set up event listeners for online/offline events and service worker messages
     */
    setupEventListeners() {
        window.addEventListener('online', () => this.handleOnline());
        window.addEventListener('offline', () => this.handleOffline());
        window.addEventListener('load', () => this.init());

        // Listen for messages from Service Worker
        navigator.serviceWorker?.addEventListener('message', (event) => {
            this.handleServiceWorkerMessage(event.data);
        });

        // Poll for connectivity changes every 5 seconds when we think we're offline
        // This helps detect when DevTools offline mode is disabled (events are unreliable)
        this.startConnectivityPolling();
    }

    /**
     * Poll for connectivity when offline (DevTools events can be unreliable)
     */
    startConnectivityPolling() {
        setInterval(async () => {
            // Only poll if we think we're offline but navigator says online
            if (!this.isOnline && navigator.onLine) {
                console.log('[Offline Sync] Polling: checking if we came back online...');
                const actuallyOnline = await this.checkActualConnectivity();
                if (actuallyOnline) {
                    console.log('[Offline Sync] Polling detected connectivity restored!');
                    await this.handleOnline();
                }
            }
        }, 5000); // Check every 5 seconds
    }

    /**
     * Initialize sync manager
     */
    async init() {
        await this.updatePendingCount();
        await this.updateConnectionStatus();
        await this.cleanupOldSyncItems();

        // Check actual connectivity (navigator.onLine can be unreliable)
        const actuallyOnline = await this.checkActualConnectivity();
        console.log('[Offline Sync] Init - navigator.onLine:', this.isOnline, 'actuallyOnline:', actuallyOnline);

        // Update our state based on actual connectivity
        this.isOnline = actuallyOnline;

        // Show offline banner if we're offline on page load
        if (!this.isOnline) {
            this.showOfflineBanner();
        }

        // If we're actually online, try to sync pending items
        if (this.isOnline) {
            await this.triggerSync();
        }
    }

    /**
     * Handle online event
     */
    async handleOnline() {
        console.log('[Offline Sync] Online event received, verifying connectivity...');

        // Verify actual connectivity before syncing
        const actuallyOnline = await this.checkActualConnectivity();
        if (!actuallyOnline) {
            console.log('[Offline Sync] Online event but connectivity check failed, waiting...');
            return;
        }

        console.log('[Offline Sync] Connection restored and verified');
        this.isOnline = true;
        await this.updateConnectionStatus();
        this.hideOfflineBanner();
        await this.triggerSync();
        this.showToast('Connection restored - syncing changes...', 'success');
    }

    /**
     * Handle offline event
     */
    async handleOffline() {
        console.log('[Offline Sync] Connection lost');
        this.isOnline = false;
        await this.updateConnectionStatus();
        this.showOfflineBanner();
        this.showToast('You are now offline - changes will be synced when reconnected', 'warning');
    }

    /**
     * Update connection status indicator
     */
    async updateConnectionStatus() {
        const statusEl = document.getElementById('connection-status');
        if (!statusEl) return;

        if (this.isOnline) {
            statusEl.innerHTML = '<i class="fas fa-wifi text-success"></i>';
            statusEl.className = 'd-none';  // Hide when online
            statusEl.setAttribute('title', 'Online');
        } else {
            statusEl.innerHTML = '<i class="fas fa-wifi-slash text-danger"></i> <span class="d-none d-sm-inline">Offline</span>';
            statusEl.className = 'badge bg-warning';
            statusEl.setAttribute('title', 'Offline - changes will be synced when reconnected');
        }
    }

    /**
     * Show offline banner
     */
    showOfflineBanner() {
        const banner = document.getElementById('offline-banner');
        if (banner) {
            banner.classList.remove('d-none');
            banner.classList.add('show');
            console.log('[Offline Sync] Offline banner shown');
        }
    }

    /**
     * Hide offline banner
     */
    hideOfflineBanner() {
        const banner = document.getElementById('offline-banner');
        if (banner) {
            banner.classList.remove('show');
            banner.classList.add('d-none');
            console.log('[Offline Sync] Offline banner hidden');
        }
    }

    /**
     * Update pending sync count indicator
     */
    async updatePendingCount() {
        const pending = await db.getPendingSyncItems();
        const countEl = document.getElementById('pending-sync-count');

        if (!countEl) return;

        if (pending.length > 0) {
            countEl.innerHTML = `<i class="fas fa-sync"></i> <span>${pending.length}</span>`;
            countEl.className = 'badge bg-info';
            countEl.setAttribute('title', `${pending.length} change(s) pending sync`);
            countEl.classList.remove('d-none');
        } else {
            countEl.classList.add('d-none');
        }
    }

    /**
     * Trigger background sync
     */
    async triggerSync() {
        if (!this.isOnline) {
            console.log('[Offline Sync] Cannot sync - offline');
            return;
        }

        const pending = await db.getPendingSyncItems();
        if (pending.length === 0) {
            console.log('[Offline Sync] No pending items to sync');
            return;
        }

        console.log(`[Offline Sync] Syncing ${pending.length} pending items`);

        // Try background sync first
        if ('serviceWorker' in navigator && 'sync' in navigator.serviceWorker) {
            try {
                const registration = await navigator.serviceWorker.ready;
                await registration.sync.register('sync-gift-manager-data');
                console.log('[Offline Sync] Background sync registered');
                return;
            } catch (error) {
                console.warn('[Offline Sync] Background sync not available, falling back to immediate sync');
            }
        }

        // Fallback: immediate sync
        await this.syncPendingItems();
    }

    /**
     * Sync pending items immediately (fallback for browsers without Background Sync API)
     */
    async syncPendingItems() {
        const pending = await db.getPendingSyncItems();

        // Sort by timestamp (FIFO)
        pending.sort((a, b) => a.timestamp - b.timestamp);

        let successCount = 0;
        let failCount = 0;

        let redirectUrl = null;

        for (const item of pending) {
            try {
                await db.updateSyncStatus(item.id, 'syncing');
                const result = await this.processSyncItem(item);
                await db.updateSyncStatus(item.id, 'success');
                successCount++;

                // Check if we should redirect (if this item was created on this page)
                if (item.type === 'create' && result && item.context && item.context.sourceUrl) {
                    // Check if we are still on the same page
                    if (window.location.href === item.context.sourceUrl || window.location.href.split('#')[0] === item.context.sourceUrl.split('#')[0]) {
                        const modelIdField = `${item.model}_id`;
                        const newId = result[modelIdField];
                        if (newId) {
                            const lang = item.context.lang || 'en';
                            // Construct detail URL: /en/gifts/<uuid>/
                            redirectUrl = `/${lang}/${item.model}s/${newId}/`;
                        }
                    }
                }

            } catch (error) {
                console.error('[Offline Sync] Sync failed:', error);
                await db.updateSyncStatus(item.id, 'failed', error.message);
                failCount++;

                // Stop syncing if too many failures
                if (failCount >= 3) {
                    console.error('[Offline Sync] Too many failures, stopping sync');
                    break;
                }
            }
        }

        await this.updatePendingCount();

        if (successCount > 0) {
            this.showToast(`${successCount} change(s) synced successfully`, 'success');
        }
        if (failCount > 0) {
            this.showToast(`${failCount} change(s) failed to sync`, 'danger');
        }

        // Redirect if applicable (for items created on a different page)
        if (redirectUrl) {
             console.log('[Offline Sync] Redirecting to new item:', redirectUrl);
             setTimeout(() => window.location.href = redirectUrl, 1500);
        }
        // Don't reload the page - it causes flickering and is unnecessary
        // The page already has the latest data from the form submission
    }

    /**
     * Process a single sync item
     * @param {object} item - Sync queue item
     */
    async processSyncItem(item) {
        const { type, model, objectId, data } = item;

        // Handle special case: relation status update
        if (type === 'status-update') {
            const url = data.updateUrl || '/relation_status_update/';
            const csrfToken = this.getCSRFToken();

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken
                },
                body: `relation_id=${data.relationId}&new_status=${data.newStatus}`
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            console.log('[Offline Sync] Successfully synced status update:', item);
            return;
        }

        // Build API endpoint for regular CRUD operations
        // Detect current language from document or URL (Django uses i18n_patterns)
        const lang = document.documentElement.lang?.split('-')[0] ||
                    window.location.pathname.match(/^\/(en|fr)\//)?.[1] ||
                    'en';

        // CRUD operations use SINGULAR URLs: /api/gift/, /api/person/, /api/event/, /api/relation/
        // List operations use PLURAL URLs: /api/gifts/, /api/persons/, /api/events/, /api/relations/
        let url = `/${lang}/api/${model}/`;  // Use singular for CRUD
        const method = type === 'create' ? 'POST' :
                      type === 'update' ? 'PUT' : 'DELETE';

        if (type === 'update' || type === 'delete') {
            url += `${objectId}/`;
        }

        if (type === 'delete') {
            url += 'delete/';
        }

        console.log('[Offline Sync] Syncing to URL:', url, 'Method:', method);

        // Get CSRF token
        const csrfToken = this.getCSRFToken();

        // Make request
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: type !== 'delete' ? JSON.stringify(data) : undefined
        });

        // Handle 409 Conflict - version mismatch
        if (response.status === 409) {
            const conflictData = await response.json();
            console.warn('[Offline Sync] Conflict detected:', conflictData);

            // Keep the item pending and show conflict modal
            await db.updateSyncStatus(item.id, 'conflict', 'Version conflict detected');
            await this.showConflictModal(item, conflictData);

            // Throw error to mark as failed for now (will be retried after user resolves)
            throw new Error(`CONFLICT: ${conflictData.message}`);
        }

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        // Handle create response - update local object with server ID
        if (type === 'create') {
            const serverData = await response.json();
            console.log('[Offline Sync] Server response for create:', serverData);
            if (serverData.data) {
                // Use atomic swap for tempID → serverID replacement
                const storeName = model + 's';
                const idField = `${model}_id`;

                // Prepare new entry with server data
                const newEntry = {
                    ...serverData.data
                };
                // Remove created_offline flag since it's now on server
                delete newEntry.created_offline;

                console.log('[Offline Sync] Atomic swapping', objectId, '→', newEntry[idField]);

                try {
                    // ATOMIC SWAP: tempID → serverID
                    if (objectId && objectId.startsWith('temp-')) {
                        await window.giftManagerDB.atomicSwapId(storeName, objectId, newEntry);
                        console.log('[Offline Sync] ✓ Atomically swapped temp ID:', objectId, '→', newEntry[idField]);
                    } else {
                        // Not a temp ID, just add (shouldn't happen but handle gracefully)
                        await db.put(storeName, newEntry);
                        console.log('[Offline Sync] Added new entry (no temp ID):', newEntry[idField]);
                    }

                    // Verify the entry was actually written
                    const verifyEntry = await db.get(storeName, newEntry[idField]);
                    if (verifyEntry) {
                        console.log('[Offline Sync] ✓ Verified new entry exists in IndexedDB:', verifyEntry[idField]);
                    } else {
                        console.error('[Offline Sync] ✗ CRITICAL: Entry not found after atomic swap!');
                    }

                } catch (error) {
                    console.error('[Offline Sync] Failed atomic swap:', error);
                    // Mark operation as failed, will retry next sync
                    throw error;
                }

                // Return the new entry for potential redirection
                return newEntry;
            } else {
                console.warn('[Offline Sync] No data in server response:', serverData);
            }
        }

        // For updates, persist the merged data to IndexedDB so cache reflects server state
        if (type === 'update') {
            const storeName = model + 's';
            const idField = `${model}_id`;
            const existing = await db.get(storeName, objectId) || {};
            const merged = {
                ...existing,
                ...data,
                [idField]: objectId,
                modified: new Date().toISOString(),
            };

            try {
                await db.put(storeName, merged);
                console.log('[Offline Sync] Updated entry in IndexedDB after server sync:', merged[idField]);
            } catch (err) {
                console.warn('[Offline Sync] Failed to update entry in IndexedDB after update sync:', err);
            }
        }

        console.log('[Offline Sync] Successfully synced:', item);
        return null;
    }

    /**
     * Show conflict resolution modal
     * @param {object} queueItem - Queue item with local changes
     * @param {object} conflictData - Server response with conflict info
     */
    async showConflictModal(queueItem, conflictData) {
        const modal = document.getElementById('conflictModal');
        if (!modal) {
            console.error('[Offline Sync] Conflict modal not found in DOM');
            return;
        }

        // Store current conflict data for modal buttons
        window.currentConflictData = {
            queueItem,
            serverData: conflictData.server_data || {}
        };

        // Compute and display diff between local and server data
        this.displayConflictDiff(queueItem.data, conflictData.server_data || {});

        // Show the modal
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();

        // Setup one-time event listeners for buttons
        const modalElement = bootstrap.Modal.getInstance(modal)?._element || modal;

        // Remove old listeners
        const overwriteBtn = modal.querySelector('#conflictOverwriteBtn');
        const discardBtn = modal.querySelector('#conflictDiscardBtn');
        const discardAllBtn = modal.querySelector('#conflictDiscardAllBtn');

        // Create new handler functions
        const handleOverwrite = async () => {
            bsModal.hide();
            await this.resolveConflict(queueItem.id, 'overwrite');
        };

        const handleDiscard = async () => {
            bsModal.hide();
            await this.resolveConflict(queueItem.id, 'discard');
        };

        const handleDiscardAll = async () => {
            bsModal.hide();
            await this.resolveConflict(queueItem.id, 'discard-all');
        };

        // Add listeners
        overwriteBtn?.addEventListener('click', handleOverwrite);
        discardBtn?.addEventListener('click', handleDiscard);
        discardAllBtn?.addEventListener('click', handleDiscardAll);
    }

    /**
     * Display conflict diff in modal
     * @param {object} localData - Local changes
     * @param {object} serverData - Server version
     */
    displayConflictDiff(localData, serverData) {
        const tbody = document.getElementById('conflictDiffBody');
        if (!tbody) return;

        tbody.innerHTML = ''; // Clear existing rows

        // Get all field names from both objects
        const allFields = new Set([...Object.keys(localData), ...Object.keys(serverData)]);
        allFields.delete('offline');
        allFields.delete('synced');
        allFields.delete('modified');

        // Only show differing fields
        for (const field of allFields) {
            const localValue = localData[field];
            const serverValue = serverData[field];

            // Skip fields that haven't changed
            if (JSON.stringify(localValue) === JSON.stringify(serverValue)) {
                continue;
            }

            const row = document.createElement('tr');
            row.innerHTML = `
                <td class="diff-field-name">${this.formatFieldName(field)}</td>
                <td class="diff-your-change">
                    <div class="diff-value">${this.formatFieldValue(localValue)}</div>
                </td>
                <td class="diff-server-version">
                    <div class="diff-value">${this.formatFieldValue(serverValue)}</div>
                </td>
            `;
            tbody.appendChild(row);
        }
    }

    /**
     * Format field name for display
     * @param {string} field - Field name
     * @returns {string}
     */
    formatFieldName(field) {
        // Convert snake_case to Title Case
        return field
            .replace(/_/g, ' ')
            .split(' ')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
    }

    /**
     * Format field value for display
     * @param {any} value - Field value
     * @returns {string}
     */
    formatFieldValue(value) {
        if (value === null || value === undefined) {
            return '<em class="text-muted">(empty)</em>';
        }
        if (typeof value === 'boolean') {
            return value ? '<span class="badge bg-success">Yes</span>' : '<span class="badge bg-secondary">No</span>';
        }
        if (typeof value === 'object') {
            return JSON.stringify(value);
        }
        return this.escapeHtml(String(value));
    }

    /**
     * Resolve conflict based on user choice
     * @param {number} queueItemId - ID of the queue item
     * @param {string} action - Action to take: 'overwrite', 'discard', or 'discard-all'
     */
    async resolveConflict(queueItemId, action) {
        try {
            if (action === 'overwrite') {
                // Retry the sync with the same queue item
                console.log('[Offline Sync] Resolving conflict - overwriting server data');
                await db.updateSyncStatus(queueItemId, 'pending');
                this.showToast('Retrying sync with your changes...', 'info');
                await this.triggerSync();

            } else if (action === 'discard') {
                // Remove this specific queue item
                console.log('[Offline Sync] Resolving conflict - discarding local changes');
                await db.deleteSyncItem(queueItemId);
                this.showToast('Your changes were discarded', 'info');
                await this.updatePendingCount();

            } else if (action === 'discard-all') {
                // Remove all pending queue items
                console.log('[Offline Sync] Resolving conflict - discarding all pending changes');
                const pending = await db.getPendingSyncItems();
                for (const item of pending) {
                    await db.deleteSyncItem(item.id);
                }
                this.showToast('All pending changes were discarded', 'info');
                await this.updatePendingCount();
            }
        } catch (error) {
            console.error('[Offline Sync] Error resolving conflict:', error);
            this.showToast('Error resolving conflict: ' + error.message, 'danger');
        }
    }

    /**
     * Handle messages from Service Worker
     * @param {object} data - Message data from SW
     */
    handleServiceWorkerMessage(data) {
        if (!data || !data.type) return;

        console.log('[Offline Sync] Received SW message:', data.type);

        switch (data.type) {
            case 'SYNC_COMPLETE':
                this.handleSyncComplete(data);
                break;

            case 'SYNC_CONFLICT':
                this.handleSyncConflictFromSW(data);
                break;

            default:
                console.warn('[Offline Sync] Unknown message type:', data.type);
        }
    }

    /**
     * Handle sync completion message from Service Worker
     * @param {object} data - Message data
     */
    async handleSyncComplete(data) {
        console.log('[Offline Sync] Background sync completed:', data);
        const { success, failed } = data;

        if (success > 0) {
            this.showToast(`Synced ${success} change${success !== 1 ? 's' : ''}`, 'success');
        }

        if (failed > 0) {
            this.showToast(`${failed} change${failed !== 1 ? 's' : ''} had issues`, 'warning');
        }

        // Update pending count
        await this.updatePendingCount();

        // Refresh CSRF token after sync to ensure it's not stale
        await this.refreshCSRFToken();
    }

    /**
     * Handle conflict message from Service Worker
     * @param {object} data - Message data with conflict info
     */
    async handleSyncConflictFromSW(data) {
        console.log('[Offline Sync] Conflict message from SW:', data);

        const { queueItem, conflictData } = data;
        if (!queueItem || !conflictData) return;

        // Show the conflict modal to the user
        await this.showConflictModal(queueItem, conflictData);
    }

    /**
     * Get fresh CSRF token from DOM (or fetch if needed)
     * Called after offline sync to ensure token not stale
     * @returns {Promise<string|null>}
     */
    async refreshCSRFToken() {
        try {
            // 1. Try to get from DOM (meta tag)
            let token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (token) {
                console.log('[Offline Sync] Got CSRF token from DOM');
                this.lastCSRFToken = token;
                return token;
            }

            // 2. Try to get from cookie
            token = this.getCSRFToken();
            if (token) {
                console.log('[Offline Sync] Got CSRF token from cookie');
                this.lastCSRFToken = token;
                return token;
            }

            // 3. Fetch new token from server if available
            // Note: This requires a backend endpoint that returns CSRF token
            // For now, just log warning if not available
            console.warn('[Offline Sync] Could not refresh CSRF token (no endpoint)');
            return null;
        } catch (error) {
            console.error('[Offline Sync] Error refreshing CSRF token:', error);
            return null;
        }
    }

    /**
     * Get CSRF token from cookie
     * @returns {string}
     */
    getCSRFToken() {
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
     * Pluralize model name for API endpoints
     * Django API uses plural URLs (e.g., /api/relations/ not /api/relation/)
     * @param {string} model - Singular model name (e.g., 'relation')
     * @returns {string} - Plural model name (e.g., 'relations')
     */
    pluralizeModel(model) {
        const pluralMap = {
            'gift': 'gifts',
            'person': 'persons',
            'event': 'events',
            'relation': 'relations',
            'group': 'groups',
            'tag': 'tags',
            'status': 'statuses'
        };

        return pluralMap[model] || model + 's';
    }

    /**
     * Clean up old sync items (older than 30 days)
     */
    async cleanupOldSyncItems() {
        await db.clearOldSyncItems(30);
    }

    /**
     * Show toast notification
     * @param {string} message - Message to display
     * @param {string} type - Toast type (success, warning, danger, info)
     */
    showToast(message, type = 'info') {
        // Check if Bootstrap toast container exists
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            document.body.appendChild(container);
        }

        // Create toast element
        const toastEl = document.createElement('div');
        toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
        toastEl.setAttribute('role', 'alert');
        toastEl.setAttribute('aria-live', 'assertive');
        toastEl.setAttribute('aria-atomic', 'true');

        toastEl.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${this.escapeHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;

        container.appendChild(toastEl);

        // Show toast using Bootstrap
        const toast = new bootstrap.Toast(toastEl, {
            autohide: true,
            delay: 5000
        });
        toast.show();

        // Remove from DOM after hidden
        toastEl.addEventListener('hidden.bs.toast', () => {
            toastEl.remove();
        });
    }

    /**
     * Escape HTML to prevent XSS
     * @param {string} text
     * @returns {string}
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Handle form submission - intercept if offline
     * @param {Event} event - Form submit event
     * @param {string} model - Model name ('gift', 'person', 'event')
     * @param {string} type - Operation type ('create', 'update', 'delete')
     * @returns {Promise<boolean>} - True if handled offline, false otherwise
     */
    async handleFormSubmit(event, model, type, objectId = null) {
        // If online, let form submit normally
        if (this.isOnline) {
            return false;
        }

        // We're offline - prevent default and handle locally
        event.preventDefault();

        const form = event.target;
        const formData = new FormData(form);
        const data = Object.fromEntries(formData);

        // Generate temporary ID for creates
        if (type === 'create') {
            objectId = GiftManagerDB.generateTempUUID();
            data[`${model}_id`] = objectId;
            data.created_offline = true;
        }

        // Mark modification time
        data.modified = new Date().toISOString();

        // Store in local IndexedDB
        const storeName = model + 's';  // 'gift' -> 'gifts'
        if (type === 'create') {
            await db.add(storeName, data);
        } else if (type === 'update') {
            await db.update(storeName, data);
        } else if (type === 'delete') {
            await db.delete(storeName, objectId);
        }

        // Add to sync queue
        await db.addToSyncQueue({
            type: type,
            model: model,
            objectId: objectId,
            data: data,
            context: { sourceUrl: window.location.href, lang: document.documentElement.lang }
        });

        // Update pending count
        await this.updatePendingCount();

        // Show success message
        this.showToast(`${model.charAt(0).toUpperCase() + model.slice(1)} ${type}d offline - will sync when reconnected`, 'info');

        // When offline, don't navigate - navigation will fail
        // The browser can't load pages while offline even if they're cached
        // because we're already on a page and attempting navigation causes chrome-error
        console.log('[Offline Sync] Staying on current page (offline mode)');

        return true;
    }

    /**
     * Handle relation status update - queue if offline
     * @param {string} relationId - Relation ID
     * @param {string} newStatus - New status ID
     * @param {string} updateUrl - URL to update status
     * @returns {Promise<boolean>} - True if handled offline, false if should proceed online
     */
    async handleStatusUpdate(relationId, newStatus, updateUrl) {
        // If online, let it proceed normally
        if (this.isOnline) {
            return false;
        }

        // We're offline - queue the status update
        await db.addToSyncQueue({
            type: 'status-update',
            model: 'relation',
            objectId: relationId,
            data: {
                relationId: relationId,
                newStatus: newStatus,
                updateUrl: updateUrl
            }
        });

        // Update pending count
        await this.updatePendingCount();

        // Show success message
        this.showToast('Status updated offline - will sync when reconnected', 'info');

        // Return true to indicate we handled it
        return true;
    }

    /**
     * Trigger logout and clear sensitive caches
     * Called when user clicks logout or auth expires
     */
    async triggerLogoutCleanup() {
        console.log('[Offline Sync] Triggering logout cleanup...');

        try {
            // 1. Clear local IndexedDB sensitive stores (user data)
            if (window.giftManagerDB) {
                await window.giftManagerDB.ready;

                // Delete stores containing user data
                const storesToClear = [
                    'gifts',
                    'persons',
                    'events',
                    'relations',
                    'groups',
                    'tags'
                ];

                for (const storeName of storesToClear) {
                    try {
                        const items = await window.giftManagerDB.getAll(storeName);
                        for (const item of items) {
                            // Get the ID key (usually store-specific like 'gift_id')
                            const idKey = this.getIdKeyForStore(storeName);
                            await window.giftManagerDB.delete(storeName, item[idKey]);
                        }
                        console.log(`[Offline Sync] Cleared ${storeName}`);
                    } catch (error) {
                        console.error(`[Offline Sync] Error clearing ${storeName}:`, error);
                    }
                }

                // Clear sync queue
                try {
                    const queue = await window.giftManagerDB.getAll('syncQueue');
                    for (const item of queue) {
                        await window.giftManagerDB.delete('syncQueue', item.id);
                    }
                    console.log('[Offline Sync] Cleared sync queue');
                } catch (error) {
                    console.error('[Offline Sync] Error clearing sync queue:', error);
                }
            }

            // 2. Clear localStorage PWA flags
            localStorage.removeItem('pwa_precache_complete');
            localStorage.removeItem('pwa_precache_timestamp');

            // 3. Send message to Service Worker to clear caches
            if (navigator.serviceWorker) {
                const registration = await navigator.serviceWorker.ready;
                if (registration.active) {
                    registration.active.postMessage({
                        type: 'CLEAR_SENSITIVE_CACHE'
                    });
                    console.log('[Offline Sync] Sent CLEAR_SENSITIVE_CACHE to SW');
                }
            }

            // 4. Unregister Service Workers
            if (navigator.serviceWorker) {
                const registrations = await navigator.serviceWorker.getRegistrations();
                for (const reg of registrations) {
                    await reg.unregister();
                }
                console.log('[Offline Sync] Unregistered service workers');
            }

            console.log('[Offline Sync] Logout cleanup complete');
            return true;
        } catch (error) {
            console.error('[Offline Sync] Error during logout cleanup:', error);
            return false;
        }
    }

    /**
     * Helper: Get ID key for a store
     * @param {string} storeName - Store name
     * @returns {string} - ID key field name
     */
    getIdKeyForStore(storeName) {
        const idKeys = {
            'gifts': 'gift_id',
            'persons': 'person_id',
            'events': 'event_id',
            'relations': 'relation_id',
            'groups': 'group_id',
            'tags': 'tag_id'
        };
        return idKeys[storeName] || 'id';
    }
}

// Initialize sync manager when DOM is ready
let syncManager;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        syncManager = new OfflineSyncManager();
        window.offlineSyncManager = syncManager;
    });
} else {
    syncManager = new OfflineSyncManager();
    window.offlineSyncManager = syncManager;
}

console.log('[Offline Sync] Module loaded');
