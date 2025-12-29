/**
 * Filter Panel Component
 * Provides collapsible filter and sort functionality for Grid.js tables
 */

(function() {
    'use strict';

    /**
     * Initialize filter panel for a grid
     * @param {string} gridId - The ID of the grid container (without the # prefix)
     * @param {object} grid - The Grid.js instance
     * @param {Array} columns - The columns configuration array
     */
    function initFilterPanel(gridId, grid, columns) {
        const filterToggle = document.getElementById(gridId + '-filter-toggle');
        const filterContent = document.getElementById(gridId + '-filter-content');
        const filterPanel = document.getElementById(gridId + '-filter-panel');
        const searchInput = document.getElementById(gridId + '-search');
        const sortOptionsContainer = document.getElementById(gridId + '-sort-options');
        const mobileBreakpoint = 768;

        if (!filterToggle || !filterContent) {
            console.warn('Filter panel elements not found for grid:', gridId);
            return;
        }

        // Detect when filter panel becomes sticky
        if (filterPanel) {
            initStickyDetection(filterPanel);
        }

        // Check if we're on mobile
        function isMobile() {
            return window.innerWidth <= mobileBreakpoint;
        }

        // On mobile: collapsed by default. On desktop: CSS handles visibility
        function setDefaultState() {
            if (isMobile()) {
                // Mobile: collapsed by default
                filterContent.classList.remove('expanded');
                filterToggle.classList.remove('active');
            } else {
                // Desktop: CSS shows content, no need for expanded class
                filterContent.classList.remove('expanded');
                filterToggle.classList.remove('active');
            }
        }

        // Set initial state
        setDefaultState();

        // Update on resize
        let resizeTimeout;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(setDefaultState, 250);
        });

        // Toggle filter panel
        filterToggle.addEventListener('click', function() {
            const isExpanded = filterContent.classList.toggle('expanded');
            filterToggle.classList.toggle('active', isExpanded);
        });

        // Store original data for filtering
        const originalData = grid.config.data;

        /**
         * Extract searchable text from a cell value (handles complex objects)
         */
        function extractSearchableText(cell) {
            if (cell === null || cell === undefined) return '';

            // Handle objects with common properties
            if (typeof cell === 'object') {
                // Try common text properties
                if (cell.name) return String(cell.name);
                if (cell.text) return String(cell.text);
                if (cell.label) return String(cell.label);

                // For arrays, extract text from each item
                if (Array.isArray(cell)) {
                    return cell.map(extractSearchableText).join(' ');
                }

                // For other objects, try to stringify
                return JSON.stringify(cell);
            }

            return String(cell);
        }

        /**
         * Filter data based on search term
         */
        function filterData(data, searchTerm) {
            if (!searchTerm || searchTerm.trim() === '') {
                return data;
            }

            const term = searchTerm.toLowerCase().trim();

            return data.filter(function(row) {
                // Search through all cells in the row
                return row.some(function(cell) {
                    const cellText = extractSearchableText(cell).toLowerCase();
                    return cellText.includes(term);
                });
            });
        }

        /**
         * Show/hide empty state message based on data
         */
        function updateEmptyState(hasData, searchValue) {
            const gridContainer = document.getElementById(gridId);
            if (!gridContainer) return;

            // Remove existing empty state
            let emptyState = gridContainer.querySelector('.grid-empty-state');
            if (emptyState) {
                emptyState.remove();
            }

            // Find Grid.js elements
            const gridWrapper = gridContainer.querySelector('.gridjs-wrapper');
            const gridTable = gridContainer.querySelector('.gridjs-table');

            // Show/hide grid table based on data
            if (gridTable) {
                gridTable.style.display = hasData ? '' : 'none';
            }

            // Show empty state if no data
            if (!hasData) {
                emptyState = document.createElement('div');
                emptyState.className = 'grid-empty-state';

                let message, icon;
                if (searchValue && searchValue.trim() !== '') {
                    // No search results
                    icon = 'fa-search';
                    message = window.gridTranslations?.noRecordsFound || 'No matching records found';
                } else {
                    // No data at all
                    icon = 'fa-inbox';
                    message = window.gridTranslations?.noData || 'No data available';
                }

                emptyState.innerHTML = `
                    <div class="empty-state-content">
                        <i class="fas ${icon} empty-state-icon"></i>
                        <p class="empty-state-message">${message}</p>
                    </div>
                `;

                // Insert before footer if it exists, otherwise just append
                const gridFooter = gridContainer.querySelector('.gridjs-footer');
                if (gridFooter) {
                    gridFooter.parentNode.insertBefore(emptyState, gridFooter);
                } else {
                    gridContainer.appendChild(emptyState);
                }
            }
        }

        // Connect custom search to Grid.js
        if (searchInput && grid) {
            let searchTimeout;
            searchInput.addEventListener('input', function(e) {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(function() {
                    const searchValue = e.target.value;
                    const filteredData = filterData(originalData, searchValue);

                    // Update grid with filtered data
                    grid.updateConfig({
                        data: filteredData
                    }).forceRender();

                    // Update empty state
                    updateEmptyState(filteredData.length > 0, searchValue);
                }, 300);
            });
        }

        // Show initial empty state if needed (wait for Grid.js to render)
        setTimeout(function() {
            updateEmptyState(originalData.length > 0, '');
        }, 200);

        /**
         * Update sort button states to reflect Grid.js sort state
         * Shows priority numbers for multi-column sorting
         */
        function updateSortButtonStates(container, headers) {
            // Reset all button states first
            container.querySelectorAll('.sort-option').forEach(function(b) {
                b.classList.remove('active');
                b.querySelector('.sort-direction').innerHTML = '<i class="fas fa-sort"></i>';
            });

            // Collect all sorted columns with their order
            const sortedColumns = [];
            headers.forEach(function(header, idx) {
                const sortIndicator = header.querySelector('.gridjs-sort');
                if (sortIndicator) {
                    const isAsc = sortIndicator.classList.contains('gridjs-sort-asc');
                    const isDesc = sortIndicator.classList.contains('gridjs-sort-desc');

                    if (isAsc || isDesc) {
                        // Get sort order from data attribute if available, otherwise use index
                        const order = header.dataset.sortOrder || sortedColumns.length;
                        sortedColumns.push({
                            idx: idx,
                            isAsc: isAsc,
                            order: parseInt(order, 10)
                        });
                    }
                }
            });

            // Sort by order to get correct priority
            sortedColumns.sort(function(a, b) {
                return a.order - b.order;
            });

            // Update buttons with sort state and priority numbers
            sortedColumns.forEach(function(col, priority) {
                const matchingBtn = container.querySelector('.sort-option[data-column-index="' + col.idx + '"]');
                if (matchingBtn) {
                    matchingBtn.classList.add('active');

                    // Show priority number only if multiple columns are sorted
                    const priorityIndicator = sortedColumns.length > 1
                        ? '<span class="sort-priority">' + (priority + 1) + '</span>'
                        : '';

                    matchingBtn.querySelector('.sort-direction').innerHTML = priorityIndicator +
                        (col.isAsc
                            ? '<i class="fas fa-sort-up"></i>'
                            : '<i class="fas fa-sort-down"></i>');
                }
            });
        }

        // Multi-sort mode toggle
        const multiSortToggle = document.getElementById(gridId + '-multi-sort-toggle');
        let multiSortMode = false;

        if (multiSortToggle) {
            multiSortToggle.addEventListener('click', function() {
                multiSortMode = !multiSortMode;
                multiSortToggle.classList.toggle('active', multiSortMode);
            });
        }

        // Generate sort buttons from columns
        if (sortOptionsContainer && columns) {
            // Get translations
            const actionsText = (window.gridTranslations && window.gridTranslations.actions) || 'Actions';

            // Filter sortable columns (exclude Actions column and hidden columns)
            const sortableColumns = columns.filter(function(col, index) {
                // Skip hidden columns
                if (col.hidden) return false;

                // Skip non-sortable columns
                if (col.sort === false) return false;

                const name = typeof col === 'object' ? (col.name || col.id || '') : col;

                // Skip Actions column
                if (name.toLowerCase() === 'actions' || name.toLowerCase() === actionsText.toLowerCase()) {
                    return false;
                }

                return name && name.length > 0;
            });

            // Keep track of original column indices for sorting
            let originalIndex = 0;
            const columnIndices = [];
            columns.forEach(function(col, idx) {
                if (!col.hidden) {
                    columnIndices.push(idx);
                }
            });

            sortableColumns.forEach(function(col, btnIndex) {
                const colName = typeof col === 'object' ? (col.name || col.id) : col;

                // Find the visible column index (for clicking header)
                let visibleIndex = 0;
                for (let i = 0; i < columns.length; i++) {
                    if (columns[i] === col) break;
                    if (!columns[i].hidden) visibleIndex++;
                }

                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'sort-option';
                btn.dataset.columnIndex = visibleIndex;
                btn.title = colName + ' (Shift+click or enable Multi mode to add as secondary sort)';
                btn.innerHTML = '<span>' + colName + '</span>' +
                    '<span class="sort-direction"><i class="fas fa-sort"></i></span>';

                btn.addEventListener('click', function(event) {
                    // Get all Grid.js headers
                    const allHeaders = document.querySelectorAll('#' + gridId + ' .gridjs-th');

                    if (allHeaders[visibleIndex]) {
                        // Use multi-sort if Shift is held OR multi-sort mode is active
                        const useMultiSort = event.shiftKey || multiSortMode;

                        // Create a click event with the appropriate Shift key state
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            shiftKey: useMultiSort
                        });
                        allHeaders[visibleIndex].dispatchEvent(clickEvent);

                        // After Grid.js updates, sync our button states with actual Grid.js state
                        setTimeout(function() {
                            updateSortButtonStates(sortOptionsContainer, allHeaders);
                        }, 100);
                    }
                });

                sortOptionsContainer.appendChild(btn);
            });

            // Sync with initial sort state after Grid.js renders
            // Use 300ms to ensure this runs after the initial sort click (which happens at 100ms)
            setTimeout(function() {
                const allHeaders = document.querySelectorAll('#' + gridId + ' .gridjs-th');
                if (allHeaders.length > 0) {
                    updateSortButtonStates(sortOptionsContainer, allHeaders);
                }
            }, 300);
        }

        // View toggle functionality
        initViewToggle(gridId);
    }

    // View toggle configuration
    var mobileBreakpoint = 768;

    /**
     * Check if we're on mobile
     */
    function isMobile() {
        return window.innerWidth <= mobileBreakpoint;
    }

    /**
     * Get default view based on screen size and user preferences
     * Uses user's profile preferences if available, otherwise defaults to
     * card view on mobile and list view on desktop
     */
    function getDefaultView() {
        var prefs = window.userViewPreferences;
        if (prefs) {
            return isMobile() ? prefs.mobile : prefs.desktop;
        }
        // Fallback if preferences not set
        return isMobile() ? 'card' : 'list';
    }

    /**
     * Initialize view toggle (list/card) for a grid
     * @param {string} gridId - The ID of the grid container
     */
    function initViewToggle(gridId) {
        const viewOptionsContainer = document.getElementById(gridId + '-view-options');
        const gridContainer = document.getElementById(gridId);

        if (!viewOptionsContainer || !gridContainer) {
            return;
        }

        // Get saved preference or use screen-size-based default
        const savedView = localStorage.getItem('view-preference-' + gridId);
        const initialView = savedView || getDefaultView();

        // Apply initial view
        setGridView(gridId, initialView);

        // Update button states
        updateViewButtons(viewOptionsContainer, initialView);

        // Handle view toggle button clicks
        viewOptionsContainer.querySelectorAll('.view-option').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const view = btn.dataset.view;

                // Apply view
                setGridView(gridId, view);

                // Update button states
                updateViewButtons(viewOptionsContainer, view);

                // Save preference
                localStorage.setItem('view-preference-' + gridId, view);
            });
        });

        // Update view on resize if no saved preference
        var resizeTimeout;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(function() {
                // Only apply default if user hasn't set a preference
                if (!localStorage.getItem('view-preference-' + gridId)) {
                    const newView = getDefaultView();
                    setGridView(gridId, newView);
                    updateViewButtons(viewOptionsContainer, newView);
                }
            }, 250);
        });
    }

    /**
     * Set the grid view mode
     * @param {string} gridId - The ID of the grid container
     * @param {string} view - 'list' or 'card'
     */
    function setGridView(gridId, view) {
        const gridContainer = document.getElementById(gridId);
        if (!gridContainer) return;

        // Remove existing view classes
        gridContainer.classList.remove('grid-view-list', 'grid-view-card');

        // Add new view class
        gridContainer.classList.add('grid-view-' + view);

        // Set data attribute for CSS targeting
        gridContainer.setAttribute('data-view', view);

        // For card view, add data-label attributes to cells
        if (view === 'card') {
            addCardLabels(gridContainer);
            // Also set up observer to add labels when Grid.js re-renders
            observeGridChanges(gridContainer);
        }
    }

    /**
     * Observe grid changes and add card labels when content changes
     * @param {Element} container - The grid container
     */
    function observeGridChanges(container) {
        // Don't add multiple observers
        if (container._cardLabelObserver) {
            return;
        }

        const observer = new MutationObserver(function(mutations) {
            // Check if we're still in card view
            if (container.getAttribute('data-view') !== 'card') {
                return;
            }

            // Check if any relevant changes occurred
            let shouldUpdate = false;
            for (const mutation of mutations) {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    shouldUpdate = true;
                    break;
                }
            }

            if (shouldUpdate) {
                addCardLabelsImmediate(container);
            }
        });

        observer.observe(container, {
            childList: true,
            subtree: true
        });

        container._cardLabelObserver = observer;
    }

    /**
     * Add data-label attributes to table cells for card view (immediate, no retry)
     * @param {Element} container - The grid container
     */
    function addCardLabelsImmediate(container) {
        const table = container.querySelector('.gridjs-table');
        if (!table) return;

        // Get headers
        const headers = Array.from(table.querySelectorAll('th')).map(function(th) {
            return th.textContent.trim();
        });

        // Add data-label attributes to cells
        const rows = table.querySelectorAll('tbody tr');
        rows.forEach(function(row) {
            const cells = row.querySelectorAll('td');
            cells.forEach(function(cell, index) {
                if (headers[index] && !cell.hasAttribute('data-label')) {
                    cell.setAttribute('data-label', headers[index]);
                }
            });
        });
    }

    /**
     * Add data-label attributes to table cells for card view
     * @param {Element} container - The grid container
     */
    function addCardLabels(container) {
        const table = container.querySelector('.gridjs-table');
        if (!table) {
            // Table might not be rendered yet, use MutationObserver for efficiency
            const tempObserver = new MutationObserver(function(mutations, obs) {
                const table = container.querySelector('.gridjs-table');
                if (table) {
                    obs.disconnect();
                    addCardLabelsImmediate(container);
                }
            });

            tempObserver.observe(container, {
                childList: true,
                subtree: true
            });

            // Fallback timeout in case observer doesn't fire
            setTimeout(function() {
                tempObserver.disconnect();
                addCardLabelsImmediate(container);
            }, 2000);

            return;
        }

        addCardLabelsImmediate(container);
    }

    /**
     * Update view toggle button states
     * @param {Element} container - The view options container
     * @param {string} activeView - The currently active view
     */
    function updateViewButtons(container, activeView) {
        container.querySelectorAll('.view-option').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.view === activeView);
        });
    }

    /**
     * Detect when filter panel becomes sticky and add visual indicator
     * @param {Element} panel - The filter panel element
     */
    function initStickyDetection(panel) {
        // Create a sentinel element to detect when sticky kicks in
        const sentinel = document.createElement('div');
        sentinel.className = 'sticky-sentinel';
        sentinel.style.cssText = 'position: absolute; top: 0; left: 0; right: 0; height: 1px; pointer-events: none;';
        panel.parentNode.insertBefore(sentinel, panel);

        // Use IntersectionObserver to detect when sentinel leaves viewport
        const observer = new IntersectionObserver(
            function(entries) {
                entries.forEach(function(entry) {
                    // When sentinel is not intersecting, panel is sticky
                    panel.classList.toggle('is-sticky', !entry.isIntersecting);
                });
            },
            {
                threshold: [0],
                rootMargin: '-' + (parseInt(getComputedStyle(document.documentElement).getPropertyValue('--navbar-height')) || 60) + 'px 0px 0px 0px'
            }
        );

        observer.observe(sentinel);
    }

    // Expose to global scope
    window.FilterPanel = {
        init: initFilterPanel,
        setView: setGridView
    };
})();
