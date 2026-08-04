/**
 * Unsaved Changes Protection
 * Implements form change tracking and navigation warnings
 * Requirements: 12.1, 12.2
 */

(function (window) {
    "use strict";

    /**
     * Configuration for unsaved changes protection
     */
    const UNSAVED_CHANGES_CONFIG = {
        // CSS classes
        classes: {
            modified: "form-modified",
            unsavedField: "field-unsaved",
            warningModal: "unsaved-changes-modal",
            saveIndicator: "save-indicator",
        },

        // Selectors
        selectors: {
            forms: "form[data-track-changes], #main-form",
            trackableFields: "input, textarea, select",
            excludeFields: '[type="hidden"], [type="submit"], [type="button"], .no-track',
        },

        // Messages
        messages: {
            navigationWarning:
                "You have unsaved changes. Are you sure you want to leave this page?",
            modalTitle: "Unsaved Changes",
            modalBody:
                "You have unsaved changes that will be lost if you continue. What would you like to do?",
            saveButton: "Save Changes",
            discardButton: "Discard Changes",
            cancelButton: "Cancel",
        },

        // Timeouts
        debounceDelay: 300,
    };

    /**
     * Global state
     */
    let hasUnsavedChanges = false;
    let originalFormData = new Map();
    let trackedForms = new Set();
    let navigationCallback = null;
    let debounceTimer = null;

    /**
     * Initialize unsaved changes protection
     */
    function init() {
        // Wait for DOM to be ready
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", setupUnsavedChangesProtection);
        } else {
            setupUnsavedChangesProtection();
        }
    }

    /**
     * Setup unsaved changes protection for all forms
     */
    function setupUnsavedChangesProtection() {
        const forms = document.querySelectorAll(UNSAVED_CHANGES_CONFIG.selectors.forms);

        forms.forEach((form) => {
            if (!trackedForms.has(form)) {
                trackForm(form);
            }
        });

        // Setup global navigation protection
        setupNavigationProtection();

        // Setup modal for confirmation dialogs
        setupConfirmationModal();
    }

    /**
     * Track changes in a specific form
     */
    function trackForm(form) {
        if (trackedForms.has(form)) {
            return;
        }

        trackedForms.add(form);

        // Store original form data
        storeOriginalFormData(form);

        // Add change listeners to all trackable fields
        const fields = form.querySelectorAll(UNSAVED_CHANGES_CONFIG.selectors.trackableFields);
        fields.forEach((field) => {
            if (!field.matches(UNSAVED_CHANGES_CONFIG.selectors.excludeFields)) {
                setupFieldTracking(field, form);
            }
        });

        // Handle form submission
        form.addEventListener("submit", function () {
            clearUnsavedChanges();
        });
    }

    /**
     * Setup tracking for individual field
     */
    function setupFieldTracking(field, form) {
        const events = ["input", "change", "paste", "keyup"];

        events.forEach((eventType) => {
            field.addEventListener(eventType, function () {
                // Debounce the change detection
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    checkForChanges(form);
                }, UNSAVED_CHANGES_CONFIG.debounceDelay);
            });
        });
    }

    /**
     * Store original form data for comparison
     */
    function storeOriginalFormData(form) {
        const formData = new FormData(form);
        const formId = form.id || form.getAttribute("data-form-id") || "default";

        originalFormData.set(formId, formData);
    }

    /**
     * Check if form has unsaved changes
     */
    function checkForChanges(form) {
        const formId = form.id || form.getAttribute("data-form-id") || "default";
        const originalData = originalFormData.get(formId);

        if (!originalData) {
            return;
        }

        const currentData = new FormData(form);
        const hasChanges = !compareFormData(originalData, currentData);

        if (hasChanges) {
            hasUnsavedChanges = true;
            updateFormState(form, true);
        } else {
            hasUnsavedChanges = false;
            updateFormState(form, false);
        }
    }

    /**
     * Compare two FormData objects
     */
    function compareFormData(formData1, formData2) {
        const entries1 = Array.from(formData1.entries()).sort();
        const entries2 = Array.from(formData2.entries()).sort();

        if (entries1.length !== entries2.length) {
            return false;
        }

        for (let i = 0; i < entries1.length; i++) {
            const [key1, value1] = entries1[i];
            const [key2, value2] = entries2[i];

            if (key1 !== key2 || value1 !== value2) {
                return false;
            }
        }

        return true;
    }

    /**
     * Update form visual state based on changes
     */
    function updateFormState(form, hasChanges) {
        if (hasChanges) {
            form.classList.add(UNSAVED_CHANGES_CONFIG.classes.modified);
            markModifiedFields(form);
            showSaveIndicator();
            addUnsavedActionsToForm(form);

            // Add class to parent offcanvas if exists
            const offcanvas = form.closest(".offcanvas");
            if (offcanvas) {
                offcanvas.classList.add("has-unsaved-changes");
            }
        } else {
            form.classList.remove(UNSAVED_CHANGES_CONFIG.classes.modified);
            clearModifiedFields(form);
            hideSaveIndicator();
            removeUnsavedActionsFromForm(form);

            // Remove class from parent offcanvas if exists
            const offcanvas = form.closest(".offcanvas");
            if (offcanvas) {
                offcanvas.classList.remove("has-unsaved-changes");
            }
        }
    }

    /**
     * Mark fields that have been modified
     */
    function markModifiedFields(form) {
        const formId = form.id || form.getAttribute("data-form-id") || "default";
        const originalData = originalFormData.get(formId);
        const currentData = new FormData(form);

        if (!originalData) return;

        // Convert FormData to objects for easier comparison
        const original = {};
        const current = {};

        for (const [key, value] of originalData.entries()) {
            original[key] = value;
        }

        for (const [key, value] of currentData.entries()) {
            current[key] = value;
        }

        // Mark modified fields
        const fields = form.querySelectorAll(UNSAVED_CHANGES_CONFIG.selectors.trackableFields);
        fields.forEach((field) => {
            const fieldName = field.name;
            if (fieldName && original[fieldName] !== current[fieldName]) {
                field.classList.add(UNSAVED_CHANGES_CONFIG.classes.unsavedField);
                field.setAttribute("title", "This field has been modified");
                field.setAttribute("data-original-value", original[fieldName] || "");
            } else {
                field.classList.remove(UNSAVED_CHANGES_CONFIG.classes.unsavedField);
                field.removeAttribute("title");
                field.removeAttribute("data-original-value");
            }
        });
    }

    /**
     * Clear modified field indicators
     */
    function clearModifiedFields(form) {
        const fields = form.querySelectorAll("." + UNSAVED_CHANGES_CONFIG.classes.unsavedField);
        fields.forEach((field) => {
            field.classList.remove(UNSAVED_CHANGES_CONFIG.classes.unsavedField);
            field.removeAttribute("title");
            field.removeAttribute("data-original-value");
        });
    }

    /**
     * Setup navigation protection (beforeunload)
     */
    function setupNavigationProtection() {
        window.addEventListener("beforeunload", function (event) {
            if (hasUnsavedChanges) {
                event.preventDefault();
                event.returnValue = UNSAVED_CHANGES_CONFIG.messages.navigationWarning;
                return UNSAVED_CHANGES_CONFIG.messages.navigationWarning;
            }
        });

        // Intercept navigation links
        document.addEventListener("click", function (event) {
            const link = event.target.closest("a[href]");
            if (link && hasUnsavedChanges) {
                // Check if it's an external link or same-page anchor
                const href = link.getAttribute("href");
                if (
                    href.startsWith("#") ||
                    href.startsWith("javascript:") ||
                    link.target === "_blank"
                ) {
                    return;
                }

                event.preventDefault();
                showNavigationConfirmation(() => {
                    clearUnsavedChanges();
                    window.location.href = href;
                });
            }
        });
    }

    /**
     * Setup confirmation modal
     */
    function setupConfirmationModal() {
        // Create modal HTML if it doesn't exist
        if (!document.getElementById("unsaved-changes-modal")) {
            const modalHTML = `
                <div class="modal fade" id="unsaved-changes-modal" tabindex="-1" aria-labelledby="unsaved-changes-modal-label" aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="unsaved-changes-modal-label">
                                    <i class="fas fa-exclamation-triangle text-warning me-2"></i>
                                    ${UNSAVED_CHANGES_CONFIG.messages.modalTitle}
                                </h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <p>${UNSAVED_CHANGES_CONFIG.messages.modalBody}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-primary" id="save-changes-btn">
                                    <i class="fas fa-save me-2"></i>
                                    ${UNSAVED_CHANGES_CONFIG.messages.saveButton}
                                </button>
                                <button type="button" class="btn btn-danger" id="discard-changes-btn">
                                    <i class="fas fa-trash me-2"></i>
                                    ${UNSAVED_CHANGES_CONFIG.messages.discardButton}
                                </button>
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                    ${UNSAVED_CHANGES_CONFIG.messages.cancelButton}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            document.body.insertAdjacentHTML("beforeend", modalHTML);

            // Setup modal event handlers
            setupModalEventHandlers();
        }
    }

    /**
     * Setup event handlers for the confirmation modal
     */
    function setupModalEventHandlers() {
        const modal = document.getElementById("unsaved-changes-modal");
        const saveBtn = document.getElementById("save-changes-btn");
        const discardBtn = document.getElementById("discard-changes-btn");

        saveBtn.addEventListener("click", function () {
            // Try to save the form
            const forms = document.querySelectorAll(UNSAVED_CHANGES_CONFIG.selectors.forms);
            const modifiedForm = Array.from(forms).find((form) =>
                form.classList.contains(UNSAVED_CHANGES_CONFIG.classes.modified)
            );

            if (modifiedForm) {
                // Trigger form submission
                modifiedForm.submit();
            }

            // Close modal
            const modalInstance = bootstrap.Modal.getInstance(modal);
            if (modalInstance) {
                modalInstance.hide();
            }
        });

        discardBtn.addEventListener("click", function () {
            // Clear unsaved changes and proceed with navigation
            clearUnsavedChanges();

            // Close modal
            const modalInstance = bootstrap.Modal.getInstance(modal);
            if (modalInstance) {
                modalInstance.hide();
            }

            // Execute pending navigation or offcanvas close
            if (navigationCallback) {
                navigationCallback();
                navigationCallback = null;
            } else if (window.pendingOffcanvasClose) {
                window.pendingOffcanvasClose();
                window.pendingOffcanvasClose = null;
            }
        });
    }

    /**
     * Show navigation confirmation dialog
     */
    function showNavigationConfirmation(callback) {
        navigationCallback = callback;

        const modal = document.getElementById("unsaved-changes-modal");
        if (modal) {
            const modalInstance = new bootstrap.Modal(modal);
            modalInstance.show();
        } else {
            // Fallback to browser confirm dialog
            if (confirm(UNSAVED_CHANGES_CONFIG.messages.navigationWarning)) {
                clearUnsavedChanges();
                callback();
            }
        }
    }

    /**
     * Clear unsaved changes state
     */
    function clearUnsavedChanges() {
        hasUnsavedChanges = false;

        // Clear all form modifications
        trackedForms.forEach((form) => {
            form.classList.remove(UNSAVED_CHANGES_CONFIG.classes.modified);
            clearModifiedFields(form);
            removeUnsavedActionsFromForm(form);

            // Remove class from parent offcanvas if exists
            const offcanvas = form.closest(".offcanvas");
            if (offcanvas) {
                offcanvas.classList.remove("has-unsaved-changes");
            }
        });

        // Update original form data
        trackedForms.forEach((form) => {
            storeOriginalFormData(form);
        });

        // Hide save indicator
        hideSaveIndicator();

        // Trigger custom event
        const event = new CustomEvent("unsavedChangesCleared");
        document.dispatchEvent(event);
    }

    /**
     * Show save indicator
     */
    function showSaveIndicator() {
        let indicator = document.getElementById("save-indicator");

        if (!indicator) {
            indicator = document.createElement("div");
            indicator.id = "save-indicator";
            indicator.className = UNSAVED_CHANGES_CONFIG.classes.saveIndicator;
            indicator.innerHTML = `
                <i class="fas fa-exclamation-triangle"></i>
                <span>Unsaved changes</span>
            `;
            document.body.appendChild(indicator);
        }

        indicator.classList.remove("hidden");
    }

    /**
     * Hide save indicator
     */
    function hideSaveIndicator() {
        const indicator = document.getElementById("save-indicator");
        if (indicator) {
            indicator.classList.add("hidden");
            setTimeout(() => {
                if (indicator.parentNode) {
                    indicator.parentNode.removeChild(indicator);
                }
            }, 300);
        }
    }

    /**
     * Add unsaved actions to form
     */
    function addUnsavedActionsToForm(form) {
        // Don't add if already exists
        if (form.querySelector(".unsaved-actions")) {
            return;
        }

        const actionsHTML = `
            <div class="unsaved-actions">
                <div class="unsaved-message">
                    You have unsaved changes
                </div>
                <div class="action-buttons">
                    <button type="submit" class="btn btn-primary btn-sm save-changes-btn">
                        <i class="fas fa-save me-1"></i>
                        Save
                    </button>
                    <button type="button" class="btn btn-outline-secondary btn-sm discard-changes-btn">
                        <i class="fas fa-undo me-1"></i>
                        Discard
                    </button>
                </div>
            </div>
        `;

        form.insertAdjacentHTML("beforeend", actionsHTML);

        // Add event listeners
        const saveBtn = form.querySelector(".save-changes-btn");
        const discardBtn = form.querySelector(".discard-changes-btn");

        if (saveBtn) {
            saveBtn.addEventListener("click", function (e) {
                e.preventDefault();
                form.submit();
            });
        }

        if (discardBtn) {
            discardBtn.addEventListener("click", function (e) {
                e.preventDefault();
                if (confirm("Are you sure you want to discard all changes?")) {
                    clearUnsavedChanges();
                    // Reload form data or reset form
                    const formId = form.id || form.getAttribute("data-form-id") || "default";
                    const originalData = originalFormData.get(formId);
                    if (originalData) {
                        // Reset form to original values
                        resetFormToOriginal(form, originalData);
                    }
                }
            });
        }
    }

    /**
     * Remove unsaved actions from form
     */
    function removeUnsavedActionsFromForm(form) {
        const actions = form.querySelector(".unsaved-actions");
        if (actions) {
            actions.remove();
        }
    }

    /**
     * Reset form to original values
     */
    function resetFormToOriginal(form, originalData) {
        const fields = form.querySelectorAll(UNSAVED_CHANGES_CONFIG.selectors.trackableFields);

        fields.forEach((field) => {
            if (field.matches(UNSAVED_CHANGES_CONFIG.selectors.excludeFields)) {
                return;
            }

            const fieldName = field.name;
            if (fieldName && originalData.has(fieldName)) {
                const originalValue = originalData.get(fieldName);

                if (field.type === "checkbox" || field.type === "radio") {
                    field.checked = field.value === originalValue;
                } else {
                    field.value = originalValue;
                }

                // Trigger change event to update any dependent UI
                field.dispatchEvent(new Event("change", { bubbles: true }));
            }
        });
    }

    /**
     * Check if there are unsaved changes
     */
    function hasUnsaved() {
        return hasUnsavedChanges;
    }

    /**
     * Manually mark form as having changes (for programmatic updates)
     */
    function markAsChanged(form) {
        if (typeof form === "string") {
            form = document.getElementById(form);
        }

        if (form && trackedForms.has(form)) {
            hasUnsavedChanges = true;
            updateFormState(form, true);
        }
    }

    /**
     * Add new form to tracking (for dynamically created forms)
     */
    function addForm(form) {
        if (typeof form === "string") {
            form = document.getElementById(form);
        }

        if (form && !trackedForms.has(form)) {
            trackForm(form);
        }
    }

    // Expose public API
    window.UnsavedChanges = {
        init: init,
        hasUnsaved: hasUnsaved,
        clearUnsavedChanges: clearUnsavedChanges,
        markAsChanged: markAsChanged,
        addForm: addForm,
        config: UNSAVED_CHANGES_CONFIG,
    };

    // Auto-initialize
    init();
})(window);
