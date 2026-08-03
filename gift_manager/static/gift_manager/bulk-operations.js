/**
 * Bulk Operations Module
 * Handles multi-select functionality and bulk actions for list views
 */

(function (window) {
    "use strict";

    const BulkOperations = {
        // Configuration
        config: {
            selectors: {
                selectAll: ".bulk-select-all",
                selectItem: ".bulk-select-item",
                bulkToolbar: ".bulk-actions-toolbar",
                bulkActionBtn: ".bulk-action-btn",
                selectedCount: ".selected-count",
                gridContainer: ".gridjs-wrapper",
            },
            classes: {
                selected: "bulk-selected",
                toolbarVisible: "bulk-toolbar-visible",
            },
        },

        // State
        state: {
            selectedItems: new Set(),
            initialized: false,
            currentEntityType: null,
            selectionModeActive: false,
            capturedColumnWidths: null, // Widths captured when entering selection mode
            baselineColumnWidths: null, // Original widths captured on page load (before any selection mode)
        },

        displayLabels: {
            relation: {
                singular: "gift plan",
                plural: "gift plans",
            },
        },

        /**
         * Initialize bulk operations for a grid
         * @param {string} gridId - The ID of the grid container
         * @param {string} entityType - The type of entity (person, gift, etc.)
         * @param {Object} options - Configuration options
         */
        init(gridId, entityType, options = {}) {
            this.state.currentEntityType = entityType;
            this.gridId = gridId;
            this.options = {
                enableSelectAll: true,
                enableBulkDelete: true,
                enableBulkShare: true,
                ...options,
            };

            // Wait for grid to be ready
            this.waitForGrid(gridId, () => {
                this.setupBulkOperations();
                this.bindEvents();
                this.bindToggleButton();
                this.state.initialized = true;
            });
        },

        /**
         * Wait for grid to be rendered and ready
         */
        waitForGrid(gridId, callback, attempts = 0) {
            const maxAttempts = 50;
            const gridContainer = document.getElementById(gridId);

            if (gridContainer && gridContainer.querySelector("tbody")) {
                callback();
            } else if (attempts < maxAttempts) {
                setTimeout(() => this.waitForGrid(gridId, callback, attempts + 1), 100);
            } else {
                console.warn(
                    `[BulkOperations] Grid ${gridId} not ready after ${maxAttempts} attempts`
                );
            }
        },

        /**
         * Setup bulk operations UI elements
         */
        setupBulkOperations() {
            this.addBulkToolbar();
            // Capture baseline column widths (before ever entering selection mode)
            this.captureBaselineWidths();
            // Checkboxes are now part of Grid.js columns, no need to add them manually
            // They are hidden by CSS until selection mode is entered
        },

        /**
         * Capture baseline column widths on page load
         * This creates a reference point to return to when exiting selection mode
         */
        captureBaselineWidths() {
            const gridContainer = document.getElementById(this.gridId);
            if (!gridContainer) return;

            const table = gridContainer.querySelector(".gridjs-table");
            if (!table) return;

            // Get all header cells (checkbox should be hidden at this point)
            const allHeaderCells = table.querySelectorAll("thead tr th");
            const visibleHeaderCells = Array.from(allHeaderCells).filter((th) => {
                const style = window.getComputedStyle(th);
                return style.display !== "none";
            });

            // Store widths of all visible columns
            this.state.baselineColumnWidths = visibleHeaderCells.map((th, index) => {
                const computedStyle = window.getComputedStyle(th);
                return {
                    width: computedStyle.width,
                    minWidth: computedStyle.minWidth,
                    maxWidth: computedStyle.maxWidth,
                    index: index + 1, // 1-indexed for nth-child
                };
            });
        },

        /**
         * Add bulk actions toolbar
         */
        addBulkToolbar() {
            const gridContainer = document.getElementById(this.gridId);
            if (!gridContainer) return;

            // Create toolbar HTML
            const toolbarHtml = `
                <div class="bulk-actions-toolbar" style="display: none;">
                    <div class="bulk-toolbar-content">
                        <div class="bulk-selection-info">
                            <span class="selected-count">0</span> items selected
                        </div>
                        <div class="bulk-actions">
                            ${
                                this.options.enableBulkDelete
                                    ? `
                                <button type="button" class="btn btn-danger btn-sm quick-action-btn bulk-action-btn"
                                        data-action="bulk-delete" disabled>
                                    <i class="fas fa-trash me-1"></i>Delete Selected
                                </button>
                            `
                                    : ""
                            }
                            ${
                                this.options.enableBulkShare
                                    ? `
                                <button type="button" class="btn btn-success btn-sm quick-action-btn bulk-action-btn"
                                        data-action="bulk-share" disabled>
                                    <i class="fas fa-share-alt me-1"></i>Share Selected
                                </button>
                            `
                                    : ""
                            }
                            <button type="button" class="btn btn-outline-secondary btn-sm" id="cancel-selection-mode">
                                <i class="fas fa-times me-1"></i>Cancel
                            </button>
                        </div>
                    </div>
                </div>
            `;

            // Insert toolbar before the grid
            gridContainer.insertAdjacentHTML("beforebegin", toolbarHtml);
        },

        /**
         * Enter selection mode - show checkboxes for multi-select
         */
        enterSelectionMode() {
            if (this.state.selectionModeActive) return; // Already active

            this.state.selectionModeActive = true;

            const gridContainer = document.getElementById(this.gridId);
            if (gridContainer) {
                const table = gridContainer.querySelector(".gridjs-table");

                // STEP 1: Get Actions column width from baseline (not current state)
                // This ensures we always use the original width, not a modified one
                if (this.state.baselineColumnWidths && this.state.baselineColumnWidths.length > 0) {
                    // Last baseline column is Actions (before checkbox was ever shown)
                    const actionsBaseline =
                        this.state.baselineColumnWidths[this.state.baselineColumnWidths.length - 1];

                    // Calculate what the Actions column index will be after checkbox is shown
                    // (checkbox will be at index 1, pushing Actions to baselineColumnWidths.length + 1)
                    const futureActionsIndex = this.state.baselineColumnWidths.length + 1;

                    // Store Actions width from baseline (we'll capture checkbox width after it renders)
                    this.state.capturedColumnWidths = {
                        actions: {
                            width: actionsBaseline.width,
                            minWidth: actionsBaseline.minWidth,
                            maxWidth: actionsBaseline.maxWidth,
                            index: futureActionsIndex,
                        },
                    };
                } else {
                    console.warn(
                        "[BulkOperations] No baseline widths available, cannot preserve Actions width"
                    );
                    this.state.capturedColumnWidths = {};
                }

                // STEP 2: Show the checkbox column WITHOUT enforcing widths yet
                // Let it render naturally so we can capture its actual width
                gridContainer.classList.add("selection-mode-active");

                // STEP 3: Wait for browser to render the checkbox, then capture and freeze widths
                requestAnimationFrame(() => {
                    // Now checkbox is visible, capture its rendered width
                    const checkboxHeader = table.querySelector("thead tr th:first-child");
                    if (checkboxHeader) {
                        const checkboxStyle = window.getComputedStyle(checkboxHeader);
                        this.state.capturedColumnWidths.checkbox = {
                            width: checkboxStyle.width,
                            minWidth: checkboxStyle.minWidth,
                            maxWidth: checkboxStyle.maxWidth,
                            index: 1,
                        };
                    }

                    // Now freeze both checkbox and Actions at their rendered widths
                    this.enforceColumnWidths(gridContainer);

                    // STEP 4: Bind checkbox events
                    this.bindCheckboxEvents();
                });
            }

            // Show toolbar (even with 0 selected)
            const toolbar = document.querySelector(this.config.selectors.bulkToolbar);
            if (toolbar) {
                toolbar.style.display = "block";
            }

            // Update toggle button appearance
            this.updateToggleButton(true);

            // Ensure button states reflect current selection (0 items on first enter)
            this.updateUI();
        },

        /**
         * Exit selection mode - hide checkboxes
         */
        exitSelectionMode() {
            if (!this.state.selectionModeActive) return; // Already inactive

            this.state.selectionModeActive = false;
            this.clearSelection();

            // Remove CSS class to hide checkbox column
            const gridContainer = document.getElementById(this.gridId);
            if (gridContainer) {
                gridContainer.classList.remove("selection-mode-active");

                // Restore baseline column widths to return to original state
                requestAnimationFrame(() => {
                    this.restoreBaselineWidths(gridContainer);
                });
            }

            // Hide toolbar
            const toolbar = document.querySelector(this.config.selectors.bulkToolbar);
            if (toolbar) {
                toolbar.style.display = "none";
            }

            // Clear captured widths (but keep baseline)
            this.state.capturedColumnWidths = null;

            // Update toggle button appearance
            this.updateToggleButton(false);
        },

        /**
         * Toggle selection mode on/off
         */
        toggleSelectionMode() {
            if (this.state.selectionModeActive) {
                this.exitSelectionMode();
            } else {
                this.enterSelectionMode();
            }
        },

        /**
         * Bind event listeners to checkboxes (called when entering selection mode)
         * Checkboxes already exist in the DOM (managed by Grid.js), we just need to bind events
         */
        bindCheckboxEvents() {
            const gridContainer = document.getElementById(this.gridId);
            if (!gridContainer) return;

            if (gridContainer.dataset.bulkCheckboxEventsBound === "true") return;

            gridContainer.addEventListener("change", (e) => {
                if (e.target.matches(".bulk-select-all")) {
                    this.handleSelectAll(e.target.checked);
                    return;
                }
                if (e.target.matches(".bulk-select-item")) {
                    this.handleItemSelect(e.target);
                }
            });
            gridContainer.dataset.bulkCheckboxEventsBound = "true";
        },

        /**
         * Enforce column widths with inline styles to prevent Grid.js from resizing
         * This is called when entering selection mode to maintain the exact column widths
         * Only freezes checkbox (at captured rendered width) and Actions column (captured pre-checkbox width)
         * All other columns remain flexible
         * @param {HTMLElement} gridContainer - The grid container element
         */
        enforceColumnWidths(gridContainer) {
            const table = gridContainer.querySelector(".gridjs-table");
            if (!table || !this.state.capturedColumnWidths) return;

            const checkboxData = this.state.capturedColumnWidths.checkbox;
            const actionsData = this.state.capturedColumnWidths.actions;

            // If checkbox width not captured yet, don't enforce (will be called again after capture)
            if (!checkboxData || !actionsData) {
                return;
            }

            const actionsColumnIndex = actionsData.index;

            // Apply widths to header cells
            const headerCells = table.querySelectorAll("thead tr th");
            headerCells.forEach((th, index) => {
                const columnIndex = index + 1; // nth-child is 1-indexed

                if (columnIndex === 1) {
                    // Checkbox column: use captured rendered width
                    th.style.width = checkboxData.width;
                    th.style.minWidth = checkboxData.minWidth;
                    th.style.maxWidth = checkboxData.maxWidth;
                } else if (columnIndex === actionsColumnIndex) {
                    // Actions column: use captured pre-checkbox width
                    th.style.width = actionsData.width;
                    th.style.minWidth = actionsData.minWidth;
                    th.style.maxWidth = actionsData.maxWidth;
                }
                // All other columns: no inline styles (remain flexible)
            });

            // Apply widths to body cells (all rows)
            const bodyRows = table.querySelectorAll("tbody tr");
            bodyRows.forEach((row) => {
                const cells = row.querySelectorAll("td");
                cells.forEach((td, index) => {
                    const columnIndex = index + 1; // nth-child is 1-indexed

                    if (columnIndex === 1) {
                        // Checkbox column: use captured rendered width
                        td.style.width = checkboxData.width;
                        td.style.minWidth = checkboxData.minWidth;
                        td.style.maxWidth = checkboxData.maxWidth;
                    } else if (columnIndex === actionsColumnIndex) {
                        // Actions column: use captured pre-checkbox width
                        td.style.width = actionsData.width;
                        td.style.minWidth = actionsData.minWidth;
                        td.style.maxWidth = actionsData.maxWidth;
                    }
                    // All other columns: no inline styles (remain flexible)
                });
            });
        },

        /**
         * Restore baseline column widths (return to original state before selection mode)
         * This is called when exiting selection mode
         * Removes all inline width styles to let the table return to natural layout
         * @param {HTMLElement} gridContainer - The grid container element
         */
        restoreBaselineWidths(gridContainer) {
            const table = gridContainer.querySelector(".gridjs-table");
            if (!table) {
                console.warn("[BulkOperations] Cannot restore - table not found");
                return;
            }

            // Remove inline styles from ALL header cells
            const headerCells = table.querySelectorAll("thead tr th");
            headerCells.forEach((th) => {
                th.style.width = "";
                th.style.minWidth = "";
                th.style.maxWidth = "";
            });

            // Remove inline styles from ALL body cells
            const bodyRows = table.querySelectorAll("tbody tr");
            bodyRows.forEach((row) => {
                const cells = row.querySelectorAll("td");
                cells.forEach((td) => {
                    td.style.width = "";
                    td.style.minWidth = "";
                    td.style.maxWidth = "";
                });
            });
        },

        /**
         * Update the toggle button appearance based on selection mode state
         * @param {boolean} isActive - Whether selection mode is active
         */
        updateToggleButton(isActive) {
            const toggleBtn = document.getElementById(`toggle-selection-${this.gridId}`);
            if (!toggleBtn) return;

            if (isActive) {
                toggleBtn.innerHTML = '<i class="fas fa-times me-1"></i>Cancel';
                toggleBtn.classList.remove("btn-outline-secondary");
                toggleBtn.classList.add("btn-secondary");
            } else {
                toggleBtn.innerHTML = '<i class="fas fa-check-square me-1"></i>Select';
                toggleBtn.classList.remove("btn-secondary");
                toggleBtn.classList.add("btn-outline-secondary");
            }
        },

        /**
         * Bind event handlers
         */
        bindEvents() {
            const gridContainer = document.getElementById(this.gridId);
            if (!gridContainer) return;

            // Checkbox event binding is now done in bindCheckboxEvents() when entering selection mode
            // No need to bind here since checkboxes are hidden initially

            // Bulk action buttons
            const toolbar = gridContainer.parentElement.querySelector(
                this.config.selectors.bulkToolbar
            );
            if (toolbar) {
                toolbar.addEventListener("click", (e) => {
                    if (
                        e.target.matches(this.config.selectors.bulkActionBtn) ||
                        e.target.closest(this.config.selectors.bulkActionBtn)
                    ) {
                        const btn = e.target.matches(this.config.selectors.bulkActionBtn)
                            ? e.target
                            : e.target.closest(this.config.selectors.bulkActionBtn);
                        this.handleBulkAction(btn.getAttribute("data-action"));
                    }
                });
            }

            // Cancel selection mode button (exits selection mode entirely)
            document.addEventListener("click", (e) => {
                if (
                    e.target.matches("#cancel-selection-mode") ||
                    e.target.closest("#cancel-selection-mode")
                ) {
                    this.exitSelectionMode();
                }
            });

            // Listen for grid refresh events to re-enforce column widths if in selection mode
            document.addEventListener("grid:refreshed", (event) => {
                // Only handle events for our grid
                if (event.detail?.containerId !== this.gridId) return;

                // If in selection mode, re-enforce column widths after grid refresh
                if (this.state.selectionModeActive) {
                    const gridContainer = document.getElementById(this.gridId);
                    if (gridContainer) {
                        requestAnimationFrame(() => {
                            this.enforceColumnWidths(gridContainer);
                            // Also re-bind checkbox events for new rows
                            this.bindCheckboxEvents();
                        });
                    }
                }
            });
        },

        /**
         * Bind the selection mode toggle button
         */
        bindToggleButton() {
            const toggleBtn = document.getElementById(`toggle-selection-${this.gridId}`);
            if (toggleBtn) {
                toggleBtn.addEventListener("click", () => {
                    this.toggleSelectionMode();
                });
            }
        },

        /**
         * Handle select all checkbox change
         */
        handleSelectAll(checked) {
            const gridContainer = document.getElementById(this.gridId);
            const itemCheckboxes = gridContainer?.querySelectorAll(
                this.config.selectors.selectItem
            );

            if (!itemCheckboxes) return;

            itemCheckboxes.forEach((checkbox) => {
                checkbox.checked = checked;
                this.updateItemSelection(checkbox, checked);
            });

            this.updateUI();
        },

        /**
         * Handle individual item selection
         */
        handleItemSelect(checkbox) {
            this.updateItemSelection(checkbox, checkbox.checked);
            this.updateSelectAllState();
            this.updateUI();
        },

        /**
         * Update item selection state
         */
        updateItemSelection(checkbox, selected) {
            const entityId = checkbox.value;
            const row = checkbox.closest("tr");

            if (selected) {
                this.state.selectedItems.add(entityId);
                row?.classList.add(this.config.classes.selected);
            } else {
                this.state.selectedItems.delete(entityId);
                row?.classList.remove(this.config.classes.selected);
            }
        },

        /**
         * Update select all checkbox state
         */
        updateSelectAllState() {
            const gridContainer = document.getElementById(this.gridId);
            const selectAllCheckbox = gridContainer?.parentElement.querySelector(
                this.config.selectors.selectAll
            );
            const itemCheckboxes = gridContainer?.querySelectorAll(
                this.config.selectors.selectItem
            );

            if (!selectAllCheckbox || !itemCheckboxes) return;

            const checkedCount = Array.from(itemCheckboxes).filter((cb) => cb.checked).length;
            const totalCount = itemCheckboxes.length;

            selectAllCheckbox.checked = checkedCount === totalCount && totalCount > 0;
            selectAllCheckbox.indeterminate = checkedCount > 0 && checkedCount < totalCount;
        },

        /**
         * Update UI based on selection state
         */
        updateUI() {
            const selectedCount = this.state.selectedItems.size;
            const toolbar = document.querySelector(this.config.selectors.bulkToolbar);
            const countElement = toolbar?.querySelector(this.config.selectors.selectedCount);

            // Update selected count
            if (countElement) {
                countElement.textContent = selectedCount;
            }

            // Show/hide toolbar
            if (toolbar) {
                // In selection mode, toolbar should always be visible (even with 0 items selected)
                // Otherwise, only show if items are selected
                if (this.state.selectionModeActive || selectedCount > 0) {
                    toolbar.style.display = "block";
                    toolbar.classList.add(this.config.classes.toolbarVisible);
                } else {
                    toolbar.style.display = "none";
                    toolbar.classList.remove(this.config.classes.toolbarVisible);
                }
            }

            // Update bulk action button states
            const bulkActionBtns = toolbar?.querySelectorAll(this.config.selectors.bulkActionBtn);
            if (bulkActionBtns) {
                bulkActionBtns.forEach((btn) => {
                    btn.disabled = selectedCount === 0;
                });
            }
        },

        /**
         * Handle bulk actions
         */
        handleBulkAction(action) {
            const selectedIds = Array.from(this.state.selectedItems);

            if (selectedIds.length === 0) {
                this.showNotification("No items selected", "warning");
                return;
            }

            switch (action) {
                case "bulk-delete":
                    this.handleBulkDelete(selectedIds);
                    break;
                case "bulk-share":
                    this.handleBulkShare(selectedIds);
                    break;
                default:
                    console.warn(`[BulkOperations] Unknown action: ${action}`);
            }
        },

        /**
         * Handle bulk delete action
         */
        handleBulkDelete(selectedIds) {
            // Load bulk delete confirmation modal via HTMX
            const langPrefix = this.getLanguagePrefix();
            const confirmationUrl = `${langPrefix}/api/bulk-delete-confirmation/?entity_type=${
                this.state.currentEntityType
            }&entity_ids=${selectedIds.join(",")}`;
            const entityLabel = this.getEntityDisplayLabel(selectedIds.length);

            fetch(confirmationUrl, {
                headers: {
                    "HX-Request": "true",
                },
            })
                .then((response) => response.text())
                .then((html) => {
                    this.showModal("bulk-delete-modal", html, () => {
                        this.executeBulkDelete(selectedIds);
                    });
                })
                .catch((error) => {
                    console.error("[BulkOperations] Error loading confirmation modal:", error);
                    // Fallback to simple confirmation
                    const modalContent = `
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-exclamation-triangle text-warning me-2"></i>
                            Confirm Bulk Delete
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>Are you sure you want to delete <strong>${selectedIds.length}</strong> selected ${entityLabel}?</p>
                        <p class="text-muted">This action cannot be undone.</p>
                        <div class="bulk-delete-progress" style="display: none;">
                            <div class="progress mb-2">
                                <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%"></div>
                            </div>
                            <small class="text-muted">Processing... <span class="progress-text">0 of ${selectedIds.length}</span></small>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-danger" id="confirm-bulk-delete">
                            <i class="fas fa-trash me-1"></i>Delete ${selectedIds.length} Items
                        </button>
                    </div>
                `;
                    this.showModal("bulk-delete-modal", modalContent, () => {
                        this.executeBulkDelete(selectedIds);
                    });
                });
        },

        getEntityDisplayLabel(count = 1) {
            const entityType = this.state.currentEntityType;
            const configuredLabel = this.displayLabels[entityType];

            if (configuredLabel) {
                return count === 1 ? configuredLabel.singular : configuredLabel.plural;
            }

            return count === 1 ? entityType : `${entityType}s`;
        },

        /**
         * Execute bulk delete operation
         */
        async executeBulkDelete(selectedIds) {
            const modal = document.getElementById("bulk-delete-modal");
            const progressContainer = modal.querySelector(".bulk-delete-progress");
            const progressBar = modal.querySelector(".progress-bar");
            const progressText = modal.querySelector(".progress-text");
            const progressPercentage = modal.querySelector(".progress-percentage");
            const confirmBtn = modal.querySelector("#confirm-bulk-delete");
            const resultsContainer = modal.querySelector(".bulk-delete-results");

            // Show progress UI
            if (progressContainer) {
                progressContainer.style.display = "block";
            }
            if (confirmBtn) {
                confirmBtn.disabled = true;
                confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Processing...';
            }

            try {
                // Send bulk delete request
                const langPrefix = this.getLanguagePrefix();
                const response = await fetch(`${langPrefix}/api/bulk-operations/`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": this.getCSRFToken(),
                        "HX-Request": "true",
                    },
                    body: JSON.stringify({
                        action: "bulk_delete",
                        entity_type: this.state.currentEntityType,
                        entity_ids: selectedIds,
                    }),
                });

                const result = await response.json();

                if (result.success) {
                    // Update progress to 100%
                    if (progressBar) {
                        progressBar.style.width = "100%";
                        progressBar.classList.remove("progress-bar-animated");
                    }
                    if (progressText) {
                        progressText.textContent = `${selectedIds.length} of ${selectedIds.length}`;
                    }
                    if (progressPercentage) {
                        progressPercentage.textContent = "100%";
                    }

                    // Show results
                    this.showBulkDeleteResults(modal, result);

                    // Auto-close modal after delay
                    setTimeout(() => {
                        const modalInstance = bootstrap.Modal.getInstance(modal);
                        if (modalInstance) {
                            modalInstance.hide();
                        }
                    }, 2000);

                    // Clear selection and refresh list
                    this.clearSelection();
                    this.triggerListUpdate();
                    this.showNotification(result.message || "Bulk operation completed", "success");
                } else {
                    throw new Error(result.error || "Bulk delete failed");
                }
            } catch (error) {
                console.error("[BulkOperations] Bulk delete error:", error);

                // Show error state
                if (progressContainer) {
                    progressContainer.innerHTML = `
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-circle me-2"></i>
                            Error: ${error.message}
                        </div>
                    `;
                }

                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    confirmBtn.innerHTML = '<i class="fas fa-trash me-1"></i>Try Again';
                }

                this.showNotification("Bulk delete failed: " + error.message, "error");
            }
        },

        /**
         * Show bulk delete results in the modal
         */
        showBulkDeleteResults(modal, result) {
            const resultsContainer = modal.querySelector(".bulk-delete-results");
            if (!resultsContainer) return;

            const deletedCount = result.deleted ? result.deleted.length : 0;
            const unsharedCount = result.shared_removed ? result.shared_removed.length : 0;
            const failedCount = result.failed ? result.failed.length : 0;

            // Update result counters
            const deletedElement = resultsContainer.querySelector(".deleted-count");
            const unsharedElement = resultsContainer.querySelector(".unshared-count");
            const failedElement = resultsContainer.querySelector(".failed-count");

            if (deletedElement) deletedElement.textContent = deletedCount;
            if (unsharedElement) unsharedElement.textContent = unsharedCount;
            if (failedElement) failedElement.textContent = failedCount;

            // Show/hide result items based on counts
            const deletedItem = resultsContainer.querySelector(".result-deleted");
            const unsharedItem = resultsContainer.querySelector(".result-unshared");
            const failedItem = resultsContainer.querySelector(".result-failed");

            if (deletedItem) {
                deletedItem.style.display = deletedCount > 0 ? "flex" : "none";
            }
            if (unsharedItem) {
                unsharedItem.style.display = unsharedCount > 0 ? "flex" : "none";
            }
            if (failedItem) {
                failedItem.style.display = failedCount > 0 ? "flex" : "none";
            }

            // Show results container
            resultsContainer.style.display = "block";
        },

        /**
         * Delete a single entity
         */
        async deleteEntity(entityId) {
            const deleteUrl = this.getEntityDeleteUrl(entityId);

            const response = await fetch(deleteUrl, {
                method: "DELETE",
                headers: {
                    "X-CSRFToken": this.getCSRFToken(),
                    "HX-Request": "true",
                },
            });

            if (!response.ok) {
                throw new Error(`Failed to delete entity ${entityId}`);
            }

            return response;
        },

        /**
         * Handle bulk share action
         */
        handleBulkShare(selectedIds) {
            // For now, redirect to the share page with selected IDs
            const langPrefix = this.getLanguagePrefix();
            const shareUrl = `${langPrefix}/share/?entity_type=${
                this.state.currentEntityType
            }&ids=${selectedIds.join(",")}`;
            window.location.href = shareUrl;
        },

        /**
         * Clear all selections
         */
        clearSelection() {
            this.state.selectedItems.clear();

            const gridContainer = document.getElementById(this.gridId);
            const checkboxes = gridContainer?.querySelectorAll('input[type="checkbox"]');

            if (checkboxes) {
                checkboxes.forEach((checkbox) => {
                    checkbox.checked = false;
                    checkbox.indeterminate = false;
                });
            }

            const rows = gridContainer?.querySelectorAll("tr");
            if (rows) {
                rows.forEach((row) => row.classList.remove(this.config.classes.selected));
            }

            this.updateUI();
        },

        /**
         * Show modal dialog
         */
        showModal(modalId, content, onConfirm) {
            // Remove existing modal
            const existingModal = document.getElementById(modalId);
            if (existingModal) {
                existingModal.remove();
            }

            let modalHtml;
            if (content.includes('<div class="modal-header">')) {
                // Content already includes modal structure
                modalHtml = `
                    <div class="modal fade" id="${modalId}" tabindex="-1">
                        <div class="modal-dialog modal-lg">
                            <div class="modal-content">
                                ${content}
                            </div>
                        </div>
                    </div>
                `;
            } else {
                // Content is just the body, wrap it
                modalHtml = `
                    <div class="modal fade" id="${modalId}" tabindex="-1">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                ${content}
                            </div>
                        </div>
                    </div>
                `;
            }

            document.body.insertAdjacentHTML("beforeend", modalHtml);

            const modal = document.getElementById(modalId);
            const modalInstance = new bootstrap.Modal(modal);

            // Bind confirm action
            const confirmBtn = modal.querySelector("#confirm-bulk-delete");
            if (confirmBtn && onConfirm) {
                confirmBtn.addEventListener("click", onConfirm);
            }

            // Clean up on hide
            modal.addEventListener("hidden.bs.modal", () => {
                modal.remove();
            });

            modalInstance.show();
        },

        /**
         * Utility functions
         */
        getEntityDeleteUrl(entityId) {
            const langPrefix = this.getLanguagePrefix();
            const entityType = this.state.currentEntityType;
            const urlMap = {
                person: `${langPrefix}/persons/${entityId}/delete/`,
                gift: `${langPrefix}/gifts/${entityId}/delete/`,
                event: `${langPrefix}/events/${entityId}/delete/`,
                relation: `${langPrefix}/relations/${entityId}/delete/`,
                persongroup: `${langPrefix}/person-groups/${entityId}/delete/`,
                gifttag: `${langPrefix}/gift-tags/${entityId}/delete/`,
            };
            return urlMap[entityType] || `${langPrefix}/${entityType}s/${entityId}/delete/`;
        },

        getLanguagePrefix() {
            const match = window.location.pathname.match(/^\/([a-z]{2})\//);
            return match ? `/${match[1]}` : "";
        },

        getCSRFToken() {
            // Prefer cookie token (always in sync with session) over form tokens
            // which may be from stale/mismatched form contexts
            return (
                document.cookie
                    .split("; ")
                    .find((c) => c.startsWith("csrftoken="))
                    ?.split("=")[1] ||
                document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
                document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
                ""
            );
        },

        triggerListUpdate() {
            document.dispatchEvent(new CustomEvent("list:update"));
        },

        showNotification(message, type = "info") {
            // Trigger notification event for the main notification system
            document.dispatchEvent(
                new CustomEvent("showNotification", {
                    detail: { message, type },
                })
            );
        },
    };

    // Export to global scope
    window.BulkOperations = BulkOperations;
})(window);
