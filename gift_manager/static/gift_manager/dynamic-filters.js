/**
 * Dynamic filtering system for Grid.js tables
 * Provides real-time filtering with state persistence
 */

(function() {
    'use strict';

    // Configuration
    const FILTER_DEBOUNCE_DELAY = 200; // milliseconds
    const STORAGE_PREFIX = 'filter-state-';

    /**
     * Initialize dynamic filtering for a grid
     * @param {string} gridId - The ID of the grid container
     * @param {object} grid - The Grid.js instance
     * @param {Array} originalData - The original data array
     * @param {Array} columns - The columns configuration
     */
    function initDynamicFilters(gridId, grid, originalData, columns) {
        const filterPanel = document.getElementById(gridId + '-filter-panel');
        const filterContent = document.getElementById(gridId + '-filter-content');

        if (!filterPanel || !filterContent) {
            console.warn('Dynamic filters: Filter panel not found for grid:', gridId);
            return;
        }

        // State management
        const filterState = {
            search: '',
            columnFilters: new Map(),
            sortState: []
        };

        // Load saved filter state
        loadFilterState(gridId, filterState);

        // Create dynamic filter controls
        createDynamicFilterControls(gridId, filterContent, columns, originalData);

        // Set up filter event handlers
        setupFilterEventHandlers(gridId, grid, originalData, filterState);

        // Apply initial filters
        applyFilters(grid, originalData, filterState);

        console.log(`[DynamicFilters] Initialized for grid: ${gridId}`);
    }

    /**
     * Create dynamic filter controls for each column
     */
    function createDynamicFilterControls(gridId, filterContent, columns, originalData) {
        // Find or create filters section
        let filtersSection = filterContent.querySelector('.filters-section');
        if (!filtersSection) {
            filtersSection = document.createElement('div');
            filtersSection.className = 'filter-section filters-section';
            filtersSection.innerHTML = `
                <label class="filter-section-label">
                    <i class="fas fa-filter me-1"></i>Filters
                </label>
                <div class="filters-container"></div>
            `;

            // Insert after search section
            const searchSection = filterContent.querySelector('.search-section');
            if (searchSection) {
                searchSection.parentNode.insertBefore(filtersSection, searchSection.nextSibling);
            } else {
                filterContent.appendChild(filtersSection);
            }
        }

        const filtersContainer = filtersSection.querySelector('.filters-container');

        // Create filters for each filterable column
        columns.forEach((column, index) => {
            if (column.hidden || column.sort === false) return;

            const columnName = typeof column === 'object' ? (column.name || column.id) : column;
            if (!columnName || columnName.toLowerCase().includes('action')) return;

            // Determine filter type based on data
            const filterType = determineFilterType(originalData, index, columnName);

            if (filterType) {
                createColumnFilter(filtersContainer, gridId, columnName, index, filterType, originalData);
            }
        });
    }

    /**
     * Determine the appropriate filter type for a column
     */
    function determineFilterType(data, columnIndex, columnName) {
        if (data.length === 0) return null;

        // Sample some values to determine type
        const sampleSize = Math.min(10, data.length);
        const samples = [];

        for (let i = 0; i < sampleSize; i++) {
            const value = data[i][columnIndex];
            if (value !== null && value !== undefined && value !== '') {
                samples.push(value);
            }
        }

        if (samples.length === 0) return null;

        // Check for date patterns
        if (samples.some(val => isDateValue(val))) {
            return 'date';
        }

        // Check for boolean patterns
        if (samples.every(val => typeof val === 'boolean' || val === 'true' || val === 'false')) {
            return 'boolean';
        }

        // Check for numeric patterns
        if (samples.every(val => !isNaN(parseFloat(val)) && isFinite(val))) {
            return 'number';
        }

        // Check for limited unique values (good for select filters)
        const uniqueValues = [...new Set(samples.map(val => extractFilterValue(val)))];
        if (uniqueValues.length <= 10 && uniqueValues.length > 1) {
            return 'select';
        }

        // Default to text filter
        return 'text';
    }

    /**
     * Check if a value represents a date
     */
    function isDateValue(value) {
        if (typeof value === 'object' && value !== null) {
            return value.iso || value.display; // Date object format
        }

        // Check for date strings
        const dateRegex = /^\d{4}-\d{2}-\d{2}$|^\d{1,2}\/\d{1,2}\/\d{4}$/;
        return typeof value === 'string' && dateRegex.test(value);
    }

    /**
     * Extract filterable value from complex data structures
     */
    function extractFilterValue(value) {
        if (value === null || value === undefined) return '';

        if (typeof value ===

        return String(value);
    }

    /**
     * Create a filter control for a specific column
     */
    function createColumnFilter(container, gridId, columnName, columnIndex, filterType, originalData) {
        const filterId = `${gridId}-filter-${columnIndex}`;
        const filterWrapper = document.createElement('div');
        filterWrapper.className = 'column-filter-wrapper';

        let filterHTML = '';

        switch (filterType) {
            case 'select':
                const uniqueValues = getUniqueColumnValues(originalData, columnIndex);
                const options = uniqueValues.map(value =>
                    `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`
                ).join('');

                filterHTML = `
                    <label class="column-filter-label">${escapeHtml(columnName)}</label>
                    <select class="form-select form-select-sm column-filter"
                            id="${filterId}"
                            data-column-index="${columnIndex}"
                            data-filter-type="select">
                        <option value="">All ${escapeHtml(columnName)}</option>
                        ${options}
                    </select>
                `;
                break;

            case 'date':
                filterHTML = `
                    <label class="column-filter-label">${escapeHtml(columnName)}</label>
                    <div class="date-filter-group">
                        <input type="date" class="form-control form-control-sm column-filter"
                               id="${filterId}-from"
                               data-column-index="${columnIndex}"
                               data-filter-type="date-from"
                               placeholder="From">
                        <input type="date" class="form-control form-control-sm column-filter"
                               id="${filterId}-to"
                               data-column-index="${columnIndex}"
                               data-filter-type="date-to"
                               placeholder="To">
                    </div>
                `;
                break;

            case 'number':
                filterHTML = `
                    <label class="column-filter-label">${escapeHtml(columnName)}</label>
                    <div class="number-filter-group">
                        <input type="number" class="form-control form-control-sm column-filter"
                               id="${filterId}-min"
                               data-column-index="${columnIndex}"
                               data-filter-type="number-min"
                               placeholder="Min">
                        <input type="number" class="form-control form-control-sm column-filter"
                               id="${filterId}-max"
                               data-column-index="${columnIndex}"
                               data-filter-type="number-max"
                               placeholder="Max">
                    </div>
                `;
                break;

            case 'boolean':
                filterHTML = `
                    <label class="column-filter-label">${escapeHtml(columnName)}</label>
                    <select class="form-select form-select-sm column-filter"
                            id="${filterId}"
                            data-column-index="${columnIndex}"
                            data-filter-type="boolean">
                        <option value="">All</option>
                        <option value="true">Yes</option>
                        <option value="false">No</option>
                    </select>
                `;
                break;

            default: // text
                filterHTML = `
                    <label class="column-filter-label">${escapeHtml(columnName)}</label>
                    <input type="text" class="form-control form-control-sm column-filter"
                           id="${filterId}"
                           data-column-index="${columnIndex}"
                           data-filter-type="text"
                           placeholder="Filter ${escapeHtml(columnName)}...">
                `;
                break;
        }

        filterWrapper.innerHTML = filterHTML;
        container.appendChild(filterWrapper);
    }

    /**
     * Get unique values for a column (for select filters)
     */
    function getUniqueColumnValues(data, columnIndex) {
        const values = new Set();

        data.forEach(row => {
            const value = extractFilterValue(row[columnIndex]);
            if (value && value.trim()) {
                values.add(value.trim());
            }
        });

        return Array.from(values).sort();
    }

    /**
     * Set up event handlers for filter controls
     */
    function setupFilterEventHandlers(gridId, grid, originalData, filterState) {
        const filterContent = document.getElementById(gridId + '-filter-content');
        let filterTimeout;

        // Handle filter input changes
        filterContent.addEventListener('input', (e) => {
            if (e.target.classList.contains('column-filter')) {
                clearTimeout(filterTimeout);
                filterTimeout = setTimeout(() => {
                    updateFilterState(e.target, filterState);
                    applyFilters(grid, originalData, filterState);
                    saveFilterState(gridId, filterState);
                }, FILTER_DEBOUNCE_DELAY);
            }
        });

        // Handle filter select changes
        filterContent.addEventListener('change', (e) => {
            if (e.target.classList.contains('column-filter')) {
                updateFilterState(e.target, filterState);
                applyFilters(grid, originalData, filterState);
                saveFilterState(gridId, filterState);
            }
        });

        // Handle search input separately (already handled by real-time search)
        const searchInput = document.getElementById(gridId + '-search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                filterState.search = e.target.value;
                saveFilterState(gridId, filterState);
            });
        }

        // Add clear filters button
        addClearFiltersButton(gridId, filterContent, filterState, grid, originalData);
    }

    /**
     * Update filter state based on input changes
     */
    function updateFilterState(input, filterState) {
        const columnIndex = parseInt(input.dataset.columnIndex);
        const filterType = input.dataset.filterType;
        const value = input.value;

        if (!filterState.columnFilters.has(columnIndex)) {
            filterState.columnFilters.set(columnIndex, {});
        }

        const columnFilter = filterState.columnFilters.get(columnIndex);

        switch (filterType) {
            case 'date-from':
                columnFilter.dateFrom = value;
                break;
            case 'date-to':
                columnFilter.dateTo = value;
                break;
            case 'number-min':
                columnFilter.numberMin = value ? parseFloat(value) : null;
                break;
            case 'number-max':
                columnFilter.numberMax = value ? parseFloat(value) : null;
                break;
            default:
                columnFilter.value = value;
                break;
        }

        // Clean up empty filters
        if (Object.values(columnFilter).every(v => !v && v !== 0)) {
            filterState.columnFilters.delete(columnIndex);
        }
    }

    /**
     * Apply all filters to the grid
     */
    function applyFilters(grid, originalData, filterState) {
        let filteredData = [...originalData];

        // Apply column filters
        filterState.columnFilters.forEach((filter, columnIndex) => {
            filteredData = filteredData.filter(row => {
                const cellValue = row[columnIndex];
                return matchesColumnFilter(cellValue, filter);
            });
        });

        // Update grid with filtered data
        try {
            grid.updateConfig({
                data: filteredData
            }).forceRender();

            // Update empty state
            updateEmptyState(grid, filteredData.length > 0, filterState);

            // Trigger custom event
            const event = new CustomEvent('filters:applied', {
                detail: {
                    gridId: grid.config.container.id,
                    resultCount: filteredData.length,
                    filterState: filterState
                }
            });
            document.dispatchEvent(event);

        } catch (error) {
            console.error('Error applying filters:', error);
        }
    }

    /**
     * Check if a cell value matches a column filter
     */
    function matchesColumnFilter(cellValue, filter) {
        const value = extractFilterValue(cellValue);

        // Text filter
        if (filter.value !== undefined) {
            if (!filter.value) return true; // Empty filter matches all
            return value.toLowerCase().includes(filter.value.toLowerCase());
        }

        // Date range filter
        if (filter.dateFrom || filter.dateTo) {
            const dateValue = extractDateValue(cellValue);
            if (!dateValue) return false;

            if (filter.dateFrom && dateValue < filter.dateFrom) return false;
            if (filter.dateTo && dateValue > filter.dateTo) return false;
            return true;
        }

        // Number range filter
        if (filter.numberMin !== null || filter.numberMax !== null) {
            const numValue = parseFloat(value);
            if (isNaN(numValue)) return false;

            if (filter.numberMin !== null && numValue < filter.numberMin) return false;
            if (filter.numberMax !== null && numValue > filter.numberMax) return false;
            return true;
        }

        return true;
    }

    /**
     * Extract date value for comparison
     */
    function extractDateValue(value) {
        if (typeof value === 'object' && value !== null) {
            return value.iso || value.display;
        }
        return value;
    }

    /**
     * Add clear filters button
     */
    function addClearFiltersButton(gridId, filterContent, filterState, grid, originalData) {
        const filtersSection = filterContent.querySelector('.filters-section');
        if (!filtersSection) return;

        const clearButton = document.createElement('button');
        clearButton.type = 'button';
        clearButton.className = 'btn btn-sm btn-outline-secondary clear-filters-btn';
        clearButton.innerHTML = '<i class="fas fa-times me-1"></i>Clear Filters';
        clearButton.style.marginTop = '0.5rem';

        clearButton.addEventListener('click', () => {
            // Clear all filter inputs
            filterContent.querySelectorAll('.column-filter').forEach(input => {
                input.value = '';
            });

            // Clear filter state
            filterState.columnFilters.clear();

            // Apply filters (will show all data)
            applyFilters(grid, originalData, filterState);
            saveFilterState(gridId, filterState);
        });

        filtersSection.appendChild(clearButton);
    }

    /**
     * Update empty state display
     */
    function updateEmptyState(grid, hasData, filterState) {
        const gridContainer = grid.config.container;

        // Remove existing empty state
        let emptyState = gridContainer.querySelector('.grid-empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        // Show/hide grid table
        const gridTable = gridContainer.querySelector('.gridjs-table');
        if (gridTable) {
            gridTable.style.display = hasData ? '' : 'none';
        }

        // Show empty state if no data
        if (!hasData) {
            emptyState = document.createElement('div');
            emptyState.className = 'grid-empty-state';

            const hasActiveFilters = filterState.search || filterState.columnFilters.size > 0;
            const message = hasActiveFilters
                ? 'No results match your current filters'
                : 'No data available';
            const icon = hasActiveFilters ? 'fa-filter' : 'fa-inbox';

            emptyState.innerHTML = `
                <div class="empty-state-content">
                    <i class="fas ${icon} empty-state-icon"></i>
                    <p class="empty-state-message">${message}</p>
                    ${hasActiveFilters ? '<button class="btn btn-sm btn-outline-secondary clear-all-filters-btn">Clear all filters</button>' : ''}
                </div>
            `;

            // Add clear all filters functionality
            const clearBtn = emptyState.querySelector('.clear-all-filters-btn');
            if (clearBtn) {
                clearBtn.addEventListener('click', () => {
                    // Clear search
                    const searchInput = document.getElementById(gridContainer.id + '-search');
                    if (searchInput) searchInput.value = '';

                    // Clear all filter inputs
                    const filterContent = document.getElementById(gridContainer.id + '-filter-content');
                    if (filterContent) {
                        filterContent.querySelectorAll('.column-filter').forEach(input => {
                            input.value = '';
                        });
                    }

                    // Clear filter state
                    filterState.search = '';
                    filterState.columnFilters.clear();

                    // Apply filters
                    applyFilters(grid, grid.config.data, filterState);
                    saveFilterState(gridContainer.id, filterState);
                });
            }

            // Insert empty state
            const gridFooter = gridContainer.querySelector('.gridjs-footer');
            if (gridFooter) {
                gridFooter.parentNode.insertBefore(emptyState, gridFooter);
            } else {
                gridContainer.appendChild(emptyState);
            }
        }
    }

    /**
     * Save filter state to localStorage
     */
    function saveFilterState(gridId, filterState) {
        try {
            const stateToSave = {
                search: filterState.search,
                columnFilters: Array.from(filterState.columnFilters.entries()),
                timestamp: Date.now()
            };
            localStorage.setItem(STORAGE_PREFIX + gridId, JSON.stringify(stateToSave));
        } catch (error) {
            console.warn('Failed to save filter state:', error);
        }
    }

    /**
     * Load filter state from localStorage
     */
    function loadFilterState(gridId, filterState) {
        try {
            const saved = localStorage.getItem(STORAGE_PREFIX + gridId);
            if (saved) {
                const parsed = JSON.parse(saved);

                // Only load if not too old (24 hours)
                if (Date.now() - parsed.timestamp < 24 * 60 * 60 * 1000) {
                    filterState.search = parsed.search || '';
                    filterState.columnFilters = new Map(parsed.columnFilters || []);

                    // Apply saved search value
                    setTimeout(() => {
                        const searchInput = document.getElementById(gridId + '-search');
                        if (searchInput && filterState.search) {
                            searchInput.value = filterState.search;
                        }
                    }, 100);
                }
            }
        } catch (error) {
            console.warn('Failed to load filter state:', error);
        }
    }

    /**
     * Utility function to escape HTML
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Expose to global scope
    window.DynamicFilters = {
        init: initDynamicFilters
    };

})();
