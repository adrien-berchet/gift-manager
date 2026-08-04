/**
 * Unsaved Changes Protection
 * Tracks dirty form state and protects panel/page navigation.
 */

(function (window) {
    "use strict";

    if (window.UnsavedChanges?.initialized) {
        return;
    }

    const CONFIG = {
        classes: {
            modified: "form-modified",
            unsavedField: "field-unsaved",
            unsavedGroup: "field-group-unsaved",
            warningModal: "unsaved-changes-modal",
            status: "unsaved-changes-status",
            badge: "unsaved-changes-badge",
        },
        selectors: {
            forms: "form[data-track-changes], #main-form",
            trackableFields: "input, textarea, select",
            excludeFields:
                '[type="hidden"], [type="submit"], [type="button"], [type="reset"], .no-track, .permission-select',
            formActions: ".panel-form-actions, .page-form-actions",
            fieldGroup: ".form-group, .mb-3, .form-floating, .form-check, .field-wrapper",
        },
        messages: {
            navigationWarning:
                "You have unsaved changes. Are you sure you want to leave this page?",
            modalTitle: "Unsaved changes",
            modalBody: "Your changes have not been saved yet.",
            closeBody: "Save your changes, discard them, or keep editing.",
            navigationBody: "Discard your changes to continue to the new page.",
            saveButton: "Save",
            discardButton: "Discard changes",
            keepEditingButton: "Keep editing",
            statusText: "Unsaved changes",
            badgeText: "Unsaved",
            fieldTitle: "This field has been changed",
        },
        debounceDelay: 150,
    };

    const trackedForms = new Set();
    const formStates = new WeakMap();
    const formTimers = new WeakMap();
    const submittingForms = new WeakSet();
    const offcanvasHandlers = new WeakSet();
    const pendingBaselines = new Map();

    let hasUnsavedChanges = false;
    let navigationCallback = null;
    let activeDialog = null;
    let navigationProtectionReady = false;
    let htmxProtectionReady = false;

    function init() {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", setupUnsavedChangesProtection, {
                once: true,
            });
        } else {
            setupUnsavedChangesProtection();
        }
    }

    function setupUnsavedChangesProtection() {
        document.querySelectorAll(CONFIG.selectors.forms).forEach(addForm);
        setupNavigationProtection();
        setupHtmxProtection();
        setupConfirmationModal();
        syncGlobalState();
    }

    function addForm(form) {
        if (typeof form === "string") {
            form = document.getElementById(form);
        }

        if (!form || trackedForms.has(form)) {
            return;
        }

        trackedForms.add(form);

        const signature = getFormSignature(form);
        const current = snapshotForm(form);
        const pendingOriginal = pendingBaselines.get(signature);
        const original = pendingOriginal || current;
        pendingBaselines.delete(signature);
        formStates.set(form, { dirty: false, original, signature });

        form.addEventListener("input", handleTrackedFieldEvent);
        form.addEventListener("change", handleTrackedFieldEvent);
        form.addEventListener("paste", handleTrackedFieldEvent);
        form.addEventListener("keyup", handleTrackedFieldEvent);
        form.addEventListener("submit", handleFormSubmit);
        form.addEventListener("htmx:afterRequest", handleHtmxAfterRequest);
        form.addEventListener("form:cleanup", function () {
            removeForm(form);
        });

        setupOffcanvasProtection(form);
        updateFormState(form, pendingOriginal ? !snapshotsEqual(original, current) : false);
    }

    function removeForm(form) {
        trackedForms.delete(form);
        form.classList.remove(CONFIG.classes.modified);
        clearModifiedFields(form);
        updateFormActions(form, false);
        updateOffcanvasState(form.closest(".offcanvas"));
        syncGlobalState();
    }

    function setupOffcanvasProtection(form) {
        const offcanvas = form.closest(".offcanvas");
        if (!offcanvas || offcanvasHandlers.has(offcanvas)) {
            return;
        }

        offcanvasHandlers.add(offcanvas);
        offcanvas.addEventListener("hide.bs.offcanvas", function (event) {
            if (
                offcanvas.dataset.skipUnsavedPrompt === "true" ||
                offcanvas.dataset.unsavedChangesAllowClose === "true"
            ) {
                return;
            }

            refreshForms(offcanvas);
            const dirtyForms = getDirtyForms(offcanvas);
            if (dirtyForms.length === 0) {
                return;
            }

            event.preventDefault();
            showConfirmation({
                form: dirtyForms[0],
                allowSave: true,
                body: CONFIG.messages.closeBody,
                onDiscard: function () {
                    discardForms(dirtyForms);
                    allowOffcanvasClose(offcanvas);
                },
            });
        });
    }

    function handleTrackedFieldEvent(event) {
        const field = event.target;
        const form = event.currentTarget;

        if (!isTrackableField(field)) {
            return;
        }

        const existingTimer = formTimers.get(form);
        if (existingTimer) {
            window.clearTimeout(existingTimer);
        }

        formTimers.set(
            form,
            window.setTimeout(function () {
                checkForChanges(form);
            }, CONFIG.debounceDelay)
        );
    }

    function handleFormSubmit(event) {
        if (event.defaultPrevented) {
            return;
        }

        submittingForms.add(event.currentTarget);
    }

    function handleHtmxAfterRequest(event) {
        const form = event.currentTarget;
        submittingForms.delete(form);

        if (event.detail?.successful) {
            clearForm(form);
            return;
        }

        checkForChanges(form);
    }

    function setupHtmxProtection() {
        if (htmxProtectionReady || !document.body) {
            return;
        }

        htmxProtectionReady = true;

        document.body.addEventListener("htmx:beforeSwap", function (event) {
            const xhr = event.detail?.xhr;
            if (!xhr || (xhr.status !== 400 && xhr.status !== 422)) {
                return;
            }

            const form = getEventForm(event);
            if (!form) {
                return;
            }

            checkForChanges(form);

            if (!isDirty(form)) {
                return;
            }

            const state = formStates.get(form);
            pendingBaselines.set(getFormSignature(form), cloneSnapshot(state.original));
        });

        document.body.addEventListener("htmx:afterSwap", function (event) {
            pruneDisconnectedForms();

            const target = event.detail?.target;
            if (!target) {
                return;
            }

            if (target.matches?.("form[data-form-type], " + CONFIG.selectors.forms)) {
                addForm(target);
            }

            target.querySelectorAll?.("form[data-form-type], " + CONFIG.selectors.forms).forEach(
                addForm
            );
        });
    }

    function setupNavigationProtection() {
        if (navigationProtectionReady) {
            return;
        }

        navigationProtectionReady = true;

        window.addEventListener("beforeunload", function (event) {
            refreshForms();

            if (!hasUnsaved() || hasSubmittingForm()) {
                return undefined;
            }

            event.preventDefault();
            event.returnValue = CONFIG.messages.navigationWarning;
            return CONFIG.messages.navigationWarning;
        });

        document.addEventListener("click", function (event) {
            if (
                event.defaultPrevented ||
                event.button !== 0 ||
                event.metaKey ||
                event.ctrlKey ||
                event.shiftKey ||
                event.altKey
            ) {
                return;
            }

            refreshForms();

            if (!hasUnsaved()) {
                return;
            }

            const link = event.target.closest("a[href]");
            if (!link || shouldIgnoreNavigationLink(link)) {
                return;
            }

            event.preventDefault();
            const href = link.getAttribute("href");
            navigationCallback = function () {
                window.location.href = href;
            };

            showConfirmation({
                form: getFirstDirtyForm(),
                allowSave: false,
                body: CONFIG.messages.navigationBody,
                onDiscard: function () {
                    clearUnsavedChanges();
                    if (navigationCallback) {
                        navigationCallback();
                        navigationCallback = null;
                    }
                },
            });
        });
    }

    function setupConfirmationModal() {
        if (document.getElementById("unsaved-changes-modal")) {
            setupModalEventHandlers();
            return;
        }

        const modalHTML = `
            <div class="modal fade" id="unsaved-changes-modal" tabindex="-1" aria-labelledby="unsaved-changes-modal-label" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="unsaved-changes-modal-label">
                                <i class="fas fa-exclamation-circle text-warning me-2" aria-hidden="true"></i>
                                ${CONFIG.messages.modalTitle}
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <p class="mb-0" id="unsaved-changes-modal-body">${CONFIG.messages.modalBody}</p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-danger" id="discard-changes-btn">
                                <i class="fas fa-undo me-1" aria-hidden="true"></i>
                                ${CONFIG.messages.discardButton}
                            </button>
                            <button type="button" class="btn btn-outline-primary" id="save-changes-btn">
                                <i class="fas fa-save me-1" aria-hidden="true"></i>
                                ${CONFIG.messages.saveButton}
                            </button>
                            <button type="button" class="btn btn-primary" id="keep-editing-btn" data-bs-dismiss="modal">
                                ${CONFIG.messages.keepEditingButton}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML("beforeend", modalHTML);
        setupModalEventHandlers();
    }

    function setupModalEventHandlers() {
        const modal = document.getElementById("unsaved-changes-modal");
        if (!modal || modal.dataset.unsavedHandlersReady === "true") {
            return;
        }

        modal.dataset.unsavedHandlersReady = "true";

        const saveBtn = document.getElementById("save-changes-btn");
        const discardBtn = document.getElementById("discard-changes-btn");

        saveBtn?.addEventListener("click", function () {
            if (activeDialog?.form) {
                submitForm(activeDialog.form);
            }
            hideConfirmation();
            activeDialog = null;
            navigationCallback = null;
        });

        discardBtn?.addEventListener("click", function () {
            const onDiscard = activeDialog?.onDiscard;
            hideConfirmation();
            activeDialog = null;

            if (onDiscard) {
                onDiscard();
            }
        });

        modal.addEventListener("hidden.bs.modal", function () {
            activeDialog = null;
            navigationCallback = null;
        });
    }

    function showConfirmation(options) {
        setupConfirmationModal();
        activeDialog = options;

        const modal = document.getElementById("unsaved-changes-modal");
        const body = document.getElementById("unsaved-changes-modal-body");
        const saveBtn = document.getElementById("save-changes-btn");

        if (!modal || !window.bootstrap?.Modal) {
            return;
        }

        if (body) {
            body.textContent = options.body || CONFIG.messages.modalBody;
        }

        if (saveBtn) {
            saveBtn.classList.toggle("d-none", !options.allowSave);
        }

        bootstrap.Modal.getOrCreateInstance(modal).show();
    }

    function hideConfirmation() {
        const modal = document.getElementById("unsaved-changes-modal");
        if (!modal || !window.bootstrap?.Modal) {
            return;
        }

        bootstrap.Modal.getOrCreateInstance(modal).hide();
    }

    function submitForm(form) {
        const submitter = form.querySelector(
            '.panel-form-actions button[type="submit"].btn-primary:not(:disabled), ' +
                '.page-form-actions button[type="submit"].btn-primary:not(:disabled), ' +
                'button[type="submit"].btn-primary:not(:disabled), ' +
                'input[type="submit"]:not(:disabled), ' +
                'button[type="submit"]:not(:disabled)'
        );

        if (typeof form.requestSubmit === "function") {
            form.requestSubmit(submitter || undefined);
        } else if (submitter) {
            submitter.click();
        }
    }

    function checkForChanges(form) {
        const state = formStates.get(form);
        if (!state) {
            return;
        }

        updateFormState(form, !snapshotsEqual(state.original, snapshotForm(form)));
    }

    function refreshForms(container) {
        pruneDisconnectedForms();

        trackedForms.forEach((form) => {
            if (!container || container.contains(form)) {
                checkForChanges(form);
            }
        });
    }

    function updateFormState(form, hasChanges) {
        const state = formStates.get(form);
        if (state) {
            state.dirty = hasChanges;
        }

        form.classList.toggle(CONFIG.classes.modified, hasChanges);

        if (hasChanges) {
            markModifiedFields(form);
        } else {
            clearModifiedFields(form);
        }

        updateFormActions(form, hasChanges);
        updateOffcanvasState(form.closest(".offcanvas"));
        syncGlobalState();
    }

    function updateFormActions(form, hasChanges) {
        const actions = form.querySelector(CONFIG.selectors.formActions);
        if (!actions) {
            return;
        }

        actions.classList.toggle("has-unsaved-changes", hasChanges);

        let status = actions.querySelector("." + CONFIG.classes.status);
        if (!status) {
            status = document.createElement("span");
            status.className = CONFIG.classes.status;
            status.setAttribute("role", "status");
            status.setAttribute("aria-live", "polite");
            status.innerHTML = `
                <i class="fas fa-circle" aria-hidden="true"></i>
                <span>${CONFIG.messages.statusText}</span>
            `;
            actions.insertBefore(status, actions.firstChild);
        }

        status.hidden = !hasChanges;
    }

    function updateOffcanvasState(offcanvas) {
        if (!offcanvas) {
            return;
        }

        const hasDirtyForm = getDirtyForms(offcanvas).length > 0;
        offcanvas.classList.toggle("has-unsaved-changes", hasDirtyForm);

        const title = offcanvas.querySelector(".offcanvas-title");
        if (!title) {
            return;
        }

        let badge = title.querySelector("." + CONFIG.classes.badge);
        if (!badge) {
            badge = document.createElement("span");
            badge.className = CONFIG.classes.badge;
            badge.setAttribute("role", "status");
            badge.setAttribute("aria-live", "polite");
            badge.innerHTML = `
                <i class="fas fa-circle" aria-hidden="true"></i>
                <span>${CONFIG.messages.badgeText}</span>
            `;
            title.appendChild(badge);
        }

        badge.hidden = !hasDirtyForm;
    }

    function markModifiedFields(form) {
        const state = formStates.get(form);
        if (!state) {
            return;
        }

        const current = snapshotForm(form);
        const changedGroups = new Set();

        form.querySelectorAll("." + CONFIG.classes.unsavedGroup).forEach((group) => {
            group.classList.remove(CONFIG.classes.unsavedGroup);
        });

        getTrackableFields(form).forEach((field) => {
            const fieldName = field.name;
            const changed =
                Boolean(fieldName) &&
                !arraysEqual(state.original.get(fieldName) || [], current.get(fieldName) || []);

            field.classList.toggle(CONFIG.classes.unsavedField, changed);

            if (changed) {
                const group = field.closest(CONFIG.selectors.fieldGroup);
                if (group) {
                    changedGroups.add(group);
                }
                field.setAttribute("title", CONFIG.messages.fieldTitle);
            } else {
                field.removeAttribute("title");
            }
        });

        changedGroups.forEach((group) => {
            group.classList.add(CONFIG.classes.unsavedGroup);
        });
    }

    function clearModifiedFields(form) {
        form.querySelectorAll("." + CONFIG.classes.unsavedField).forEach((field) => {
            field.classList.remove(CONFIG.classes.unsavedField);
            field.removeAttribute("title");
        });

        form.querySelectorAll("." + CONFIG.classes.unsavedGroup).forEach((group) => {
            group.classList.remove(CONFIG.classes.unsavedGroup);
        });
    }

    function clearForm(form) {
        const state = formStates.get(form);
        if (!state) {
            return;
        }

        state.original = snapshotForm(form);
        updateFormState(form, false);
        submittingForms.delete(form);
    }

    function clearUnsavedChanges() {
        trackedForms.forEach((form) => {
            if (form.isConnected) {
                clearForm(form);
            }
        });

        syncGlobalState();
        document.dispatchEvent(new CustomEvent("unsavedChangesCleared"));
    }

    function discardForms(forms) {
        forms.forEach((form) => {
            const state = formStates.get(form);
            if (!state) {
                return;
            }
            resetFormToOriginal(form, state.original);
            clearForm(form);
        });
    }

    function resetFormToOriginal(form, original) {
        getTrackableFields(form).forEach((field) => {
            const fieldName = field.name;
            if (!fieldName) {
                return;
            }

            const values = original.get(fieldName) || [];

            if (field.type === "checkbox") {
                field.checked = values.includes(normalizeValue(field.value));
            } else if (field.type === "radio") {
                field.checked = values[0] === normalizeValue(field.value);
            } else if (field.tagName === "SELECT" && field.multiple) {
                Array.from(field.options).forEach((option) => {
                    option.selected = values.includes(normalizeValue(option.value));
                });
            } else if (field.type === "file") {
                field.value = "";
            } else {
                field.value = values[0] || "";
            }

            field.dispatchEvent(new Event("input", { bubbles: true }));
            field.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }

    function allowOffcanvasClose(offcanvas) {
        offcanvas.dataset.unsavedChangesAllowClose = "true";
        const instance = bootstrap.Offcanvas.getOrCreateInstance(offcanvas);

        offcanvas.addEventListener(
            "hidden.bs.offcanvas",
            function () {
                delete offcanvas.dataset.unsavedChangesAllowClose;
            },
            { once: true }
        );

        instance.hide();
    }

    function confirmPanelReplacement(target, callback) {
        const panel = typeof target === "string" ? document.getElementById(target) : target;
        if (!panel) {
            return true;
        }

        refreshForms(panel);
        const dirtyForms = getDirtyForms(panel);
        if (dirtyForms.length === 0) {
            return true;
        }

        showConfirmation({
            form: dirtyForms[0],
            allowSave: true,
            body: CONFIG.messages.closeBody,
            onDiscard: function () {
                discardForms(dirtyForms);
                if (callback) {
                    callback();
                }
            },
        });

        return false;
    }

    function markAsChanged(form) {
        if (typeof form === "string") {
            form = document.getElementById(form);
        }

        if (form && trackedForms.has(form)) {
            updateFormState(form, true);
        }
    }

    function hasUnsaved() {
        syncGlobalState();
        return hasUnsavedChanges;
    }

    function hasSubmittingForm() {
        pruneDisconnectedForms();
        return Array.from(trackedForms).some((form) => submittingForms.has(form));
    }

    function getFirstDirtyForm() {
        pruneDisconnectedForms();
        return Array.from(trackedForms).find(isDirty) || null;
    }

    function getDirtyForms(container) {
        pruneDisconnectedForms();
        return Array.from(trackedForms).filter((form) => {
            if (!isDirty(form)) {
                return false;
            }

            return !container || container.contains(form);
        });
    }

    function isDirty(form) {
        return Boolean(formStates.get(form)?.dirty);
    }

    function syncGlobalState() {
        pruneDisconnectedForms();
        hasUnsavedChanges = Array.from(trackedForms).some(isDirty);
        document.body?.classList.toggle("has-unsaved-changes", hasUnsavedChanges);
    }

    function pruneDisconnectedForms() {
        trackedForms.forEach((form) => {
            if (!form.isConnected) {
                trackedForms.delete(form);
            }
        });
    }

    function snapshotForm(form) {
        const formData = new FormData(form);
        const snapshot = new Map();

        getTrackableFields(form).forEach((field) => {
            if (!field.name || snapshot.has(field.name)) {
                return;
            }

            const values = formData.getAll(field.name).map(normalizeValue).sort();
            snapshot.set(field.name, values);
        });

        return snapshot;
    }

    function cloneSnapshot(snapshot) {
        const clone = new Map();
        snapshot.forEach((values, name) => {
            clone.set(name, values.slice());
        });
        return clone;
    }

    function getTrackableFields(form) {
        return Array.from(form.querySelectorAll(CONFIG.selectors.trackableFields)).filter(
            isTrackableField
        );
    }

    function isTrackableField(field) {
        return (
            field &&
            field.matches?.(CONFIG.selectors.trackableFields) &&
            !field.matches(CONFIG.selectors.excludeFields) &&
            !field.disabled
        );
    }

    function normalizeValue(value) {
        if (value instanceof File) {
            return ["file", value.name, value.size, value.lastModified].join(":");
        }

        return String(value);
    }

    function snapshotsEqual(snapshotA, snapshotB) {
        const keysA = Array.from(snapshotA.keys()).sort();
        const keysB = Array.from(snapshotB.keys()).sort();

        if (!arraysEqual(keysA, keysB)) {
            return false;
        }

        return keysA.every((key) => arraysEqual(snapshotA.get(key), snapshotB.get(key)));
    }

    function arraysEqual(valuesA = [], valuesB = []) {
        if (valuesA.length !== valuesB.length) {
            return false;
        }

        return valuesA.every((value, index) => value === valuesB[index]);
    }

    function getFormSignature(form) {
        return [
            form.dataset.formType || "",
            form.id || "",
            form.getAttribute("method") || "get",
            form.getAttribute("action") ||
                form.getAttribute("hx-post") ||
                form.getAttribute("hx-get") ||
                "",
        ].join("|");
    }

    function getEventForm(event) {
        const elt = event.detail?.elt;
        const target = event.detail?.target;

        if (elt?.matches?.("form")) {
            return elt;
        }

        if (elt?.closest) {
            const form = elt.closest("form");
            if (form) {
                return form;
            }
        }

        if (target?.matches?.("form")) {
            return target;
        }

        return target?.querySelector?.("form") || null;
    }

    function shouldIgnoreNavigationLink(link) {
        const href = link.getAttribute("href") || "";

        return (
            href.startsWith("#") ||
            href.startsWith("javascript:") ||
            link.target === "_blank" ||
            link.hasAttribute("download") ||
            link.closest("#unsaved-changes-modal") ||
            link.closest("[data-action='delete']")
        );
    }

    window.UnsavedChanges = {
        initialized: true,
        init,
        hasUnsaved,
        isDirty,
        clearForm,
        clearUnsavedChanges,
        confirmPanelReplacement,
        markAsChanged,
        addForm,
        config: CONFIG,
    };

    init();
})(window);
