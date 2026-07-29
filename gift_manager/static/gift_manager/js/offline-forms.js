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
            return;
        }

        if (!window.giftManagerDB) {
            console.warn("[Offline Forms] IndexedDB not available yet, waiting...");
            // Wait for IndexedDB to be available (db.js might still be loading)
            let attempts = 0;
            while (!window.giftManagerDB && attempts < 50) {
                await new Promise((r) => setTimeout(r, 100));
                attempts++;
            }

            if (!window.giftManagerDB) {
                console.error("[Offline Forms] IndexedDB never became available!");
                return;
            }
        }

        await window.giftManagerDB.ready;

        // Intercept all forms with data-offline-sync attribute
        this.attachFormListeners();

        // Start background sync if online
        if (navigator.onLine) {
            this.startBackgroundSync();
        }

        // Listen for online/offline events
        window.addEventListener("online", () => this.startBackgroundSync());

        this.isInitialized = true;
    }

    /**
     * Attach listeners to all forms
     */
    attachFormListeners() {
        const tryAttach = () => {
            // Main form (create/edit pages)
            const mainForm = document.getElementById("main-form");

            if (mainForm) {
                // CRITICAL: Use capture: true to execute BEFORE other listeners
                // This ensures we can preventDefault() before anything else runs
                mainForm.addEventListener("submit", (e) => this.handleFormSubmit(e), {
                    capture: true,
                    once: false,
                });

                // Also prevent the default form submission behavior
                mainForm.addEventListener(
                    "submit",
                    (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        e.stopImmediatePropagation();
                    },
                    { capture: true, once: false }
                );

                // Prefill edit/delete forms from IndexedDB when offline or editing temp items
                this.prefillFormFromIndexedDB(mainForm, this.detectOperation(mainForm)).catch(
                    (err) => {
                        console.warn("[Offline Forms] Prefill failed:", err);
                    }
                );
                return true;
            } else {
                // Form not found - this is normal for pages without forms (like home page)
                // Only log once to avoid console spam
                if (!this._formNotFoundLogged) {
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
        if (document.readyState !== "complete") {
            window.addEventListener("load", () => {
                if (!tryAttach()) {
                    // Still not found, retry after a short delay (for dynamically rendered content)
                    setTimeout(() => {
                        tryAttach();
                    }, 500);
                }
            });
        } else {
            // Document already complete, retry after a short delay
            setTimeout(() => {
                tryAttach();
            }, 500);
        }
    }

    /**
     * Handle form submission - OFFLINE-FIRST approach
     * Always save to IndexedDB first, then sync to server
     */
    async handleFormSubmit(event) {
        // ALWAYS prevent default - we handle everything
        event.preventDefault();
        event.stopPropagation(); // Also stop propagation to prevent other handlers
        event.stopImmediatePropagation(); // Stop ALL other handlers

        const form = event.target;

        // Check if we're already processing this form
        if (form.dataset.submitting === "true") {
            return;
        }

        // Mark form as being submitted
        form.dataset.submitting = "true";

        // Disable the submit button to prevent double-clicks
        const submitButtons = form.querySelectorAll('button[type="submit"]');
        submitButtons.forEach((btn) => {
            btn.disabled = true;
            btn.dataset.originalText = btn.textContent;
            btn.textContent = "Saving...";
        });

        try {
            // Extract form data
            const formData = new FormData(form);
            const data = this.formDataToObject(formData);

            // Determine the operation type and model
            const operation = this.detectOperation(form);

            // STEP 1: Check connectivity FIRST
            const isActuallyOnline = await this.checkActualConnectivity();

            if (isActuallyOnline) {
                // Online: submit directly to server WITHOUT saving to IndexedDB
                try {
                    await this.syncImmediately(form, operation, data);
                    // Sync successful - redirect will happen in syncImmediately
                    return;
                } catch (error) {
                    console.warn(
                        "[Offline Forms] Direct submission failed, falling back to offline mode:",
                        error
                    );
                    // Fall through to offline behavior
                }
            }

            // STEP 2: Offline mode - Save to IndexedDB and queue for sync
            try {
                await this.saveToIndexedDB(operation, data);
            } catch (error) {
                console.error("[Offline Forms] Failed to save to IndexedDB:", error);
                alert("Failed to save. Please try again.");
                return;
            }

            // Offline (or sync failed): show message and redirect locally
            this.showOfflineMessage();
            this.redirectAfterSubmit(operation);
        } finally {
            // Re-enable submit buttons in case of error
            form.dataset.submitting = "false";
            const submitButtons = form.querySelectorAll('button[type="submit"]');
            submitButtons.forEach((btn) => {
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
        const formData = new FormData(form);

        const response = await fetch(form.action || window.location.href, {
            method: form.method || "POST",
            body: formData,
            credentials: "same-origin",
            redirect: "follow",
        });

        if (response.ok || response.redirected) {
            // Remove from sync queue since we synced immediately
            await this.removePendingSync(operation);

            // Follow the redirect from server
            window.location.href = response.url;
        } else {
            console.error("[Offline Forms] Server returned error:", response.status);
            throw new Error(`Server returned ${response.status}`);
        }
    }

    /**
     * Remove pending sync item after successful immediate sync
     */
    async removePendingSync(operation) {
        try {
            const pending = await window.giftManagerDB.getPendingSyncItems();
            const toRemove = pending.find(
                (item) => item.objectId === operation.objectId && item.model === operation.modelType
            );
            if (toRemove) {
                await window.giftManagerDB.removeSyncItem(toRemove.id);
            }
        } catch (error) {
            console.warn("[Offline Forms] Could not remove sync item:", error);
        }
    }

    /**
     * Submit form online via fetch (when we've prevented default)
     */
    async submitFormOnline(form) {
        try {
            const formData = new FormData(form);
            const response = await fetch(form.action || window.location.href, {
                method: form.method || "POST",
                body: formData,
                credentials: "same-origin",
                redirect: "follow",
            });

            if (response.ok || response.redirected) {
                // Follow the redirect
                window.location.href = response.url;
            } else {
                console.error("[Offline Forms] Form submission failed:", response.status);
                alert("Failed to save. Please try again.");
            }
        } catch (error) {
            console.error("[Offline Forms] Online form submission error:", error);
            // Maybe we went offline during the request - try offline mode

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
            const response = await fetch("/api/gifts/", {
                method: "HEAD",
                cache: "no-store",
                signal: controller.signal,
            });

            clearTimeout(timeoutId);
            // Any response (even 401, 404, 500) means we have connectivity
            return true;
        } catch (error) {
            // Network error (Failed to fetch, aborted) means we're offline
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
        const method = (form.method || "get").toUpperCase();

        // Normalize URL for parsing
        let path = "";
        try {
            path = new URL(url, window.location.origin).pathname;
        } catch (e) {
            path = url; // Fallback to raw string
        }

        const idPattern = "([a-f0-9-]{36}|temp-[a-z0-9-]+)";

        // Determine model type from URL (singularize)
        let modelType = null;

        // Check for add_relation URLs first (these are relation creations)
        if (url.includes("/add_relation")) {
            modelType = "relation";
        } else if (url.includes("/gifts/")) {
            modelType = "gift";
        } else if (url.includes("/persons/")) {
            modelType = "person";
        } else if (url.includes("/events/")) {
            modelType = "event";
        } else if (url.includes("/relations/")) {
            modelType = "relation";
        } else if (url.includes("/person_groups/")) {
            modelType = "group";
        } else if (url.includes("/gift-tag/")) {
            modelType = "tag";
        }

        // Determine if create or update
        const isCreate = /\/(create|add_relation)\/?$/i.test(path);
        const updateMatch = new RegExp(`/ ${idPattern} /edit/?$`.replace(/\s+/g, ""), "i").exec(
            path
        );
        const deleteMatch = new RegExp(`/ ${idPattern} /delete/?$`.replace(/\s+/g, ""), "i").exec(
            path
        );

        let objectId = updateMatch?.[1] || deleteMatch?.[1] || null;

        return {
            modelType,
            type: isCreate ? "create" : updateMatch ? "update" : deleteMatch ? "delete" : "unknown",
            objectId,
            method,
            url,
        };
    }

    /**
     * Prefill edit/delete forms from IndexedDB when data is available
     */
    async prefillFormFromIndexedDB(form, operation) {
        if (!operation || !operation.modelType || !operation.objectId) {
            return;
        }

        if (operation.type !== "update" && operation.type !== "delete") {
            return;
        }

        if (!window.giftManagerDB) {
            return;
        }

        await window.giftManagerDB.ready;

        const storeName = operation.modelType + "s";

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
                        return el.value === "" || el.selectedIndex === -1;
                    }
                    return false;
                };

                if (!isEmptyInput(field)) {
                    return;
                }

                if (field instanceof HTMLInputElement) {
                    if (field.type === "checkbox") {
                        field.checked = Boolean(value);
                    } else if (field.type === "radio") {
                        const radios = form.querySelectorAll(`input[name="${name}"][type="radio"]`);
                        radios.forEach((radio) => {
                            if (radio.value === String(value)) {
                                radio.checked = true;
                            }
                        });
                    } else {
                        field.value = String(value);
                    }
                } else if (field instanceof HTMLSelectElement) {
                    if (field.multiple && Array.isArray(value)) {
                        const values = value.map((v) => String(v));
                        Array.from(field.options).forEach((opt) => {
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
        } catch (error) {
            console.warn("[Offline Forms] Could not prefill form from IndexedDB:", error);
        }
    }

    /**
     * Save data to IndexedDB
     */
    async saveToIndexedDB(operation, data) {
        const { modelType, type, objectId } = operation;

        if (!modelType) {
            console.warn("[Offline Forms] Cannot determine model type");
            return;
        }

        const storeName = modelType + "s"; // Pluralize for DB store

        let savedObject;

        if (type === "create") {
            // Generate a temporary ID for new objects
            const tempId = objectId || this.generateTempId();
            // Update operation object so subsequent steps (sync, redirect) know the ID
            operation.objectId = tempId;

            savedObject = {
                ...data,
                [this.getIdField(modelType)]: tempId,
                created_offline: true,
                modified: new Date().toISOString(),
            };
            await window.giftManagerDB.put(storeName, savedObject);
        } else if (type === "update") {
            // Get existing object and merge changes
            const existing = await window.giftManagerDB.get(storeName, objectId);
            savedObject = {
                ...existing,
                ...data,
                modified: new Date().toISOString(),
            };
            await window.giftManagerDB.put(storeName, savedObject);
        } else if (type === "delete") {
            // Mark as deleted (soft delete for sync purposes)
            const existing = await window.giftManagerDB.get(storeName, objectId);
            savedObject = {
                ...existing,
                _deleted: true,
                modified: new Date().toISOString(),
            };
            await window.giftManagerDB.put(storeName, savedObject);
        }

        // Queue for sync
        await this.queueForSync(operation, savedObject);
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
                lang: document.documentElement.lang || "en",
            },
        });
    }

    /**
     * Sync data to server
     */
    async syncToServer(operation, data) {
        const { modelType, type, objectId, url } = operation;
        const storeName = modelType + "s";

        try {
            const csrfToken = this.getCsrfToken();

            // Build fetch options
            const options = {
                method: type === "create" ? "POST" : type === "delete" ? "DELETE" : "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                },
                body: this.buildFormData(data),
                credentials: "same-origin",
            };

            const response = await fetch(url, options);

            if (response.ok) {
                // Handle ID swapping for creations
                if (type === "create" && objectId && objectId.startsWith("temp-")) {
                    // Extract real ID from redirect URL (e.g. /gifts/<uuid>/)
                    const newId = this.extractIdFromUrl(response.url);

                    if (newId) {
                        // Get the temp object
                        const obj = await window.giftManagerDB.get(storeName, objectId);
                        if (obj) {
                            // Delete the temp entry
                            await window.giftManagerDB.delete(storeName, objectId);

                            // Update with new ID
                            const idField = this.getIdField(modelType);
                            obj[idField] = newId;
                            delete obj.created_offline; // No longer pending

                            // Save as new entry
                            await window.giftManagerDB.put(storeName, obj);

                            // Update operation object so the caller knows the real ID (e.g. for redirect)
                            operation.objectId = newId;
                        }
                    } else {
                        console.warn(
                            "[Offline Forms] Could not extract new ID from response URL:",
                            response.url
                        );
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
                console.warn("[Offline Forms] Server returned error:", response.status);
                return false;
            }
        } catch (error) {
            console.error("[Offline Forms] Sync failed:", error);
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
            return;
        }

        this.syncInProgress = true;

        try {
            if (window.offlineSyncManager?.triggerSync) {
                await window.offlineSyncManager.triggerSync();
            }
        } catch (error) {
            console.error("[Offline Forms] Background sync error:", error);
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
                value.forEach((v) => formData.append(key, v));
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
        const name = "csrftoken";
        let cookieValue = null;
        if (document.cookie && document.cookie !== "") {
            const cookies = document.cookie.split(";");
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === name + "=") {
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
            gift: "gift_id",
            person: "person_id",
            event: "event_id",
            relation: "relation_id",
            group: "group_id",
            tag: "tag_id",
        };
        return mapping[modelType] || "id";
    }

    /**
     * Generate temporary ID for offline-created objects
     */
    generateTempId() {
        return "temp-" + Date.now() + "-" + Math.random().toString(36).substr(2, 9);
    }

    /**
     * Show offline message to user
     */
    showOfflineMessage() {
        // Show visual feedback to user
        if (window.offlineSyncManager && window.offlineSyncManager.showToast) {
            window.offlineSyncManager.showToast(
                "Changes saved offline. Will sync when reconnected.",
                "success"
            );
        } else {
            // Fallback: simple alert
            alert("Changes saved offline. Will sync when reconnected.");
        }
    }

    /**
     * Get language prefix from current path
     */
    getLanguagePrefix() {
        const match = window.location.pathname.match(/^\/(en|fr)/);
        return match ? match[0] : "";
    }

    /**
     * Redirect after successful form submission
     */
    redirectAfterSubmit(operation) {
        const { modelType, type, objectId } = operation;

        // Service worker caches pages, so navigation works offline
        // Show success message if offline
        if (!navigator.onLine) {
            this.showOfflineMessage();
        }

        // Determine redirect URL
        // Ensure we preserve language prefix (e.g. /en)
        const langPrefix = this.getLanguagePrefix();
        const urlPrefix = langPrefix + "/" + modelType + "s"; // Pluralize for URL

        let redirectUrl;

        if (type === "delete") {
            // Redirect to list page after delete
            redirectUrl = `${urlPrefix}/`;
        } else if (type === "create") {
            // Redirect to detail page if we have a real ID, otherwise list
            if (objectId && !objectId.startsWith("temp-")) {
                // Approximate URL construction - assumes standard URL pattern
                redirectUrl = `${urlPrefix}/${objectId}/`;
            } else {
                redirectUrl = `${urlPrefix}/`;
            }
        } else {
            // Redirect to detail page after edit
            redirectUrl = `${urlPrefix}/${objectId}/`;
        }

        window.location.href = redirectUrl;
    }
}

// Create global instance
const offlineFormsHandler = new OfflineFormsHandler();
window.offlineFormsHandler = offlineFormsHandler;

// Auto-initialize when DOM is ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
        offlineFormsHandler.init();
    });
} else {
    offlineFormsHandler.init();
}
