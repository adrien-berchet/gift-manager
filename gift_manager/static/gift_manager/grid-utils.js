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
     * Create action buttons formatter for CRUD operations
     *
     * @param urls Object with URL templates (e.g., {details: '/persons/{id}/'})
     *             OR functions that take (row) and return the URL
     * @param actions Array of action names to display OR objects with {type, condition}
     *                condition is optional and takes (row) => boolean
     * @param options Optional {idResolver: function(row) => id} to get ID from row instead of cell
     */
    function actionButtonsFormatter(urls, actions, options = {}) {
        return function (cell, row) {
            // Get ID - either from cell, or use custom resolver
            const id = options.idResolver ? options.idResolver(row) : cell;

            const buttons = [];

            // Helper to check if action should be displayed
            const shouldDisplay = (action) => {
                if (typeof action === 'string') return true;
                return !action.condition || action.condition(row);
            };

            // Helper to get action type
            const getActionType = (action) => {
                return typeof action === 'string' ? action : action.type;
            };

            // Helper to resolve URL
            const resolveUrl = (urlTemplate, actionId) => {
                if (typeof urlTemplate === 'function') {
                    return urlTemplate(row);
                }
                return urlTemplate.replace('{id}', actionId || id);
            };

            // Process each action
            actions.forEach(action => {
                const actionType = getActionType(action);

                if (!shouldDisplay(action)) return;

                if (actionType === 'give' && urls.give) {
                    const url = resolveUrl(urls.give, action.id);
                    buttons.push(`
                        <a href="${url}"
                           class="btn btn-primary btn-sm"
                           title="Give">
                            <i class="fas fa-hand-holding-heart"></i>
                        </a>
                    `);
                }

                if (actionType === 'details' && urls.details) {
                    const url = resolveUrl(urls.details, action.id);
                    buttons.push(`
                        <a href="${url}"
                           class="btn btn-info btn-sm"
                           title="Details">
                            <i class="fas fa-eye"></i>
                        </a>
                    `);
                }

                if (actionType === 'edit' && urls.edit) {
                    const url = resolveUrl(urls.edit, action.id);
                    buttons.push(`
                        <a href="${url}"
                           class="btn btn-warning btn-sm"
                           title="Edit">
                            <i class="fas fa-edit"></i>
                        </a>
                    `);
                }

                if (actionType === 'delete' && urls.delete) {
                    const url = resolveUrl(urls.delete, action.id);
                    buttons.push(`
                        <a href="${url}"
                           class="btn btn-danger btn-sm"
                           title="Delete">
                            <i class="fas fa-trash"></i>
                        </a>
                    `);
                }
            });

            return gridjs.html(`<div style="white-space: nowrap;">${buttons.join(' ')}</div>`);
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

            if (!id) {
                return text;
            }

            return gridjs.html(`<a href="${urlTemplate.replace('{id}', id)}">${text}</a>`);
        };
    }

    /**
     * Create multi-link formatter for arrays of links (e.g., groups)
     * @param urlTemplate Optional URL template (e.g., '/groups/{id}/'). If not provided, expects items to have a 'url' property
     * @param separator String to separate links (default: ', ')
     */
    function multiLinkFormatter(urlTemplate = null, separator = ', ') {
        return function (cell) {
            if (!cell || !Array.isArray(cell) || cell.length === 0) {
                return '';
            }

            const links = cell.map(item => {
                const text = item.name || item;
                const id = item.id;

                // Use item.url if available, otherwise use urlTemplate
                let url;
                if (item.url) {
                    url = item.url;
                } else if (urlTemplate) {
                    url = urlTemplate.replace('{id}', id);
                } else {
                    // No URL available, just return text
                    return text;
                }

                return `<a href="${url}">${text}</a>`;
            }).join(separator);

            return gridjs.html(links);
        };
    }

    /**
     * Create badge formatter for tags
     * @param urlTemplate Optional URL template (e.g., '/tags/{id}/'). If not provided, expects items to have a 'url' property
     */
    function badgeFormatter(urlTemplate = null) {
        return function (cell) {
            if (!cell || !Array.isArray(cell) || cell.length === 0) {
                return '';
            }

            const badges = cell.map(tag => {
                const text = tag.name || tag;
                const id = tag.id;

                // Use tag.url if available, otherwise use urlTemplate
                let url;
                if (tag.url) {
                    url = tag.url;
                } else if (urlTemplate) {
                    url = urlTemplate.replace('{id}', id);
                } else {
                    // No URL available, just return text as badge without link
                    return `<span class="badge bg-primary">${text}</span>`;
                }

                return `<a href="${url}" class="badge bg-primary">${text}</a>`;
            }).join(' ');

            return gridjs.html(badges);
        };
    }

    /**
     * Initialize a Grid.js table with common settings
     * @param {string} containerId - The ID of the container element
     * @param {Array} columns - Array of column definitions
     * @param {Array} data - Array of data rows
     * @param {Object} options - Optional configuration overrides
     * @param {Function} onReady - Optional callback when grid is ready
     */
    function initGrid(containerId, columns, data, options = {}, onReady = null) {
        console.log('[GridUtils.initGrid] Starting initialization');
        console.log('[GridUtils.initGrid] containerId:', containerId);
        console.log('[GridUtils.initGrid] data length:', data ? data.length : 0);
        console.log('[GridUtils.initGrid] onReady callback provided:', typeof onReady === 'function');

        const translations = getGridTranslations();

        const defaultOptions = {
            columns: columns,
            data: data,
            search: true,
            pagination: {
                enabled: true,
                limit: 10
            },
            sort: true,
            language: translations,
            className: {
                table: 'table table-striped',
                th: 'gridjs-th',
                td: 'gridjs-td'
            }
        };

        const config = Object.assign({}, defaultOptions, options);
        console.log('[GridUtils.initGrid] Config created');

        try {
            const grid = new gridjs.Grid(config);
            console.log('[GridUtils.initGrid] Grid object created');

            // Attach ready event listener BEFORE rendering if callback provided
            if (onReady && typeof onReady === 'function') {
                console.log('[GridUtils.initGrid] Attaching ready event listener');
                grid.on('ready', onReady);
                console.log('[GridUtils.initGrid] Ready event listener attached');
            }

            console.log('[GridUtils.initGrid] About to call render()');
            grid.render(document.getElementById(containerId));
            console.log('[GridUtils.initGrid] Render completed');

            return grid;
        } catch (error) {
            console.error('[GridUtils.initGrid] Error during initialization:', error);
            console.error('[GridUtils.initGrid] Error stack:', error.stack);
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

    // Expose utilities to global scope
    window.GridUtils = {
        initGrid: initGrid,
        actionButtonsFormatter: actionButtonsFormatter,
        linkFormatter: linkFormatter,
        multiLinkFormatter: multiLinkFormatter,
        badgeFormatter: badgeFormatter,
        setupFilterDropdown: setupFilterDropdown,
        setupCustomColumnFilter: setupCustomColumnFilter,
        getGridTranslations: getGridTranslations
    };

})(window);
