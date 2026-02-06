/**
 * HTMX-Grid Bridge
 *
 * Event-driven synchronization between HTMX and Grid.js.
 * Listens for HTMX events and updates Grid.js state automatically.
 *
 * Requires: grid-state-manager.js, htmx
 *
 * Usage:
 *   // Initialize after grids are registered
 *   HTMXGridBridge.init();
 *
 *   // Add data attributes to HTMX elements:
 *   <select hx-post="..." data-grid-update="sharing-grid" data-row-id="123" data-update-field="2">
 */

(function(window) {
    'use strict';

    let initialized = false;

    /**
     * Initialize the HTMX-Grid bridge
     * Sets up global event listeners for HTMX events
     */
    function init() {
        if (initialized) {
            console.warn('[HTMXGridBridge] Already initialized');
            return;
        }

        if (typeof htmx === 'undefined') {
            console.error('[HTMXGridBridge] HTMX not loaded');
            return;
        }

        if (typeof GridStateManager === 'undefined') {
            console.error('[HTMXGridBridge] GridStateManager not loaded');
            return;
        }

        // Set up global HTMX event handler
        setupGlobalEventHandler();

        // Set up smart MutationObserver for pagination only
        setupPaginationObserver();

        initialized = true;
        console.log('[HTMXGridBridge] Initialized successfully');
    }

    /**
     * Set up global HTMX afterRequest event handler
     */
    function setupGlobalEventHandler() {
        document.body.addEventListener('htmx:afterRequest', function(event) {
            // Only process successful requests
            if (!event.detail.successful) {
                return;
            }

            const element = event.detail.elt;
            if (!element) {
                return;
            }

            // Check if this element has grid update attributes
            const gridId = element.getAttribute('data-grid-update');
            if (!gridId) {
                return;
            }

            // Get update strategy
            const updateStrategy = element.getAttribute('data-update-strategy') || 'updateRow';

            console.log(`[HTMXGridBridge] Processing ${updateStrategy} for grid: ${gridId}`);

            switch (updateStrategy) {
                case 'updateRow':
                    handleRowUpdate(element, gridId);
                    break;
                case 'refresh':
                    handleGridRefresh(element, gridId);
                    break;
                default:
                    console.warn(`[HTMXGridBridge] Unknown update strategy: ${updateStrategy}`);
            }
        });

        console.log('[HTMXGridBridge] Global event handler registered');
    }

    /**
     * Handle row update strategy
     * Updates specific row data in Grid.js
     */
    function handleRowUpdate(element, gridId) {
        const rowId = element.getAttribute('data-row-id');
        if (!rowId) {
            console.warn('[HTMXGridBridge] Missing data-row-id attribute');
            return;
        }

        // Get update information
        const updateField = element.getAttribute('data-update-field');
        const updateValue = getUpdateValue(element);

        if (updateField === null || updateValue === null) {
            console.warn('[HTMXGridBridge] Missing update field or value');
            return;
        }

        // Build updates object
        const updates = {};

        // Handle multiple field updates (comma-separated)
        const fields = updateField.split(',').map(f => f.trim());
        const values = Array.isArray(updateValue) ? updateValue : [updateValue];

        fields.forEach((field, index) => {
            const value = values[index] !== undefined ? values[index] : updateValue;

            // Try parsing field as number (for array-based rows)
            const fieldIndex = parseInt(field);
            if (!isNaN(fieldIndex)) {
                updates[fieldIndex] = value;
            } else {
                updates[field] = value;
            }
        });

        // Update grid state
        const success = GridStateManager.updateGridRow(gridId, rowId, updates);

        if (success) {
            console.log(`[HTMXGridBridge] Updated row ${rowId} in grid ${gridId}:`, updates);

            // Trigger custom event
            dispatchGridUpdateEvent(gridId, 'rowUpdate', { rowId, updates });
        }
    }

    /**
     * Handle grid refresh strategy
     * Refreshes entire grid from API or data attribute
     */
    function handleGridRefresh(element, gridId) {
        const refreshUrl = element.getAttribute('data-refresh-url');

        if (refreshUrl) {
            // Fetch new data from URL
            fetch(refreshUrl)
                .then(response => response.json())
                .then(data => {
                    const success = GridStateManager.refreshGridData(gridId, data);
                    if (success) {
                        console.log(`[HTMXGridBridge] Refreshed grid ${gridId} from ${refreshUrl}`);
                        dispatchGridUpdateEvent(gridId, 'refresh', { source: refreshUrl });
                    }
                })
                .catch(error => {
                    console.error(`[HTMXGridBridge] Error refreshing grid ${gridId}:`, error);
                });
        } else {
            console.warn('[HTMXGridBridge] Refresh strategy requires data-refresh-url');
        }
    }

    /**
     * Get update value from element
     * Handles select, input, and data attributes
     */
    function getUpdateValue(element) {
        // Check for explicit data-update-value attribute
        const explicitValue = element.getAttribute('data-update-value');
        if (explicitValue !== null) {
            return explicitValue;
        }

        // Get value from form element
        if (element.tagName === 'SELECT' || element.tagName === 'INPUT') {
            return element.value;
        }

        // Check if element is inside a form
        const form = element.closest('form');
        if (form) {
            const formData = new FormData(form);
            const updateField = element.getAttribute('data-update-field');
            if (updateField) {
                // Get form field value
                const fieldName = element.name || updateField;
                return formData.get(fieldName);
            }
        }

        return null;
    }

    /**
     * Set up MutationObserver for pagination events only
     * Much smarter than observing all DOM changes
     */
    function setupPaginationObserver() {
        // Get all registered grids
        const gridIds = GridStateManager.getRegisteredGrids();

        gridIds.forEach(gridId => {
            const container = document.getElementById(gridId);
            if (!container) {
                return;
            }

            // Observe only the pagination footer
            const footer = container.querySelector('.gridjs-footer');
            if (!footer) {
                return;
            }

            const observer = new MutationObserver(function(mutations) {
                // Check if pagination buttons were clicked
                const paginationChanged = mutations.some(mutation => {
                    return Array.from(mutation.addedNodes).some(node => {
                        return node.classList && (
                            node.classList.contains('gridjs-pages') ||
                            node.classList.contains('gridjs-summary')
                        );
                    });
                });

                if (paginationChanged) {
                    // Re-process HTMX on new page content
                    const tbody = container.querySelector('.gridjs-tbody');
                    if (tbody && typeof htmx !== 'undefined') {
                        htmx.process(tbody);
                        console.log(`[HTMXGridBridge] Re-processed HTMX after pagination in ${gridId}`);
                    }
                }
            });

            // Observe footer with minimal configuration
            observer.observe(footer, {
                childList: true,
                subtree: false // Don't observe deep children
            });

            console.log(`[HTMXGridBridge] Set up pagination observer for ${gridId}`);
        });
    }

    /**
     * Dispatch custom grid update event
     */
    function dispatchGridUpdateEvent(gridId, updateType, detail) {
        const event = new CustomEvent('grid:update', {
            detail: {
                gridId,
                updateType,
                ...detail
            }
        });
        document.dispatchEvent(event);
    }

    /**
     * Manually trigger grid update
     * Useful for programmatic updates outside HTMX
     */
    function triggerUpdate(gridId, rowId, updates) {
        const success = GridStateManager.updateGridRow(gridId, rowId, updates);
        if (success) {
            dispatchGridUpdateEvent(gridId, 'manual', { rowId, updates });
        }
        return success;
    }

    /**
     * Re-initialize observers for a specific grid
     * Useful after dynamic grid creation
     */
    function reinitializeGrid(gridId) {
        const container = document.getElementById(gridId);
        if (!container) {
            console.warn(`[HTMXGridBridge] Grid container not found: ${gridId}`);
            return false;
        }

        // Process HTMX elements
        if (typeof htmx !== 'undefined') {
            htmx.process(container);
        }

        // Set up pagination observer for this grid
        const footer = container.querySelector('.gridjs-footer');
        if (footer) {
            const observer = new MutationObserver(function(mutations) {
                const paginationChanged = mutations.some(mutation => {
                    return Array.from(mutation.addedNodes).some(node => {
                        return node.classList && (
                            node.classList.contains('gridjs-pages') ||
                            node.classList.contains('gridjs-summary')
                        );
                    });
                });

                if (paginationChanged) {
                    const tbody = container.querySelector('.gridjs-tbody');
                    if (tbody && typeof htmx !== 'undefined') {
                        htmx.process(tbody);
                    }
                }
            });

            observer.observe(footer, {
                childList: true,
                subtree: false
            });

            console.log(`[HTMXGridBridge] Re-initialized ${gridId}`);
            return true;
        }

        return false;
    }

    // Expose public API
    window.HTMXGridBridge = {
        init,
        triggerUpdate,
        reinitializeGrid
    };

})(window);
