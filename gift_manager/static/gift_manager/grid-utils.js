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
        const actionConfig = {
            give: { class: 'btn-primary', icon: 'fa-hand-holding-heart', title: 'Give' },
            details: { class: 'btn-info', icon: 'fa-eye', title: 'Details' },
            edit: { class: 'btn-warning', icon: 'fa-edit', title: 'Edit' },
            delete: { class: 'btn-danger', icon: 'fa-trash', title: 'Delete' }
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

                    return `<a href="${url}" class="btn ${config.class} btn-sm" title="${config.title}">
                        <i class="fas ${config.icon}"></i>
                    </a>`;
                })
                .filter(Boolean);

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
     * Initialize a Grid.js table with common settings
     * @param {string} containerId - The ID of the container element
     * @param {Array} columns - Array of column definitions
     * @param {Array} data - Array of data rows
     * @param {Object} options - Optional configuration overrides
     * @param {Function} onReady - Optional callback when grid is ready
     */
    function initGrid(containerId, columns, data, options = {}, onReady = null) {
        const config = Object.assign({
            columns: columns,
            data: data,
            search: true,
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
            const grid = new gridjs.Grid(config);
            if (onReady && typeof onReady === 'function') {
                grid.on('ready', onReady);
            }
            grid.render(document.getElementById(containerId));
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

    // Expose utilities to global scope
    window.GridUtils = {
        initGrid: initGrid,
        actionButtonsFormatter: actionButtonsFormatter,
        linkFormatter: linkFormatter,
        multiLinkFormatter: multiLinkFormatter,
        badgeFormatter: badgeFormatter,
        setupFilterDropdown: setupFilterDropdown,
        setupCustomColumnFilter: setupCustomColumnFilter,
        getGridTranslations: getGridTranslations,
        sortByProperty: sortByProperty,
        sortString: sortString
    };

})(window);
