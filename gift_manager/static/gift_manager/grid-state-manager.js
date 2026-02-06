/**
 * Grid State Manager
 *
 * Centralized registry and state management for Grid.js instances.
 * Provides API to update grid data without full re-render and handles
 * row identification for HTMX correlation.
 *
 * Usage:
 *   // Register a grid after initialization
 *   GridStateManager.registerGrid('sharing-grid', gridInstance, originalData);
 *
 *   // Update a specific row's data
 *   GridStateManager.updateGridRow('sharing-grid', userId, {permission: 'editor'});
 *
 *   // Refresh entire grid from new data
 *   GridStateManager.refreshGridData('sharing-grid', newData);
 */

(function(window) {
    'use strict';

    // Registry of all Grid.js instances
    const gridRegistry = new Map();

    /**
     * Register a Grid.js instance for state management
     *
     * @param {string} gridId - Unique identifier for the grid (container element ID)
     * @param {object} gridInstance - The Grid.js instance
     * @param {Array} originalData - The original data array used to initialize the grid
     * @param {object} options - Optional configuration
     * @param {string} options.rowIdField - Index or field name to use as row identifier (default: 0)
     */
    function registerGrid(gridId, gridInstance, originalData, options = {}) {
        const config = {
            rowIdField: options.rowIdField || 0,
            ...options
        };

        gridRegistry.set(gridId, {
            instance: gridInstance,
            data: JSON.parse(JSON.stringify(originalData)), // Deep copy
            config: config
        });

        console.log(`[GridStateManager] Registered grid: ${gridId}`);
        return true;
    }

    /**
     * Get a registered grid instance
     *
     * @param {string} gridId - The grid identifier
     * @returns {object|null} Grid instance or null if not found
     */
    function getGrid(gridId) {
        const entry = gridRegistry.get(gridId);
        return entry ? entry.instance : null;
    }

    /**
     * Get grid data
     *
     * @param {string} gridId - The grid identifier
     * @returns {Array|null} Grid data or null if not found
     */
    function getGridData(gridId) {
        const entry = gridRegistry.get(gridId);
        return entry ? entry.data : null;
    }

    /**
     * Find a row by ID in the grid data
     *
     * @param {string} gridId - The grid identifier
     * @param {string|number} rowId - The row identifier (value of rowIdField)
     * @returns {object|null} Object with {index, row} or null if not found
     */
    function findRowById(gridId, rowId) {
        const entry = gridRegistry.get(gridId);
        if (!entry) {
            console.warn(`[GridStateManager] Grid not found: ${gridId}`);
            return null;
        }

        const { data, config } = entry;
        const rowIdField = config.rowIdField;

        for (let i = 0; i < data.length; i++) {
            const row = data[i];
            const currentId = Array.isArray(row) ? row[rowIdField] : row[rowIdField];

            // Convert both to strings for comparison (handles UUID vs string)
            if (String(currentId) === String(rowId)) {
                return { index: i, row: row };
            }
        }

        console.warn(`[GridStateManager] Row not found: ${rowId} in grid ${gridId}`);
        return null;
    }

    /**
     * Update a specific row's data in the grid
     *
     * @param {string} gridId - The grid identifier
     * @param {string|number} rowId - The row identifier
     * @param {object|Array} updates - Object with field updates or array of cell values
     * @param {object} options - Update options
     * @param {boolean} options.rerender - Whether to re-render the grid (default: true)
     * @returns {boolean} True if update successful
     */
    function updateGridRow(gridId, rowId, updates, options = {}) {
        const entry = gridRegistry.get(gridId);
        if (!entry) {
            console.warn(`[GridStateManager] Grid not found: ${gridId}`);
            return false;
        }

        const rowInfo = findRowById(gridId, rowId);
        if (!rowInfo) {
            return false;
        }

        const { index, row } = rowInfo;
        const { data } = entry;
        const rerender = options.rerender !== false;

        // Handle array-based updates (for array row data)
        if (Array.isArray(updates)) {
            data[index] = updates;
            console.log(`[GridStateManager] Updated row ${rowId} with array data`);
        }
        // Handle object-based updates (for object row data)
        else if (typeof updates === 'object') {
            if (Array.isArray(row)) {
                // For array rows, updates should be index-based
                Object.keys(updates).forEach(key => {
                    const cellIndex = parseInt(key);
                    if (!isNaN(cellIndex) && cellIndex < row.length) {
                        data[index][cellIndex] = updates[key];
                    }
                });
            } else {
                // For object rows, merge updates
                data[index] = { ...row, ...updates };
            }
            console.log(`[GridStateManager] Updated row ${rowId} with fields:`, Object.keys(updates));
        }

        // Re-render grid if requested
        if (rerender) {
            refreshGridData(gridId, data, { skipDataUpdate: true });
        }

        return true;
    }

    /**
     * Refresh the entire grid with new data
     *
     * @param {string} gridId - The grid identifier
     * @param {Array} newData - New data array
     * @param {object} options - Refresh options
     * @param {boolean} options.skipDataUpdate - Skip updating stored data (internal use)
     * @returns {boolean} True if refresh successful
     */
    function refreshGridData(gridId, newData, options = {}) {
        const entry = gridRegistry.get(gridId);
        if (!entry) {
            console.warn(`[GridStateManager] Grid not found: ${gridId}`);
            return false;
        }

        const { instance } = entry;
        const skipDataUpdate = options.skipDataUpdate || false;

        // Update stored data (unless skipped for internal calls)
        if (!skipDataUpdate) {
            entry.data = JSON.parse(JSON.stringify(newData)); // Deep copy
        }

        try {
            // Update Grid.js configuration with new data
            instance.updateConfig({
                data: newData
            }).forceRender();

            console.log(`[GridStateManager] Refreshed grid ${gridId} with ${newData.length} rows`);
            return true;
        } catch (error) {
            console.error(`[GridStateManager] Error refreshing grid ${gridId}:`, error);
            return false;
        }
    }

    /**
     * Unregister a grid (cleanup)
     *
     * @param {string} gridId - The grid identifier
     * @returns {boolean} True if unregistered
     */
    function unregisterGrid(gridId) {
        const removed = gridRegistry.delete(gridId);
        if (removed) {
            console.log(`[GridStateManager] Unregistered grid: ${gridId}`);
        }
        return removed;
    }

    /**
     * Get all registered grid IDs
     *
     * @returns {Array<string>} Array of grid IDs
     */
    function getRegisteredGrids() {
        return Array.from(gridRegistry.keys());
    }

    /**
     * Clear all registered grids
     */
    function clearRegistry() {
        gridRegistry.clear();
        console.log('[GridStateManager] Cleared all registered grids');
    }

    // Expose public API
    window.GridStateManager = {
        registerGrid,
        getGrid,
        getGridData,
        findRowById,
        updateGridRow,
        refreshGridData,
        unregisterGrid,
        getRegisteredGrids,
        clearRegistry
    };

})(window);
