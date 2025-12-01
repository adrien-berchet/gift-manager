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
     */
    function actionButtonsFormatter(urls, actions, idField = 0) {
        return function (cell, row) {
            // Get the ID from the specified cell index
            const id = row._cells[idField].data;

            const buttons = [];

            if (actions.includes('give') && urls.give) {
                buttons.push(`
                    <a href="${urls.give.replace('{id}', id)}"
                       class="btn btn-primary btn-sm"
                       title="Give">
                        <i class="fas fa-hand-holding-heart"></i>
                    </a>
                `);
            }

            if (actions.includes('details') && urls.details) {
                buttons.push(`
                    <a href="${urls.details.replace('{id}', id)}"
                       class="btn btn-info btn-sm"
                       title="Details">
                        <i class="fas fa-eye"></i>
                    </a>
                `);
            }

            if (actions.includes('edit') && urls.edit) {
                buttons.push(`
                    <a href="${urls.edit.replace('{id}', id)}"
                       class="btn btn-warning btn-sm"
                       title="Edit">
                        <i class="fas fa-edit"></i>
                    </a>
                `);
            }

            if (actions.includes('delete') && urls.delete) {
                buttons.push(`
                    <a href="${urls.delete.replace('{id}', id)}"
                       class="btn btn-danger btn-sm"
                       title="Delete">
                        <i class="fas fa-trash"></i>
                    </a>
                `);
            }

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
     */
    function multiLinkFormatter(urlTemplate, separator = ', ') {
        return function (cell) {
            if (!cell || !Array.isArray(cell) || cell.length === 0) {
                return '';
            }

            const links = cell.map(item => {
                const text = item.name || item;
                const id = item.id;
                return `<a href="${urlTemplate.replace('{id}', id)}">${text}</a>`;
            }).join(separator);

            return gridjs.html(links);
        };
    }

    /**
     * Create badge formatter for tags
     */
    function badgeFormatter(urlTemplate) {
        return function (cell) {
            if (!cell || !Array.isArray(cell) || cell.length === 0) {
                return '';
            }

            const badges = cell.map(tag =>
                `<a href="${urlTemplate.replace('{id}', tag.id)}" class="badge bg-primary">${tag.name}</a>`
            ).join(' ');

            return gridjs.html(badges);
        };
    }

    /**
     * Initialize a Grid.js table with common settings
     */
    function initGrid(containerId, columns, data, options = {}) {
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

        const grid = new gridjs.Grid(config);
        grid.render(document.getElementById(containerId));

        return grid;
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
