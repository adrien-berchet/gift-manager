/**
 * Grid.js Utilities
 * Reusable utilities for initializing and customizing Grid.js tables
 * Requires Grid.js to be loaded first
 */

(function (window) {
    'use strict';

    // Grid.js override rules moved to vendor/gridjs-mermaid.css (self-hosted).
    // No runtime CSS injection needed.

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

    function escapeHtml(value) {
        const replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        };
        return String(value ?? '').replace(/[&<>"']/g, character => replacements[character]);
    }

    function escapeAttribute(value) {
        return escapeHtml(value);
    }

    function sanitizeUrl(value) {
        const url = String(value ?? '').trim();
        if (!url) return '';
        if (/^(https?:|mailto:|#)/i.test(url)) return url;
        if (url.startsWith('/') && !url.startsWith('//')) return url;
        return '#';
    }

    function safeUrl(value) {
        return escapeAttribute(sanitizeUrl(value));
    }

    function linkHtml(url, text, attrs = '') {
        const extraAttrs = attrs ? ` ${attrs}` : '';
        return `<a href="${safeUrl(url)}"${extraAttrs}>${escapeHtml(text)}</a>`;
    }

    function badgeHtml(text, url = null, badgeClass = 'badge bg-primary', attrs = '') {
        const classAttr = escapeAttribute(badgeClass);
        const extraAttrs = attrs ? ` ${attrs}` : '';
        const label = escapeHtml(text);
        if (url) {
            return `<a href="${safeUrl(url)}" class="${classAttr}"${extraAttrs}>${label}</a>`;
        }
        return `<span class="${classAttr}"${extraAttrs}>${label}</span>`;
    }

    function optionsHtml(options, selectedValue) {
        return (options || []).map(option => {
            const value = String(option?.value ?? '');
            const selected = String(selectedValue ?? '') === value ? ' selected' : '';
            return `<option value="${escapeAttribute(value)}"${selected}>${escapeHtml(option?.label ?? '')}</option>`;
        }).join('');
    }

    function statusSelectFormHtml({
        relationId,
        updateUrl,
        currentValue,
        options = [],
        formClass = '',
        formStyle = 'display: inline;',
        selectClass = '',
        disabled = false,
        disabledTitle = ''
    }) {
        const safeRelationId = escapeAttribute(relationId);
        const formClassAttr = formClass ? ` class="${escapeAttribute(formClass)}"` : '';
        const formStyleAttr = formStyle ? ` style="${escapeAttribute(formStyle)}"` : '';
        const selectClasses = `form-select form-select-sm status-selector ${selectClass}`.trim();
        const disabledAttr = disabled
            ? ` disabled title="${escapeAttribute(disabledTitle)}"`
            : '';

        return `
            <form id="status-form-${safeRelationId}"${formClassAttr}${formStyleAttr}>
                <select class="${escapeAttribute(selectClasses)}"
                        name="new_status"
                        data-relation-id="${safeRelationId}"
                        data-update-url="${safeUrl(updateUrl)}"
                        data-current-value="${escapeAttribute(currentValue)}"
                        ${disabledAttr}>
                    ${optionsHtml(options, currentValue)}
                </select>
            </form>
        `;
    }

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    async function parseStatusError(response) {
        const contentType = response.headers.get('content-type') || '';

        if (contentType.includes('application/json')) {
            const data = await response.json();
            return data.error || data.message || `HTTP ${response.status}`;
        }

        const text = await response.text();
        return text || `HTTP ${response.status}`;
    }

    async function updateStatusSelect(select) {
        if (!select) return false;

        const form = select.closest('form');
        const relationId = select.dataset.relationId;
        const updateUrl = select.dataset.updateUrl;
        const previousValue = select.dataset.currentValue || select.defaultValue || '';
        const newStatus = select.value;

        if (!form || !relationId || !updateUrl) return false;

        select.disabled = true;
        select.setAttribute('aria-busy', 'true');
        form.classList.add('is-loading');

        try {
            const body = new URLSearchParams({
                relation_id: relationId,
                new_status: newStatus
            });

            const response = await fetch(updateUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCookie('csrftoken') || ''
                },
                body: body.toString()
            });

            if (!response.ok) {
                throw new Error(await parseStatusError(response));
            }

            const html = await response.text();
            form.outerHTML = html;
            document.dispatchEvent(new CustomEvent('list:update'));
            return true;
        } catch (error) {
            select.value = previousValue;
            select.dataset.currentValue = previousValue;

            if (window.showNotification) {
                window.showNotification(error.message || 'Failed to update status. Please try again.', 'error');
            } else {
                alert(error.message || 'Failed to update status. Please try again.');
            }

            return false;
        } finally {
            if (select.isConnected) {
                select.disabled = false;
                select.removeAttribute('aria-busy');
                form.classList.remove('is-loading');
            }
        }
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
            const safeId = escapeAttribute(id);

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
                    const safeResolvedUrl = safeUrl(url);
                    const title = escapeAttribute(config.title);
                    const actionName = escapeAttribute(config.action);

                    // Enhanced button with modern UX attributes and hover effects
                    return `<a href="${safeResolvedUrl}"
                              class="btn ${config.class} btn-sm quick-action-btn"
                              title="${title}"
                              data-action="${actionName}"
                              data-entity-id="${safeId}"
                              ${config.action === 'detail' ? 'data-detail-url="' + safeResolvedUrl + '"' : ''}
                              ${config.action === 'edit' ? 'data-edit-url="' + safeResolvedUrl + '"' : ''}
                              ${config.action === 'delete' ? 'data-delete-url="' + safeResolvedUrl + '"' : ''}
                              ${config.action === 'expand' ? 'data-detail-url="' + safeResolvedUrl + '"' : ''}
                              data-bs-toggle="tooltip"
                              data-bs-placement="top">
                        <i class="fas ${config.icon}"></i>
                        <span class="btn-text d-none d-lg-inline ms-1">${escapeHtml(config.title)}</span>
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

            return gridjs.html(linkHtml(urlTemplate.replace('{id}', id), text));
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
                    return url ? linkHtml(url, text) : escapeHtml(text);
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
                    return badgeHtml(text, url, badgeClass);
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

            // Remove sort controls from columns with sort: false
            // Grid.js doesn't properly respect per-column sort: false
            grid.on('ready', () => {
                applyColumnDataAttributes(container, columns);

                const visibleColumns = columns.filter(col => !col.hidden);
                const headerCells = container.querySelectorAll('thead tr th');
                visibleColumns.forEach((col, index) => {
                    if (col.sort === false && headerCells[index]) {
                        const sortBtn = headerCells[index].querySelector('.gridjs-sort');
                        if (sortBtn) sortBtn.remove();
                        headerCells[index].classList.remove('gridjs-th-sort');
                    }
                });
            });

            grid.render(container);

            new MutationObserver(() => applyColumnDataAttributes(container, columns)).observe(
                container,
                {
                    childList: true,
                    subtree: true
                }
            );

            // If the grid has a checkbox column, set up persistent select-all injection
            // Uses MutationObserver to survive Grid.js re-renders (sort, pagination)
            var hasCheckboxColumn = columns.some(function(col) { return col.id === 'checkbox'; });
            if (hasCheckboxColumn) {
                var selectAllRowsLabel = escapeAttribute(
                    window.gridTranslations?.selectAllRows || 'Select all rows'
                );
                var checkboxHtml =
                    '<div class="form-check">' +
                    '<input type="checkbox" class="form-check-input bulk-select-all"' +
                    ' aria-label="' + selectAllRowsLabel + '"' +
                    ' id="bulk-select-all-' + containerId + '">' +
                    '</div>';
                var injectCheckbox = function() {
                    var th = container.querySelector('thead tr th:first-child');
                    if (th && !th.querySelector('.bulk-select-all')) {
                        th.innerHTML = checkboxHtml;
                    }
                };
                // Initial injection after Grid.js renders
                setTimeout(injectCheckbox, 50);
                // Re-inject on every Grid.js re-render via MutationObserver
                new MutationObserver(injectCheckbox).observe(container, {
                    childList: true,
                    subtree: true
                });
            }

            // Hide pagination footer if only one page
            // Apply class to the container (not the footer) so it persists across Grid.js re-renders
            const paginationLimit = config.pagination && config.pagination.limit ? config.pagination.limit : 10;
            if (config.pagination && config.pagination.enabled && data.length <= paginationLimit) {
                document.getElementById(containerId).classList.add('gridjs-hide-footer');
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
            // Try to get the deleted item ID from the modal or delete context
            const deletedItemId = getDeletedItemId();

            if (deletedItemId) {
                // Remove the specific row from grid data (delete operation)
                removeItemFromGrid(grid, deletedItemId, entityType, idColumnIndex, postUpdateCallback);
            } else {
                // Create or update operation - refresh grid data without full page reload
                refreshGridData(grid, entityType, idColumnIndex, postUpdateCallback);
            }
        });

        // Handle browser back/forward cache (bfcache): when a page is restored
        // from bfcache, the DOM is stale and may not reflect recent CRUD changes.
        window.addEventListener('pageshow', function(event) {
            if (event.persisted) {
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

                    // Also extract and update permissions if available
                    const permissionsStr = extractPermissions(html);
                    if (permissionsStr) {
                        try {
                            const extractedPermissions = new Function('return ' + permissionsStr)();

                            // Update global permissions variable IN PLACE
                            // We need to modify the existing object, not replace it,
                            // because the formatter has a closure reference to it
                            if (window.userPermissions !== undefined && typeof window.userPermissions === 'object') {
                                Object.keys(window.userPermissions).forEach(key => delete window.userPermissions[key]);
                                Object.assign(window.userPermissions, extractedPermissions);
                            }
                            // Also update PermissionUtils if it has a setter
                            if (window.PermissionUtils && window.PermissionUtils.updatePermissions) {
                                window.PermissionUtils.updatePermissions(extractedPermissions);
                            }
                        } catch (permError) {
                            console.warn(`[${entityType}List] Could not update permissions:`, permError);
                        }
                    }

                    // Remove empty state before rendering new data (restores table visibility)
                    if (extractedData.length > 0) {
                        removeEmptyStateIfPresent(grid._containerId);
                    }

                    // Update the grid
                    grid.updateConfig({
                        data: extractedData
                    }).forceRender();

                    // Wait for Grid.js to finish rendering using MutationObserver
                    // This detects when DOM mutations have stopped, indicating rendering is complete
                    const gridContainer = document.getElementById(grid._containerId);
                    if (gridContainer) {
                        waitForGridRenderComplete(gridContainer, () => {
                            // Fix Grid.js bug: forceRender with empty data doesn't show noRecordsFound
                            // Use force=true because Grid.js leaves stale rows in DOM after forceRender
                            if (extractedData.length === 0) {
                                injectEmptyStateIfNeeded(grid._containerId, null, true);
                            }
                            document.dispatchEvent(new CustomEvent('grid:refreshed', {
                                detail: { containerId: grid._containerId, entityType: entityType }
                            }));
                            // Update pagination footer after DOM is fully rendered
                            updatePaginationVisibility(grid, extractedData.length);
                        });
                    }

                    // Update global data variable if it exists
                    if (window.data !== undefined) {
                        window.data = extractedData;
                    }

                    // After grid renders, update UI based on permissions
                    // This ensures buttons are enabled/disabled correctly after refresh
                    setTimeout(() => {
                        const containerId = grid._containerId;
                        if (containerId && window.PermissionUtils && window.userPermissions) {
                            window.PermissionUtils.updateUIForPermissions(containerId, window.userPermissions);
                        }
                    }, 50);

                    // Run post-update callback if provided
                    if (postUpdateCallback && typeof postUpdateCallback === 'function') {
                        setTimeout(postUpdateCallback, 100);
                    }

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
            return extractObjectFromPosition(html, objStart);
        }

        // Fallback: try const userPermissions = { (might be used in some templates)
        const altMarker = 'const userPermissions = {';
        const altIndex = html.indexOf(altMarker);
        if (altIndex !== -1) {
            const objStart = altIndex + 'const userPermissions = '.length;
            return extractObjectFromPosition(html, objStart);
        }

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
            return objStr;
        }

        console.warn('[extractPermissions] Could not find matching closing brace');
        return null;
    }

    /**
     * Inject "No data available" empty state into a grid container.
     * Grid.js has a bug where forceRender() with data: [] leaves the tbody empty
     * instead of showing the noRecordsFound message. This function creates a visible
     * div-based empty state (same approach as RealTimeSearch) that works even when
     * Grid.js hides the table element.
     * @param {string} containerId - The grid container element ID
     * @param {string} message - Optional custom message (defaults to grid translation)
     * @param {boolean} force - Skip DOM row check (use when data is known to be empty but Grid.js leaves stale rows)
     */
    function injectEmptyStateIfNeeded(containerId, message, force) {
        const container = document.getElementById(containerId);
        if (!container) return;

        // Check if grid actually has data rows - if so, don't inject
        // Skip this check when force=true (Grid.js forceRender with empty data leaves stale rows)
        if (!force) {
            const tbody = container.querySelector('tbody');
            if (tbody && tbody.querySelectorAll('tr.gridjs-tr').length > 0) {
                // Check if any row has actual data cells (not just the empty message)
                const dataCells = tbody.querySelectorAll('td:not(.gridjs-message)');
                if (dataCells.length > 0) return;
            }
        }

        // Remove any existing empty state div
        const existingEmptyState = container.querySelector('.grid-empty-state');
        if (existingEmptyState) {
            existingEmptyState.remove();
        }

        // Hide the grid table (Grid.js may leave it visible but empty)
        const gridWrapper = container.querySelector('.gridjs-wrapper');
        if (gridWrapper) {
            gridWrapper.style.display = 'none';
        }

        // Hide the footer (pagination) since there's no data
        const gridFooter = container.querySelector('.gridjs-footer');
        if (gridFooter) {
            gridFooter.style.display = 'none';
        }

        // Create visible div-based empty state (same structure as RealTimeSearch)
        const text = message || (window.gridTranslations && window.gridTranslations.noData) || 'No data available';
        const emptyState = document.createElement('div');
        emptyState.className = 'grid-empty-state';
        emptyState.innerHTML =
            '<div class="empty-state-content">' +
                '<i class="fas fa-inbox empty-state-icon"></i>' +
                '<p class="empty-state-message">' + text + '</p>' +
            '</div>';

        // Insert before footer if it exists, otherwise append to container
        if (gridFooter) {
            gridFooter.parentNode.insertBefore(emptyState, gridFooter);
        } else {
            container.appendChild(emptyState);
        }

    }

    /**
     * Remove empty state and restore grid visibility.
     * Called when grid gets data again (e.g., after create operation).
     * @param {string} containerId - The grid container element ID
     */
    function removeEmptyStateIfPresent(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const emptyState = container.querySelector('.grid-empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        // Restore grid table visibility
        const gridWrapper = container.querySelector('.gridjs-wrapper');
        if (gridWrapper) {
            gridWrapper.style.display = '';
        }

        // Restore footer visibility
        const gridFooter = container.querySelector('.gridjs-footer');
        if (gridFooter) {
            gridFooter.style.display = '';
        }
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
            const containerId = grid._containerId;
            const container = containerId ? document.getElementById(containerId) : null;
            if (container) {
                if (dataLength <= paginationLimit) {
                    container.classList.add('gridjs-hide-footer');
                } else {
                    container.classList.remove('gridjs-hide-footer');
                }
            }
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
                        return uuidMatch[1];
                    }
                }
            }
        }

        return null;
    }

    /**
     * Reset all delete button states in the grid to their default enabled state
     */
    function resetDeleteButtonStates() {
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

    }

    /**
     * Remove a specific item from the grid by ID
     */
    function removeItemFromGrid(gridInstance, itemId, entityType, idColumnIndex, postUpdateCallback) {
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
                    // Fix Grid.js bug: forceRender with empty data doesn't show noRecordsFound
                    // Use force=true because Grid.js leaves stale rows in DOM after forceRender
                    if (newData.length === 0) {
                        injectEmptyStateIfNeeded(gridInstance._containerId, null, true);
                    }
                    document.dispatchEvent(new CustomEvent('grid:refreshed', {
                        detail: { containerId: gridInstance._containerId, entityType: entityType }
                    }));
                    // Update pagination footer after DOM is fully rendered
                    updatePaginationVisibility(gridInstance, newData.length);
                });
            }

            // Update global data variable
            if (window.data) {
                window.data = newData;
            }

            // Run post-update callback if provided
            if (postUpdateCallback && typeof postUpdateCallback === 'function') {
                setTimeout(() => {
                    postUpdateCallback();
                }, 150);
            }

            // Reset all delete button states after grid update
            setTimeout(function() {
                resetDeleteButtonStates();
            }, 120);

            // Schedule a deferred empty state check after all event handlers complete.
            // This handles the case where forceRender() + MutationObserver timing
            // prevents the empty state from being injected in the callback.
            if (newData.length === 0) {
                setTimeout(() => {
                    const container = document.getElementById(gridInstance._containerId);
                    if (container && !container.querySelector('.grid-empty-state')) {
                        injectEmptyStateIfNeeded(gridInstance._containerId, null, true);
                    }
                }, 300);
            }
        } else {
            console.warn(`[${entityType}List] Item not found in grid data (likely already removed by a previous list:update event):`, itemId);
            // Don't reload - the item was likely already removed by a previous event.
            // If the grid is now empty, ensure the empty state is shown.
            const currentLen = (gridInstance.config.data || []).length;
            if (currentLen === 0) {
                injectEmptyStateIfNeeded(gridInstance._containerId, null, true);
            }
        }
    }

    // =========================================================================
    // Shared List Template Helpers
    // Reusable functions to reduce code duplication across list templates
    // =========================================================================

    /**
     * Create a checkbox column definition for bulk operations
     * @param {number} entityIdIndex - The column index where the entity ID is stored
     * @returns {Object} Column definition object for Grid.js
     */
    function createCheckboxColumn(entityIdIndex) {
        return {
            id: 'checkbox',
            name: '',
            width: '50px',
            sort: false,
            formatter: (cell, row) => {
                const entityId = row.cells[entityIdIndex].data;
                const safeEntityId = escapeAttribute(entityId);
                const selectRowLabel = escapeAttribute(
                    window.gridTranslations?.selectRow || 'Select row'
                );
                return gridjs.html(`
                    <div class="form-check">
                        <input type="checkbox" class="form-check-input bulk-select-item"
                               value="${safeEntityId}"
                               data-entity-id="${safeEntityId}"
                               aria-label="${selectRowLabel}">
                    </div>
                `);
            }
        };
    }

    /**
     * Inject a select-all checkbox into the first header cell of a grid.
     * @param {string} gridId - The grid container ID
     * @returns {boolean} True if checkbox was added
     */
    function injectSelectAllCheckbox(gridId) {
        const gridContainer = document.getElementById(gridId);
        const firstHeaderCell = gridContainer?.querySelector('thead tr th:first-child');
        if (firstHeaderCell && !firstHeaderCell.querySelector('.bulk-select-all')) {
            const selectAllRowsLabel = escapeAttribute(
                window.gridTranslations?.selectAllRows || 'Select all rows'
            );
            firstHeaderCell.innerHTML =
                '<div class="form-check">' +
                '<input type="checkbox" class="form-check-input bulk-select-all"' +
                ' aria-label="' + selectAllRowsLabel + '"' +
                ' id="bulk-select-all-' + gridId + '">' +
                '</div>';
            return true;
        }
        return false;
    }

    /**
     * Add stable column identifiers to rendered Grid.js cells.
     * @param {Element} container - The grid container
     * @param {Array} columns - Original Grid.js column definitions
     */
    function applyColumnDataAttributes(container, columns) {
        if (!container || !Array.isArray(columns)) return;

        const visibleColumns = columns.filter((column) => !column.hidden);
        const tableRows = container.querySelectorAll('thead tr, tbody tr');

        tableRows.forEach((row) => {
            Array.from(row.children).forEach((cell, index) => {
                const column = visibleColumns[index];
                if (!column || !column.id) return;

                cell.setAttribute('data-column-id', column.id);
            });
        });
    }

    /**
     * Add entity ID data attributes to grid rows
     * @param {string} gridId - The grid container ID
     * @param {string} entityType - The entity type name (e.g., 'person', 'gift')
     * @param {Array} data - The grid data array
     * @param {number} idColumnIndex - The column index where the entity ID is stored
     */
    function addEntityDataAttributes(gridId, entityType, data, idColumnIndex) {
        const gridContainer = document.getElementById(gridId);
        if (!gridContainer) return;

        const rows = gridContainer.querySelectorAll('tbody tr');
        rows.forEach((row, index) => {
            if (data[index] && data[index][idColumnIndex]) {
                const entityId = data[index][idColumnIndex];
                row.setAttribute('data-entity-id', entityId);
                row.setAttribute(`data-${entityType}-id`, entityId);
            }
        });
    }

    /**
     * Apply row classes and data attributes from marker elements rendered inside rows.
     * This keeps metadata attached to the correct row after sorting, filtering, and pagination.
     * @param {string} gridId - The grid container ID
     * @param {Object} options - Marker and class configuration
     */
    function setupRowStateMarkers(gridId, options) {
        const gridContainer = document.getElementById(gridId);
        if (!gridContainer) return;

        const markerSelector = options.markerSelector || '[data-grid-row-state]';
        const rowClass = options.rowClass || 'grid-state-row';
        const attentionClass = options.attentionClass || `${rowClass}--attention`;
        const missingDataClass = options.missingDataClass || `${rowClass}--missing-data`;
        const classPrefix = options.classPrefix || `${rowClass}--`;
        const stateKeys = options.stateKeys || [];
        let applyTimer = null;

        function clearRowState(row) {
            row.classList.remove(rowClass, attentionClass, missingDataClass);
            stateKeys.forEach((stateKey) => {
                row.classList.remove(`${classPrefix}${stateKey}`);
            });
            row.removeAttribute('data-urgency-key');
            row.removeAttribute('data-needs-attention');
            row.removeAttribute('data-attention-label');
            row.removeAttribute('data-has-missing-data');
            row.removeAttribute('data-missing-data-label');
            row.removeAttribute('data-has-missing-due-date');
            row.removeAttribute('data-missing-due-date-label');
            row.removeAttribute('data-has-missing-event');
            row.removeAttribute('data-missing-event-label');
        }

        function applyRowStateMarkers() {
            const rows = gridContainer.querySelectorAll('tbody tr');
            rows.forEach((row) => {
                clearRowState(row);

                const marker = row.querySelector(markerSelector);
                if (!marker) return;

                const urgencyKey = marker.dataset.urgencyKey || marker.dataset.stateKey || 'unknown';
                const needsAttention = marker.dataset.needsAttention === 'true';
                const attentionLabel = marker.dataset.attentionLabel || '';
                const hasMissingData = marker.dataset.hasMissingData === 'true';
                const missingDataLabel = marker.dataset.missingDataLabel || '';
                const hasMissingDueDate = marker.dataset.hasMissingDueDate === 'true';
                const missingDueDateLabel = marker.dataset.missingDueDateLabel || '';
                const hasMissingEvent = marker.dataset.hasMissingEvent === 'true';
                const missingEventLabel = marker.dataset.missingEventLabel || '';

                row.classList.add(rowClass, `${classPrefix}${urgencyKey}`);
                if (needsAttention) {
                    row.classList.add(attentionClass);
                }
                if (hasMissingData) {
                    row.classList.add(missingDataClass);
                }
                row.setAttribute('data-urgency-key', urgencyKey);
                row.setAttribute('data-needs-attention', needsAttention ? 'true' : 'false');
                if (attentionLabel) {
                    row.setAttribute('data-attention-label', attentionLabel);
                }
                row.setAttribute('data-has-missing-data', hasMissingData ? 'true' : 'false');
                if (missingDataLabel) {
                    row.setAttribute('data-missing-data-label', missingDataLabel);
                }
                row.setAttribute('data-has-missing-due-date', hasMissingDueDate ? 'true' : 'false');
                if (missingDueDateLabel) {
                    row.setAttribute('data-missing-due-date-label', missingDueDateLabel);
                }
                row.setAttribute('data-has-missing-event', hasMissingEvent ? 'true' : 'false');
                if (missingEventLabel) {
                    row.setAttribute('data-missing-event-label', missingEventLabel);
                }
            });
        }

        function scheduleApply() {
            if (applyTimer) clearTimeout(applyTimer);
            applyTimer = setTimeout(applyRowStateMarkers, 0);
        }

        scheduleApply();

        new MutationObserver(scheduleApply).observe(gridContainer, {
            childList: true,
            subtree: true
        });

        document.addEventListener('grid:refreshed', (event) => {
            if (event.detail?.containerId === gridId) {
                scheduleApply();
            }
        });
    }

    /**
     * Setup a grid:refreshed event listener that re-injects select-all checkbox,
     * re-adds entity data attributes, and re-binds bulk operations if active
     * @param {string} gridId - The grid container ID
     * @param {string} entityType - The entity type name (capitalized, e.g., 'Event')
     * @param {Array} data - The grid data array
     * @param {number} idColumnIndex - The column index where the entity ID is stored
     */
    function setupGridRefreshHandler(gridId, entityType, data, idColumnIndex) {
        document.addEventListener('grid:refreshed', (event) => {
            if (event.detail?.containerId !== gridId) return;

            injectSelectAllCheckbox(gridId);

            addEntityDataAttributes(gridId, entityType.toLowerCase(), data, idColumnIndex);

            if (window.BulkOperations && window.BulkOperations.state?.selectionModeActive) {
                window.BulkOperations.bindCheckboxEvents();
            }
        });
    }

    /**
     * Setup inline editing with a fallback timeout in case the grid ready event doesn't fire
     * @param {string} gridId - The grid container ID
     * @param {string} entityType - The entity type name (e.g., 'event')
     * @param {Object} columnMapping - Mapping of column indices to field names
     * @param {Object} state - State object with inlineEditingInitialized flag
     * @param {Function} [addDataAttributesFn] - Optional function to add entity data attributes
     */
    function setupInlineEditingFallback(gridId, entityType, columnMapping, state, addDataAttributesFn) {
        setTimeout(() => {
            if (!state.inlineEditingInitialized) {
                const gridContainer = document.getElementById(gridId);
                const editableCells = gridContainer ? gridContainer.querySelectorAll('.inline-editable') : [];

                if (editableCells.length === 0) {
                    if (addDataAttributesFn) addDataAttributesFn();

                    if (window.InlineEditing) {
                        try {
                            window.InlineEditing.init(gridId, entityType, columnMapping);
                            state.inlineEditingInitialized = true;
                        } catch (error) {
                            console.error(`[${entityType}List] Error in fallback inline editing:`, error);
                        }
                    }
                }
            }
        }, 1000);
    }

    /**
     * Initialize bulk operations for a grid if available
     * @param {string} gridId - The grid container ID
     * @param {string} entityType - The entity type name (e.g., 'event')
     * @param {Object} [options] - Bulk operations options overrides
     */
    function initBulkOperations(gridId, entityType, options) {
        if (window.BulkOperations) {
            BulkOperations.init(gridId, entityType, Object.assign({
                enableSelectAll: true,
                enableBulkDelete: true,
                enableBulkShare: true
            }, options || {}));
        }
    }

    /**
     * Run a callback once the advanced list controls are explicitly opened.
     * @param {string} gridId - The grid container ID
     * @param {boolean|Object} advancedControls - Advanced controls config
     * @param {Function} callback - Work to run after the controls are opened
     * @returns {Function} Function that can be called to activate immediately
     */
    function setupAdvancedControls(gridId, advancedControls, callback) {
        if (!advancedControls) {
            callback();
            return callback;
        }

        var options = typeof advancedControls === 'object' ? advancedControls : {};
        var controlsId = options.controlsId || (gridId + '-advanced-tools');
        var controls = document.getElementById(controlsId);
        var initialized = false;

        function activate() {
            if (initialized) return;
            initialized = true;

            if (controls) {
                controls.classList.add('advanced-list-tools--active');
            }

            callback();

            document.dispatchEvent(new CustomEvent('advanced:list-controls-ready', {
                detail: { containerId: gridId }
            }));
        }

        if (!controls) {
            console.warn('[GridUtils] Advanced controls not found for grid:', gridId);
            activate();
            return activate;
        }

        if (controls.tagName && controls.tagName.toLowerCase() === 'details') {
            if (controls.open) {
                activate();
            } else {
                controls.addEventListener('toggle', function () {
                    if (controls.open) {
                        activate();
                    }
                });
            }
        } else {
            controls.addEventListener('click', activate);
        }

        return activate;
    }

    /**
     * Calculate the optimal number of rows per page based on available viewport height.
     * Measures the space between the grid container's top and the viewport bottom,
     * then divides by estimated row height.
     *
     * @param {string} containerId - The grid container element ID
     * @param {Object} [options] - Configuration options
     * @param {number} [options.minRows=5] - Minimum rows per page
     * @param {number} [options.maxRows=50] - Maximum rows per page
     * @param {number} [options.rowHeight=65] - Estimated height per row in pixels
     * @param {number} [options.headerHeight=57] - Grid header (thead) height
     * @param {number} [options.footerHeight=125] - Grid footer (pagination) height
     * @param {number} [options.buffer=20] - Extra buffer (scrollbar, borders)
     * @returns {number} Optimal page size
     */
    function calculateOptimalPageSize(containerId, options) {
        var opts = Object.assign({
            minRows: 5,
            maxRows: 50,
            rowHeight: 65,
            headerHeight: 57,
            footerHeight: 125,
            buffer: 20
        }, options || {});

        var container = document.getElementById(containerId);
        if (!container) return 10;

        var containerTop = container.getBoundingClientRect().top;

        // Account for fixed-top navbar if body padding hasn't been applied yet
        // (script may run before DOMContentLoaded when adjustBodyPadding fires)
        var navbar = document.querySelector('.navbar.fixed-top');
        if (navbar) {
            var navbarHeight = navbar.offsetHeight;
            var bodyPadding = parseFloat(window.getComputedStyle(document.body).paddingTop) || 0;
            if (bodyPadding < navbarHeight) {
                containerTop += (navbarHeight - bodyPadding);
            }
        }

        var viewportHeight = window.innerHeight;
        var availableHeight = viewportHeight - containerTop - opts.headerHeight - opts.footerHeight - opts.buffer;

        var optimalRows = Math.floor(availableHeight / opts.rowHeight);
        return Math.max(opts.minRows, Math.min(opts.maxRows, optimalRows));
    }

    /**
     * Enable dynamic page size adjustment on window resize.
     * Recalculates optimal page size and updates the grid with a debounced handler.
     *
     * @param {Object} grid - The Grid.js instance
     * @param {Object} [options] - Options passed to calculateOptimalPageSize
     */
    function enableDynamicPageSize(grid, options) {
        var resizeTimeout = null;
        var containerId = grid._containerId;
        if (!containerId) return;

        window.addEventListener('resize', function () {
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(function () {
                var newLimit = calculateOptimalPageSize(containerId, options);
                var currentLimit = (grid.config.pagination && grid.config.pagination.limit) || 10;

                if (newLimit !== currentLimit) {
                    grid.updateConfig({
                        pagination: { enabled: true, limit: newLimit }
                    }).forceRender();

                    var container = document.getElementById(containerId);
                    if (container) {
                        waitForGridRenderComplete(container, function () {
                            var dataLength = Array.isArray(grid.config.data) ? grid.config.data.length : 0;
                            updatePaginationVisibility(grid, dataLength);
                            document.dispatchEvent(new CustomEvent('grid:refreshed', {
                                detail: { containerId: containerId }
                            }));
                        });
                    }
                }
            }, 250);
        });
    }

    /**
     * Initialize a standard list grid with common features (bulk operations, inline editing, etc.)
     * Reduces code duplication across list templates by centralizing grid configuration.
     *
     * @param {Object} config - Configuration object
     * @param {string} config.gridId - HTML container ID for grid
     * @param {string} config.entityType - Entity type (e.g., 'person', 'gift', 'event')
     * @param {Array} config.columns - Grid.js columns array
     * @param {Array} config.data - Grid.js data array
     * @param {Object} [config.features] - Feature configuration
     * @param {boolean} [config.features.bulkOperations] - Enable bulk select/delete
     * @param {Object} [config.features.inlineEditing] - Inline editing config
     * @param {Object} [config.features.inlineEditing.mapping] - Field index to field name mapping
     * @param {Object} [config.features.expandableRows] - Expandable rows config
     * @param {string} [config.features.expandableRows.urlTemplate] - Detail URL template with {id}
     * @param {boolean} [config.features.realTimeSearch] - Enable real-time search
     * @param {boolean} [config.features.dynamicFilters] - Enable dynamic filters
     * @param {boolean} [config.features.dynamicPageSize] - Enable dynamic page sizing
     * @param {Array} [config.features.initialSort] - Initial sort configuration
     * @param {Object} [config.features.initialSort[].columnSelector] - CSS selector for column header
     * @param {boolean} [config.features.initialSort[].shift] - Whether to apply shift+click (multi-column)
     * @param {Object} [config.pagination] - Pagination config (default: { enabled: true })
     * @param {Object} [config.sort] - Sort config (default: {})
     * @param {Object} [config.userPermissions] - User permissions object to store in window.userPermissions
     * @param {number} [config.idFieldIndex] - Index of entity ID field in data array (auto-detected if not provided)
     * @returns {Object} Initialized Grid.js instance
     */
    function initStandardListGrid(config) {
        var gridId = config.gridId;
        var entityType = config.entityType;
        var columns = config.columns;
        var data = config.data;
        var features = config.features || {};
        var pagination = config.pagination || { enabled: true };
        var sort = config.sort || {};
        var userPermissions = config.userPermissions;
        var idFieldIndex = config.idFieldIndex;
        var advancedControls = features.advancedControls;
        var useAdvancedControls = Boolean(advancedControls);
        var inlineEditing = features.inlineEditing;
        var inlineEntityType = inlineEditing && inlineEditing.entityType
            ? inlineEditing.entityType
            : entityType;
        var bulkOperations = features.bulkOperations;
        var bulkOptions = typeof bulkOperations === 'object' ? bulkOperations : {};
        var bulkEntityType = bulkOptions.entityType || entityType;

        // Store permissions if provided
        if (userPermissions) {
            window.userPermissions = userPermissions;
        }

        // Calculate page size if dynamic sizing enabled
        if (features.dynamicPageSize && !pagination.limit) {
            pagination.limit = calculateOptimalPageSize(gridId);
        }

        // Track initialization state
        var editState = { inlineEditingInitialized: false };
        var listControlsInitialized = false;
        var advancedFeaturesInitialized = false;

        // Auto-detect ID field index if not provided
        if (idFieldIndex === undefined) {
            idFieldIndex = columns.findIndex(function (c) {
                return c.name === (entityType + '_id');
            });
            if (idFieldIndex === -1) {
                // Fallback: assume checkbox column at 0, so ID is first hidden column after data columns
                idFieldIndex = 0;
            }
        }

        function getCurrentGridData() {
            if (grid && grid.config && Array.isArray(grid.config.data)) {
                return grid.config.data;
            }
            return data;
        }

        function addAdvancedDataAttributes() {
            if (bulkOperations || inlineEditing) {
                addEntityDataAttributes(gridId, entityType, getCurrentGridData(), idFieldIndex);
            }
        }

        function initializeInlineEditing() {
            if (inlineEditing && !editState.inlineEditingInitialized && window.InlineEditing) {
                try {
                    window.InlineEditing.init(gridId, inlineEntityType, inlineEditing.mapping);
                    editState.inlineEditingInitialized = true;
                } catch (error) {
                    console.error('[' + entityType + 'List] Error initializing inline editing:', error);
                }
            }
        }

        function initializeListControls() {
            if (listControlsInitialized) return;
            listControlsInitialized = true;

            if (features.filterPanel !== false && window.FilterPanel) {
                FilterPanel.init(gridId, grid, columns);
            }

            if (features.realTimeSearch && window.RealTimeSearch) {
                RealTimeSearch.init(gridId, grid, data);
            }
        }

        function initializeAdvancedFeatures() {
            if (advancedFeaturesInitialized) return;
            advancedFeaturesInitialized = true;

            initializeListControls();
            addAdvancedDataAttributes();

            if (bulkOperations) {
                injectSelectAllCheckbox(gridId);
            }

            initializeInlineEditing();

            if (features.dynamicFilters && window.DynamicFilters) {
                DynamicFilters.init(gridId, grid, data, columns);
            }

            if (bulkOperations) {
                initBulkOperations(gridId, bulkEntityType, bulkOptions);
            }
        }

        // Initialize grid with ready callback
        var grid = initGrid(
            gridId,
            columns,
            data,
            { pagination: pagination, sort: sort },
            function () {
                // Grid ready callback
                addAdvancedDataAttributes();
                initializeInlineEditing();

                if (!useAdvancedControls) {
                    if (bulkOperations) {
                        injectSelectAllCheckbox(gridId);
                    }
                }
            },
            undefined
        );

        // Add list update listener
        var capitalizedEntity = entityType.charAt(0).toUpperCase() + entityType.slice(1);
        addListUpdateListener(
            grid,
            capitalizedEntity,
            idFieldIndex,
            function () {
                if (inlineEditing || !useAdvancedControls || advancedFeaturesInitialized) {
                    addAdvancedDataAttributes();
                }
            }
        );

        // Setup grid refresh handler
        setupGridRefreshHandler(gridId, capitalizedEntity, data, idFieldIndex);

        if (inlineEditing) {
            setTimeout(function () {
                addAdvancedDataAttributes();
                initializeInlineEditing();
            }, 0);
        }

        // Setup inline editing fallback
        if (inlineEditing) {
            setupInlineEditingFallback(gridId, inlineEntityType, inlineEditing.mapping, editState, function () {
                addAdvancedDataAttributes();
            });
        }

        initializeListControls();

        if (useAdvancedControls) {
            setupAdvancedControls(gridId, advancedControls, initializeAdvancedFeatures);
        } else {
            initializeAdvancedFeatures();
        }

        if (features.rowStateMarkers) {
            setupRowStateMarkers(gridId, features.rowStateMarkers);
        }

        // Enable dynamic page sizing
        if (features.dynamicPageSize) {
            enableDynamicPageSize(grid);
        }

        // Enable expandable rows
        if (features.expandableRows) {
            enableExpandableRows(gridId, grid, features.expandableRows);
        }

        // Apply initial sort (only when there is data - sorting empty grid triggers forceRender bug)
        if (features.initialSort && features.initialSort.length > 0 && data.length > 0) {
            setTimeout(function () {
                features.initialSort.forEach(function (sortConfig, index) {
                    var header = document.querySelector('#' + gridId + ' ' + sortConfig.columnSelector);
                    if (header) {
                        if (index === 0) {
                            header.click();
                        } else {
                            var shiftClick = new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                shiftKey: true
                            });
                            header.dispatchEvent(shiftClick);
                        }
                    }
                });
            }, 100);
        }

        // Deferred empty state check: after all initialization (sort clicks, observers, etc.)
        // verify the grid is showing proper empty state if data is empty.
        // This catches the Grid.js bug where forceRender() (triggered by sort clicks or
        // MutationObserver cascades) leaves tbody empty instead of showing noRecordsFound.
        if (data.length === 0) {
            setTimeout(function () {
                var container = document.getElementById(gridId);
                if (container && !container.querySelector('.grid-empty-state')) {
                    // Check if Grid.js native empty message is visible
                    var nativeMsg = container.querySelector('.gridjs-notfound');
                    if (!nativeMsg) {
                        injectEmptyStateIfNeeded(gridId);
                    }
                }
            }, 200);
        }

        return grid;
    }

    // Expose utilities to global scope
    window.GridUtils = {
        initGrid: initGrid,
        initStandardListGrid: initStandardListGrid,
        actionButtonsFormatter: actionButtonsFormatter,
        linkFormatter: linkFormatter,
        multiLinkFormatter: multiLinkFormatter,
        badgeFormatter: badgeFormatter,
        escapeHtml: escapeHtml,
        escapeAttribute: escapeAttribute,
        sanitizeUrl: sanitizeUrl,
        safeUrl: safeUrl,
        linkHtml: linkHtml,
        badgeHtml: badgeHtml,
        optionsHtml: optionsHtml,
        statusSelectFormHtml: statusSelectFormHtml,
        updateStatusSelect: updateStatusSelect,
        setupFilterDropdown: setupFilterDropdown,
        setupCustomColumnFilter: setupCustomColumnFilter,
        enableExpandableRows: enableExpandableRows,
        getGridTranslations: getGridTranslations,
        sortByProperty: sortByProperty,
        sortString: sortString,
        sortDateObject: sortDateObject,
        dateObjectFormatter: dateObjectFormatter,
        addListUpdateListener: addListUpdateListener,
        resetDeleteButtonStates: resetDeleteButtonStates,
        createCheckboxColumn: createCheckboxColumn,
        injectSelectAllCheckbox: injectSelectAllCheckbox,
        addEntityDataAttributes: addEntityDataAttributes,
        setupRowStateMarkers: setupRowStateMarkers,
        setupGridRefreshHandler: setupGridRefreshHandler,
        setupInlineEditingFallback: setupInlineEditingFallback,
        initBulkOperations: initBulkOperations,
        setupAdvancedControls: setupAdvancedControls,
        calculateOptimalPageSize: calculateOptimalPageSize,
        enableDynamicPageSize: enableDynamicPageSize,
        injectEmptyStateIfNeeded: injectEmptyStateIfNeeded,
        removeEmptyStateIfPresent: removeEmptyStateIfPresent
    };

})(window);
