/**
 * Grid.js Utilities
 * Reusable utilities for initializing and customizing Grid.js tables
 * Requires Grid.js to be loaded first
 */

(function (window) {
    'use strict';

    /**
     * Get translations for Grid.js from Django's i18n
     */
    function getGridTranslations() {
        const translations = window.gridTranslations || {};

        return {
            search: {
                placeholder: translations.search || 'Search...'
            },
            pagination: {
                previous: translations.previous || 'Previous',
                next: translations.next || 'Next',
                showing: translations.showing || 'Showing',
                of: translations.of || 'of',
                to: translations.to || 'to',
                results: translations.results || 'results'
            },
            loading: translations.loading || 'Loading...',
            noRecordsFound: translations.noRecordsFound || 'No matching records found',
            error: translations.error || 'An error occurred while loading data'
        };
    }

    /**
     * Create action buttons formatter for CRUD operations with modern UX enhancements
     *
     * @param urls Object with URL templates (e.g., {details: '/persons/{id}/'})
     *             OR functions that take (row) and return the URL
     * @param actions Array of action names to display OR objects with {type, condition}
     *                condition is optional and takes (row) => boolean
     * @param options Optional {idResolver: function(row) => id} to get ID from row instead of cell
     */
    function actionButtonsFormatter(urls, actions, options = {}) {
        const actionConfig = {
            give: {
                class: 'btn-primary',
                icon: 'fa-hand-holding-heart',
                title: 'Give',
                action: 'create' // Maps to data-action for modern UX handling
            },
            details: {
                class: 'btn-info',
                icon: 'fa-eye',
                title: 'Details',
                action: 'detail'
            },
            edit: {
                class: 'btn-warning',
                icon: 'fa-edit',
                title: 'Edit',
                action: 'edit'
            },
            delete: {
                class: 'btn-danger',
                icon: 'fa-trash',
                title: 'Delete',
                action: 'delete'
            },
            share: {
                class: 'btn-success',
                icon: 'fa-share-alt',
                title: 'Share',
                action: 'share'
            },
            expand: {
                class: 'btn-outline-secondary',
                icon: 'fa-chevron-down',
                title: 'Expand',
                action: 'expand'
            }
        };

        return function (cell, row) {
            const id = options.idResolver ? options.idResolver(row) : cell;

            const resolveUrl = (urlTemplate, actionId) => {
                if (typeof urlTemplate === 'function') return urlTemplate(row);
                return urlTemplate ? urlTemplate.replace('{id}', actionId || id) : null;
            };

            const shouldDisplay = (action) => {
                if (typeof action === 'string') return true;
                return !action.condition || action.condition(row);
            };

            const buttons = actions
                .filter(shouldDisplay)
                .map(action => {
                    const actionType = typeof action === 'string' ? action : action.type;
                    const urlTemplate = urls[actionType];
                    const config = actionConfig[actionType];

                    if (!urlTemplate || !config) return null;

                    const url = resolveUrl(urlTemplate, typeof action === 'object' ? action.id : null);
                    if (!url) return null;

                    // Enhanced button with modern UX attributes and hover effects
                    return `<a href="${url}"
                              class="btn ${config.class} btn-sm quick-action-btn"
                              title="${config.title}"
                              data-action="${config.action}"
                              data-entity-id="${id}"
                              ${config.action === 'detail' ? 'data-detail-url="' + url + '"' : ''}
                              ${config.action === 'edit' ? 'data-edit-url="' + url + '"' : ''}
                              ${config.action === 'delete' ? 'data-delete-url="' + url + '"' : ''}
                              ${config.action === 'expand' ? 'data-detail-url="' + url + '"' : ''}
                              data-bs-toggle="tooltip"
                              data-bs-placement="top">
                        <i class="fas ${config.icon}"></i>
                        <span class="btn-text d-none d-lg-inline ms-1">${config.title}</span>
                    </a>`;
                })
                .filter(Boolean);

            return gridjs.html(`<div class="quick-actions-container">${buttons.join('')}</div>`);
        };
    }

    /**
     * Create link formatter for columns that should be links
     */
    function linkFormatter(urlTemplate, textField, idField) {
        return function (cell) {
            if (!cell || typeof cell !== 'object') {
                return cell || '';
            }

            const text = cell[textField] || cell.name || cell;
            const id = cell[idField] || cell.id;

            if (!id || !urlTemplate) {
                return text;
            }

            return gridjs.html(`<a href="${urlTemplate.replace('{id}', id)}">${text}</a>`);
        };
    }

    /**
     * Helper to resolve URL from item or template
     */
    function resolveItemUrl(item, urlTemplate) {
        if (!item) return null;
        if (item.url) return item.url;
        if (urlTemplate && item.id) return urlTemplate.replace('{id}', item.id);
        return null;
    }

    /**
     * Create multi-link formatter for arrays of links (e.g., groups)
     * @param urlTemplate Optional URL template (e.g., '/groups/{id}/'). If not provided, expects items to have a 'url' property
     * @param separator String to separate links (default: ', ')
     */
    function multiLinkFormatter(urlTemplate = null, separator = ', ') {
        return function (cell) {
            if (!cell || !Array.isArray(cell) || cell.length === 0) return '';

            const links = cell
                .map(item => {
                    if (!item) return '';
                    const text = item.name || item;
                    const url = resolveItemUrl(item, urlTemplate);
                    return url ? `<a href="${url}">${text}</a>` : text;
                })
                .filter(Boolean);

            return gridjs.html(links.join(separator));
        };
    }

    /**
     * Create badge formatter for tags
     * @param urlTemplate Optional URL template (e.g., '/tags/{id}/'). If not provided, expects items to have a 'url' property
     */
    function badgeFormatter(urlTemplate = null) {
        return function (cell) {
            if (!cell || !Array.isArray(cell) || cell.length === 0) return '';

            const badges = cell
                .map(tag => {
                    if (!tag) return '';
                    const text = tag.name || tag;
                    const url = resolveItemUrl(tag, urlTemplate);
                    const badgeClass = 'badge bg-primary';
                    return url ? `<a href="${url}" class="${badgeClass}">${text}</a>`
                        : `<span class="${badgeClass}">${text}</span>`;
                })
                .filter(Boolean);

            return gridjs.html(badges.join(' '));
        };
    }

    /**
     * Initialize a Grid.js table with common settings and optional inline editing
     * @param {string} containerId - The ID of the container element
     * @param {Array} columns - Array of column definitions
     * @param {Array} data - Array of data rows
     * @param {Object} options - Optional configuration overrides
     * @param {Function} onReady - Optional callback when grid is ready
     * @param {Object} inlineEditingConfig - Optional inline editing configuration
     *                 {entityType: 'person', columnMapping: {0: 'first_name', 1: 'family_name'}}
     */
    function initGrid(containerId, columns, data, options = {}, onReady = null, inlineEditingConfig = null) {
        const config = Object.assign({
            columns: columns,
            data: data,
            search: false, // Disabled - using custom search in filter panel
            pagination: { enabled: true, limit: 10 },
            sort: true,
            language: getGridTranslations(),
            className: {
                table: 'table table-striped',
                th: 'gridjs-th',
                td: 'gridjs-td'
            }
        }, options);

        try {
            const container = document.getElementById(containerId);
            if (!container) {
                console.error(`[GridUtils.initGrid] Container element with ID '${containerId}' not found`);
                throw new Error(`Container element with ID '${containerId}' not found`);
            }

            const grid = new gridjs.Grid(config);

            // Store the container ID on the grid instance for later use
            grid._containerId = containerId;

            // Call user-provided onReady callback if exists
            if (onReady && typeof onReady === 'function') {
                grid.on('ready', onReady);
            }

            // Initialize inline editing if configured
            if (inlineEditingConfig && window.InlineEditing) {
                grid.on('ready', () => {
                    window.InlineEditing.init(
                        containerId,
                        inlineEditingConfig.entityType,
                        inlineEditingConfig.columnMapping
                    );
                });
            }

            grid.render(container);

            // Hide pagination footer if only one page
            // Use a longer timeout to ensure Grid.js has fully rendered
            const paginationLimit = config.pagination && config.pagination.limit ? config.pagination.limit : 10;
            const totalRows = data.length;

            if (config.pagination && config.pagination.enabled && totalRows <= paginationLimit) {
                setTimeout(function() {
                    const container = document.getElementById(containerId);
                    const footer = container ? container.querySelector('.gridjs-footer') : null;
                    if (footer) {
                        // Add a class to hide the footer permanently
                        footer.classList.add('gridjs-footer-hidden');
                        // Also set inline style with !important via cssText
                        footer.style.cssText = 'display: none !important;';
                    }
                }, 100);
            }

            return grid;
        } catch (error) {
            console.error('[GridUtils.initGrid] Error:', error);
            throw error;
        }
    }

    /**
     * Setup custom dropdown filter UI
     */
    function setupFilterDropdown(filterIconSelector, dropdownSelector) {
        // Show/hide dropdown on filter icon click
        document.querySelectorAll(filterIconSelector).forEach(function (icon) {
            icon.addEventListener('click', function (e) {
                e.stopPropagation();
                const container = this.parentElement;
                const dropdown = container.querySelector(dropdownSelector);

                if (dropdown) {
                    const isVisible = dropdown.style.display === 'block';
                    // Hide all dropdowns first
                    document.querySelectorAll(dropdownSelector).forEach(function (d) {
                        d.style.display = 'none';
                    });
                    // Toggle this one
                    dropdown.style.display = isVisible ? 'none' : 'block';
                }
            });
        });

        // Hide dropdown when clicking outside
        document.addEventListener('click', function () {
            document.querySelectorAll(dropdownSelector).forEach(function (el) {
                el.style.display = 'none';
            });
        });

        // Prevent closing when clicking inside dropdown
        document.querySelectorAll(dropdownSelector).forEach(function (el) {
            el.addEventListener('click', function (e) {
                e.stopPropagation();
            });
        });
    }

    /**
     * Custom column filter using checkboxes
     */
    function setupCustomColumnFilter(grid, columnIndex, checkboxSelector) {
        // Store original data
        const originalData = grid.config.store.state.data || grid.config.data;

        function applyFilter() {
            const selected = Array.from(document.querySelectorAll(checkboxSelector + ':checked'))
                .map(function (cb) { return cb.value; });

            if (selected.length === 0) {
                // No filter, show all
                grid.updateConfig({
                    data: originalData
                }).forceRender();
            } else {
                // Filter based on selected values
                const filtered = originalData.filter(function (row) {
                    const cellValue = row[columnIndex];

                    return selected.some(function (value) {
                        if (typeof cellValue === 'string') {
                            return cellValue.includes(value);
                        } else if (Array.isArray(cellValue)) {
                            return cellValue.some(function (v) {
                                return (v.name === value) || (v === value);
                            });
                        }
                        return false;
                    });
                });

                grid.updateConfig({
                    data: filtered
                }).forceRender();
            }
        }

        document.querySelectorAll(checkboxSelector).forEach(function (cb) {
            cb.addEventListener('change', applyFilter);
        });
    }

    /**
     * Create a comparator function for sorting objects by a specific property
     */
    function sortByProperty(property) {
        return function (a, b) {
            if (!a && !b) return 0;
            if (!a) return -1;
            if (!b) return 1;

            const valA = (a[property] || '').toString();
            const valB = (b[property] || '').toString();

            return valA.localeCompare(valB, undefined, { sensitivity: 'base' });
        };
    }

    /**
     * Create a comparator function for sorting strings accent-insensitively
     */
    function sortString() {
        return function (a, b) {
            if (!a && !b) return 0;
            if (!a) return -1;
            if (!b) return 1;

            const valA = a.toString();
            const valB = b.toString();

            return valA.localeCompare(valB, undefined, { sensitivity: 'base' });
        };
    }

    /**
     * Create a comparator function for sorting date objects with iso/display properties
     * Expected format: { iso: "YYYY-MM-DD", display: "localized date" } or null
     */
    function sortDateObject() {
        return function (a, b) {
            // Extract ISO date for sorting
            const isoA = (a && typeof a === 'object' && a.iso) ? a.iso : null;
            const isoB = (b && typeof b === 'object' && b.iso) ? b.iso : null;

            // Handle null/empty values - sort them to the end
            if (!isoA && !isoB) return 0;
            if (!isoA) return 1;
            if (!isoB) return -1;

            // Compare ISO date strings directly (YYYY-MM-DD format)
            // This works because ISO format is lexicographically sortable
            if (isoA < isoB) return -1;
            if (isoA > isoB) return 1;
            return 0;
        };
    }

    /**
     * Enable expandable rows functionality for Grid.js
     * @param {string} containerId - The ID of the grid container
     * @param {Object} grid - The Grid.js instance
     * @param {Object} options - Configuration options
     *                 {detailUrlTemplate: '/entity/{id}/', expandButtonColumn: 'actions'}
     */
    function enableExpandableRows(containerId, grid, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`[GridUtils.enableExpandableRows] Container element with ID '${containerId}' not found`);
            return;
        }

        // Add CSS class to container to enable expandable row styling
        container.classList.add('expandable-grid');

        // Handle expand button clicks
        container.addEventListener('click', function(e) {
            const expandButton = e.target.closest('[data-action="expand"]');
            if (!expandButton) return;

            e.preventDefault();
            e.stopPropagation();

            const row = expandButton.closest('tr');
            if (!row) return;

            const entityId = expandButton.dataset.entityId;
            const detailUrl = expandButton.dataset.detailUrl;

            if (!entityId || !detailUrl) {
                console.error('[GridUtils.enableExpandableRows] Missing entity ID or detail URL');
                return;
            }

            toggleExpandableRow(row, entityId, detailUrl, expandButton);
        });

        /**
         * Toggle expandable row content
         */
        function toggleExpandableRow(row, entityId, detailUrl, button) {
            const existingDetailRow = row.nextElementSibling;
            const isExpanded = existingDetailRow && existingDetailRow.classList.contains('expandable-detail-row');

            if (isExpanded) {
                // Collapse
                collapseRow(existingDetailRow, button);
            } else {
                // Expand
                expandRow(row, entityId, detailUrl, button);
            }
        }

        /**
         * Expand a row to show details
         */
        function expandRow(row, entityId, detailUrl, button) {
            // Update button icon
            const icon = button.querySelector('i');
            if (icon) {
                icon.className = 'fas fa-chevron-up';
            }
            button.setAttribute('aria-expanded', 'true');
            button.title = 'Collapse';

            // Create detail row
            const colCount = row.cells.length;
            const detailRow = document.createElement('tr');
            detailRow.className = 'expandable-detail-row';
            detailRow.innerHTML = `
                <td colspan="${colCount}" class="expandable-detail-cell">
                    <div class="expandable-detail-content">
                        <div class="text-center p-3">
                            <i class="fas fa-spinner fa-spin"></i> Loading details...
                        </div>
                    </div>
                </td>
            `;

            // Insert after current row
            row.parentNode.insertBefore(detailRow, row.nextSibling);

            // Load content via HTMX
            const detailContent = detailRow.querySelector('.expandable-detail-content');

            // Use fetch to load content
            fetch(detailUrl, {
                headers: {
                    'HX-Request': 'true',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                return response.text();
            })
            .then(html => {
                detailContent.innerHTML = html;
                detailRow.setAttribute('data-loaded', 'true');

                // Animate expansion
                animateExpansion(detailRow);
            })
            .catch(error => {
                console.error('Failed to load expandable content:', error);
                detailContent.innerHTML = `
                    <div class="text-center p-3 text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Failed to load details.
                        <button class="btn btn-sm btn-outline-primary ms-2" onclick="this.closest('tr').previousElementSibling.querySelector('[data-action=expand]').click()">
                            Retry
                        </button>
                    </div>
                `;
            });
        }

        /**
         * Collapse an expanded row
         */
        function collapseRow(detailRow, button) {
            // Update button icon
            const icon = button.querySelector('i');
            if (icon) {
                icon.className = 'fas fa-chevron-down';
            }
            button.setAttribute('aria-expanded', 'false');
            button.title = 'Expand';

            // Animate collapse and remove
            animateCollapse(detailRow, () => {
                if (detailRow.parentNode) {
                    detailRow.parentNode.removeChild(detailRow);
                }
            });
        }

        /**
         * Animate row expansion
         */
        function animateExpansion(row) {
            const content = row.querySelector('.expandable-detail-content');
            if (!content) return;

            // Set initial state
            content.style.maxHeight = '0px';
            content.style.overflow = 'hidden';
            content.style.transition = 'max-height 0.3s ease-out';

            // Force reflow
            content.offsetHeight;

            // Animate to full height
            content.style.maxHeight = content.scrollHeight + 'px';

            // Clean up after animation
            content.addEventListener('transitionend', function handler() {
                content.style.maxHeight = 'none';
                content.style.overflow = 'visible';
                content.removeEventListener('transitionend', handler);
            });
        }

        /**
         * Animate row collapse
         */
        function animateCollapse(row, callback) {
            const content = row.querySelector('.expandable-detail-content');
            if (!content) {
                if (callback) callback();
                return;
            }

            // Set current height
            content.style.maxHeight = content.scrollHeight + 'px';
            content.style.overflow = 'hidden';
            content.style.transition = 'max-height 0.3s ease-out';

            // Force reflow
            content.offsetHeight;

            // Animate to zero height
            content.style.maxHeight = '0px';

            // Remove after animation
            content.addEventListener('transitionend', function handler() {
                content.removeEventListener('transitionend', handler);
                if (callback) callback();
            });
        }
    }

    /**
     * Formatter for date objects with iso/display properties
     * Displays the localized date string
     */
    function dateObjectFormatter(cell) {
        if (!cell) return '';
        return cell.display || cell;
    }

    /**
     * Add list update event listener for automatic grid updates after CRUD operations
     * @param {Object} grid - The Grid.js instance
     * @param {string} entityType - The type of entity (e.g., 'person', 'gift')
     * @param {number} idColumnIndex - The index of the ID column in the data array
     * @param {Function} postUpdateCallback - Optional callback to run after grid update
     */
    function addListUpdateListener(grid, entityType, idColumnIndex, postUpdateCallback = null) {
        document.addEventListener('list:update', function(event) {
            console.log(`[${entityType}List] Received list:update event, updating grid...`);

            // Try to get the deleted item ID from the modal or delete context
            const deletedItemId = getDeletedItemId();

            if (deletedItemId) {
                // Remove the specific row from grid data (delete operation)
                removeItemFromGrid(grid, deletedItemId, entityType, idColumnIndex, postUpdateCallback);
            } else {
                // This is likely a create or update operation
                // Refresh grid data smoothly without full page reload
                console.log(`[${entityType}List] Create/update operation detected, refreshing grid data...`);
                refreshGridData(grid, entityType, idColumnIndex, postUpdateCallback);
            }
        });
    }

    /**
     * Wait for Grid.js to finish rendering after forceRender()
     * Uses MutationObserver to detect when DOM mutations have stopped
     * @param {HTMLElement} gridContainer - The grid container element
     * @param {Function} callback - Callback to execute when rendering is complete
     * @param {number} debounceMs - Milliseconds of inactivity to wait (default: 50ms)
     * @param {number} safetyTimeoutMs - Maximum time to wait before forcing callback (default: 2000ms)
     */
    function waitForGridRenderComplete(gridContainer, callback, debounceMs = 50, safetyTimeoutMs = 2000) {
        let debounceTimer;
        let safetyTimer;

        const observer = new MutationObserver(() => {
            // Clear previous debounce timer
            clearTimeout(debounceTimer);

            // Set new debounce timer
            // Will only execute if no more mutations occur for debounceMs
            debounceTimer = setTimeout(() => {
                observer.disconnect();
                clearTimeout(safetyTimer);
                console.log('[GridUtils] Grid rendering complete (detected via MutationObserver)');
                callback();
            }, debounceMs);
        });

        // Start observing DOM changes in the grid container
        observer.observe(gridContainer, {
            childList: true,
            subtree: true
        });

        // Safety timeout: force callback if mutations continue for too long
        safetyTimer = setTimeout(() => {
            clearTimeout(debounceTimer);
            observer.disconnect();
            console.warn('[GridUtils] MutationObserver safety timeout reached, forcing callback');
            callback();
        }, safetyTimeoutMs);
    }

    /**
     * Refresh grid data by fetching fresh data from the current page
     * @param {Object} grid - The Grid.js instance
     * @param {string} entityType - The type of entity
     * @param {number} idColumnIndex - The index of the ID column
     * @param {Function} postUpdateCallback - Optional callback to run after update
     */
    function refreshGridData(grid, entityType, idColumnIndex, postUpdateCallback = null) {
        // Build URL with cache-busting parameter to ensure fresh data
        const url = new URL(window.location.href);
        url.searchParams.set('_t', Date.now());

        // Log current data count and URL for debugging
        const currentDataCount = (grid.config.data || []).length;
        console.log(`[${entityType}List] Current data count before refresh: ${currentDataCount}`);
        console.log(`[${entityType}List] Fetching fresh data from: ${url.toString()}`);

        // Fetch the current page to get updated data
        // Use cache: 'no-store' and headers to bypass all caching
        // Include credentials to ensure session cookies are sent
        fetch(url.toString(), {
            cache: 'no-store',
            credentials: 'same-origin',
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache'
            }
        })
        .then(response => response.text())
        .then(html => {
            // Extract the data array using bracket counting (more robust than regex for nested arrays)
            const dataArrayStr = extractDataArray(html);

            if (dataArrayStr) {
                try {
                    // Use Function constructor to safely evaluate the array
                    // This handles the complex object structures in the data
                    const extractedData = new Function('return ' + dataArrayStr)();

                    console.log(`[${entityType}List] Extracted ${extractedData.length} items from refreshed data`);
                    // Log first few items for debugging
                    if (extractedData.length > 0) {
                        console.log(`[${entityType}List] First item (sample):`, extractedData[0]);
                        // Log all IDs (assuming ID is at a consistent index, typically 4 for persons)
                        const ids = extractedData.map(item => item[4] || item.id || 'unknown');
                        console.log(`[${entityType}List] Extracted IDs:`, ids);
                    }

                    // Also extract and update permissions if available
                    const permissionsStr = extractPermissions(html);
                    console.log(`[${entityType}List] Extracted permissions string: ${permissionsStr ? permissionsStr.substring(0, 200) + '...' : 'null'}`);
                    if (permissionsStr) {
                        try {
                            const extractedPermissions = new Function('return ' + permissionsStr)();
                            console.log(`[${entityType}List] Parsed permissions:`, extractedPermissions);
                            console.log(`[${entityType}List] Permission IDs:`, Object.keys(extractedPermissions));

                            // Update global permissions variable IN PLACE
                            // We need to modify the existing object, not replace it,
                            // because the formatter has a closure reference to it
                            if (window.userPermissions !== undefined && typeof window.userPermissions === 'object') {
                                console.log(`[${entityType}List] Before update, userPermissions:`, {...window.userPermissions});
                                // Clear existing keys
                                Object.keys(window.userPermissions).forEach(key => delete window.userPermissions[key]);
                                // Add new keys
                                Object.assign(window.userPermissions, extractedPermissions);
                                console.log(`[${entityType}List] After update, userPermissions:`, {...window.userPermissions});
                                console.log(`[${entityType}List] Updated userPermissions with ${Object.keys(extractedPermissions).length} entries`);
                            }
                            // Also update PermissionUtils if it has a setter
                            if (window.PermissionUtils && window.PermissionUtils.updatePermissions) {
                                window.PermissionUtils.updatePermissions(extractedPermissions);
                            }
                        } catch (permError) {
                            console.warn(`[${entityType}List] Could not update permissions:`, permError);
                        }
                    } else {
                        console.warn(`[${entityType}List] No permissions extracted from HTML`);
                    }

                    // Update the grid using updateConfig (same method as delete operation)
                    console.log(`[${entityType}List] About to call forceRender. userPermissions now has ${Object.keys(window.userPermissions || {}).length} entries:`, window.userPermissions);

                    // Update the grid
                    grid.updateConfig({
                        data: extractedData
                    }).forceRender();
                    console.log(`[${entityType}List] forceRender called (rendering may still be in progress)`);

                    // Wait for Grid.js to finish rendering using MutationObserver
                    // This detects when DOM mutations have stopped, indicating rendering is complete
                    const gridContainer = document.getElementById(grid._containerId);
                    if (gridContainer) {
                        waitForGridRenderComplete(gridContainer, () => {
                            console.log(`[${entityType}List] Grid rendering complete, emitting grid:refreshed event`);
                            console.log(`[${entityType}List] Emitting grid:refreshed event with containerId:`, grid._containerId);
                            document.dispatchEvent(new CustomEvent('grid:refreshed', {
                                detail: { containerId: grid._containerId, entityType: entityType }
                            }));
                            console.log(`[${entityType}List] grid:refreshed event emitted`);
                        });
                    } else {
                        console.warn(`[${entityType}List] Grid container not found, cannot wait for render completion`);
                    }

                    // Update global data variable if it exists
                    if (window.data !== undefined) {
                        window.data = extractedData;
                    }

                    // Show/hide pagination footer based on data length
                    updatePaginationVisibility(grid, extractedData.length);

                    // After grid renders, update UI based on permissions
                    // This ensures buttons are enabled/disabled correctly after refresh
                    setTimeout(() => {
                        // Get the container ID from the grid instance (stored by initGrid)
                        const containerId = grid._containerId;
                        if (containerId && window.PermissionUtils && window.userPermissions) {
                            console.log(`[${entityType}List] Calling updateUIForPermissions for container ${containerId} with ${Object.keys(window.userPermissions).length} permissions`);
                            window.PermissionUtils.updateUIForPermissions(containerId, window.userPermissions);
                        } else {
                            console.warn(`[${entityType}List] Cannot call updateUIForPermissions: containerId=${containerId}, PermissionUtils=${!!window.PermissionUtils}, userPermissions=${!!window.userPermissions}`);
                        }
                    }, 50);

                    // Run post-update callback if provided
                    if (postUpdateCallback && typeof postUpdateCallback === 'function') {
                        setTimeout(postUpdateCallback, 100);
                    }

                    console.log(`[${entityType}List] Grid data refreshed successfully`);
                } catch (parseError) {
                    console.error(`[${entityType}List] Error parsing refreshed data:`, parseError);
                    // Fallback to page reload on parse error
                    setTimeout(() => window.location.reload(), 300);
                }
            } else {
                console.warn(`[${entityType}List] Could not extract data from page, falling back to reload`);
                setTimeout(() => window.location.reload(), 300);
            }
        })
        .catch(error => {
            console.error(`[${entityType}List] Error fetching page data:`, error);
            // Fallback to page reload on fetch error
            setTimeout(() => window.location.reload(), 300);
        });
    }

    /**
     * Extract the data array from HTML using bracket counting
     * This is more robust than regex for nested arrays
     * @param {string} html - The HTML content
     * @returns {string|null} - The data array string or null if not found
     */
    function extractDataArray(html) {
        // Find the start of the data declaration
        const startMarker = 'const data = [';
        const startIndex = html.indexOf(startMarker);

        if (startIndex === -1) {
            console.warn('[extractDataArray] Could not find "const data = [" marker');
            return null;
        }

        // Start counting brackets from the opening bracket
        const arrayStartIndex = startIndex + startMarker.length - 1; // Position of '['
        let bracketCount = 1;
        let i = arrayStartIndex + 1;
        let inString = false;
        let stringChar = null;
        let escapeNext = false;

        while (i < html.length && bracketCount > 0) {
            const char = html[i];

            if (escapeNext) {
                escapeNext = false;
                i++;
                continue;
            }

            if (char === '\\' && inString) {
                escapeNext = true;
                i++;
                continue;
            }

            if ((char === '"' || char === "'") && !inString) {
                inString = true;
                stringChar = char;
            } else if (char === stringChar && inString) {
                inString = false;
                stringChar = null;
            } else if (!inString) {
                if (char === '[') {
                    bracketCount++;
                } else if (char === ']') {
                    bracketCount--;
                }
            }

            i++;
        }

        if (bracketCount === 0) {
            // Found the matching closing bracket
            const arrayStr = html.substring(arrayStartIndex, i);
            console.log('[extractDataArray] Successfully extracted data array');
            return arrayStr;
        }

        console.warn('[extractDataArray] Could not find matching closing bracket');
        return null;
    }

    /**
     * Extract the userPermissions object from HTML
     * @param {string} html - The HTML content
     * @returns {string|null} - The permissions object string or null if not found
     */
    function extractPermissions(html) {
        // Look for window.userPermissions = { FIRST (the actual JSON object)
        // This is important because the template has:
        //   window.userPermissions = {...};
        //   const userPermissions = window.userPermissions;
        // We need to match the first line, not the second
        const primaryMarker = 'window.userPermissions = {';
        const primaryIndex = html.indexOf(primaryMarker);

        if (primaryIndex !== -1) {
            // Found the actual JSON object assignment
            // Position at the opening brace
            const objStart = primaryIndex + 'window.userPermissions = '.length;
            console.log('[extractPermissions] Found window.userPermissions = { at position', primaryIndex);
            return extractObjectFromPosition(html, objStart);
        }

        // Fallback: try const userPermissions = { (might be used in some templates)
        const altMarker = 'const userPermissions = {';
        const altIndex = html.indexOf(altMarker);
        if (altIndex !== -1) {
            const objStart = altIndex + 'const userPermissions = '.length;
            console.log('[extractPermissions] Found const userPermissions = { at position', altIndex);
            return extractObjectFromPosition(html, objStart);
        }

        console.log('[extractPermissions] No userPermissions JSON object found in HTML');
        return null;
    }

    /**
     * Extract a JSON object starting from a position in HTML
     * @param {string} html - The HTML content
     * @param {number} startPos - Starting position of the object
     * @returns {string|null} - The object string or null if not found
     */
    function extractObjectFromPosition(html, startPos) {
        // Find the opening brace
        if (html[startPos] !== '{') {
            console.warn('[extractObjectFromPosition] Expected { at position', startPos);
            return null;
        }

        let braceCount = 1;
        let i = startPos + 1;
        let inString = false;
        let stringChar = null;
        let escapeNext = false;

        while (i < html.length && braceCount > 0) {
            const char = html[i];

            if (escapeNext) {
                escapeNext = false;
                i++;
                continue;
            }

            if (char === '\\' && inString) {
                escapeNext = true;
                i++;
                continue;
            }

            if ((char === '"' || char === "'") && !inString) {
                inString = true;
                stringChar = char;
            } else if (char === stringChar && inString) {
                inString = false;
                stringChar = null;
            } else if (!inString) {
                if (char === '{') {
                    braceCount++;
                } else if (char === '}') {
                    braceCount--;
                }
            }

            i++;
        }

        if (braceCount === 0) {
            const objStr = html.substring(startPos, i);
            console.log('[extractPermissions] Successfully extracted permissions object');
            return objStr;
        }

        console.warn('[extractPermissions] Could not find matching closing brace');
        return null;
    }

    /**
     * Update pagination footer visibility based on data length
     * @param {Object} grid - The Grid.js instance
     * @param {number} dataLength - The number of rows in the data
     */
    function updatePaginationVisibility(grid, dataLength) {
        const paginationConfig = grid.config.pagination;
        if (paginationConfig && paginationConfig.enabled) {
            const paginationLimit = paginationConfig.limit || 10;

            setTimeout(function() {
                const containers = document.querySelectorAll('.gridjs-wrapper');
                for (const container of containers) {
                    const footer = container.querySelector('.gridjs-footer');
                    if (footer) {
                        if (dataLength <= paginationLimit) {
                            // Hide footer if only one page
                            footer.classList.add('gridjs-footer-hidden');
                            footer.style.cssText = 'display: none !important;';
                        } else {
                            // Show footer if multiple pages
                            footer.classList.remove('gridjs-footer-hidden');
                            footer.style.cssText = '';
                        }
                    }
                }
            }, 100);
        }
    }

    /**
     * Get the ID of the deleted item from the delete modal or context
     */
    function getDeletedItemId() {
        // Primary method: Get from the delete form in the modal
        const deleteForm = document.getElementById('deleteForm');
        if (deleteForm && deleteForm.action) {
            // Extract UUID from delete URL (e.g., /persons/uuid/delete/)
            const uuidMatch = deleteForm.action.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/);
            if (uuidMatch) {
                console.log('Found deleted item ID from modal form:', uuidMatch[1]);
                return uuidMatch[1];
            }
        }

        // Fallback method: Check if there's a modal with delete URL data
        const confirmModal = document.getElementById('confirmModal');
        if (confirmModal) {
            const modalBody = confirmModal.querySelector('.modal-body');
            if (modalBody) {
                const form = modalBody.querySelector('form[action*="/delete/"]');
                if (form && form.action) {
                    const uuidMatch = form.action.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/);
                    if (uuidMatch) {
                        console.log('Found deleted item ID from modal body form:', uuidMatch[1]);
                        return uuidMatch[1];
                    }
                }
            }
        }

        console.warn('Could not determine deleted item ID from modal');
        return null;
    }

    /**
     * Reset all delete button states in the grid to their default enabled state
     */
    function resetDeleteButtonStates() {
        console.log('[GridUtils] Resetting delete button states...');

        // Find all delete buttons in grid containers
        const deleteButtons = document.querySelectorAll('.gridjs-wrapper [data-action="delete"]');

        deleteButtons.forEach(button => {
            // Re-enable the button
            button.disabled = false;

            // Reset button text and remove any loading indicators
            const btnText = button.querySelector('.btn-text');
            if (btnText) {
                btnText.textContent = 'Delete';
            }

            // Remove any spinner icons that might have been added
            const spinner = button.querySelector('.fa-spinner');
            if (spinner) {
                spinner.remove();
            }

            // Ensure the trash icon is present
            const icon = button.querySelector('i');
            if (icon && !icon.classList.contains('fa-trash')) {
                icon.className = 'fas fa-trash';
            }

            // Reset any inline styles that might have been applied
            button.style.pointerEvents = '';
            button.style.opacity = '';

            // Remove any disabled-related classes
            button.classList.remove('disabled');
        });

        console.log(`[GridUtils] Reset ${deleteButtons.length} delete button states`);
    }

    /**
     * Remove a specific item from the grid by ID
     */
    function removeItemFromGrid(gridInstance, itemId, entityType, idColumnIndex, postUpdateCallback) {
        console.log(`[${entityType}List] Removing item from grid:`, itemId);

        // Get current data from grid
        const currentData = gridInstance.config.data || window.data;

        // Find the item in the data array
        const itemIndex = currentData.findIndex(row => row[idColumnIndex] === itemId);

        if (itemIndex !== -1) {
            // Create new data array without the deleted item
            const newData = [...currentData];
            newData.splice(itemIndex, 1);

            // Update the grid with new data
            gridInstance.updateConfig({
                data: newData
            }).forceRender();

            // Wait for Grid.js to finish rendering using MutationObserver
            const gridContainer = document.getElementById(gridInstance._containerId);
            if (gridContainer) {
                waitForGridRenderComplete(gridContainer, () => {
                    console.log(`[${entityType}List] Grid rendering complete after delete, emitting grid:refreshed event`);
                    document.dispatchEvent(new CustomEvent('grid:refreshed', {
                        detail: { containerId: gridInstance._containerId, entityType: entityType }
                    }));
                });
            } else {
                console.warn(`[${entityType}List] Grid container not found after delete, cannot wait for render completion`);
            }

            // Update global data variable
            if (window.data) {
                window.data = newData;
            }

            // Hide pagination footer if only one page after update
            const paginationConfig = gridInstance.config.pagination;
            if (paginationConfig && paginationConfig.enabled) {
                const paginationLimit = paginationConfig.limit || 10;
                const totalRows = newData.length;

                if (totalRows <= paginationLimit) {
                    setTimeout(function() {
                        // Find the grid container by looking for the grid instance's container
                        const containers = document.querySelectorAll('.gridjs-wrapper');
                        for (const container of containers) {
                            const footer = container.querySelector('.gridjs-footer');
                            if (footer) {
                                // Add a class to hide the footer permanently
                                footer.classList.add('gridjs-footer-hidden');
                                // Also set inline style with !important via cssText
                                footer.style.cssText = 'display: none !important;';
                            }
                        }
                    }, 100);
                }
            }

            // Run post-update callback if provided
            if (postUpdateCallback && typeof postUpdateCallback === 'function') {
                setTimeout(() => {
                    postUpdateCallback();
                }, 150); // Slightly longer delay to ensure footer hiding runs first
            }

            // Reset all delete button states after grid update
            setTimeout(function() {
                resetDeleteButtonStates();
            }, 120);

            console.log(`[${entityType}List] Item removed from grid successfully`);
        } else {
            console.warn(`[${entityType}List] Item not found in grid data:`, itemId);
            // Fallback to page reload if item not found
            setTimeout(() => window.location.reload(), 500);
        }
    }

    // Expose utilities to global scope
    window.GridUtils = {
        initGrid: initGrid,
        actionButtonsFormatter: actionButtonsFormatter,
        linkFormatter: linkFormatter,
        multiLinkFormatter: multiLinkFormatter,
        badgeFormatter: badgeFormatter,
        setupFilterDropdown: setupFilterDropdown,
        setupCustomColumnFilter: setupCustomColumnFilter,
        enableExpandableRows: enableExpandableRows,
        getGridTranslations: getGridTranslations,
        sortByProperty: sortByProperty,
        sortString: sortString,
        sortDateObject: sortDateObject,
        dateObjectFormatter: dateObjectFormatter,
        addListUpdateListener: addListUpdateListener,
        resetDeleteButtonStates: resetDeleteButtonStates
    };

})(window);
