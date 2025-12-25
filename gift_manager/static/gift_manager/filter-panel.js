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
        const searchInput = document.getElementById(gridId + '-search');
        const sortOptionsContainer = document.getElementById(gridId + '-sort-options');
        const mobileBreakpoint = 768;

        if (!filterToggle || !filterContent) {
            console.warn('Filter panel elements not found for grid:', gridId);
            return;
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

        // Connect custom search to Grid.js
        if (searchInput && grid) {
            let searchTimeout;
            searchInput.addEventListener('input', function(e) {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(function() {
                    const searchValue = e.target.value;
                    grid.updateConfig({
                        search: {
                            enabled: true,
                            keyword: searchValue
                        }
                    }).forceRender();
                }, 300);
            });
        }

        // Generate sort buttons from columns
        if (sortOptionsContainer && columns) {
            // Track current sort state
            let currentSort = { column: null, direction: 1 }; // 1 = asc, -1 = desc

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
                btn.innerHTML = '<span>' + colName + '</span>' +
                    '<span class="sort-direction"><i class="fas fa-sort"></i></span>';

                btn.addEventListener('click', function() {
                    // Toggle sort direction if same column, otherwise reset
                    if (currentSort.column === visibleIndex) {
                        currentSort.direction = currentSort.direction === 1 ? -1 : 1;
                    } else {
                        currentSort.column = visibleIndex;
                        currentSort.direction = 1;
                    }

                    // Update button states
                    sortOptionsContainer.querySelectorAll('.sort-option').forEach(function(b) {
                        b.classList.remove('active');
                        b.querySelector('.sort-direction').innerHTML = '<i class="fas fa-sort"></i>';
                    });

                    btn.classList.add('active');
                    btn.querySelector('.sort-direction').innerHTML = currentSort.direction === 1
                        ? '<i class="fas fa-sort-up"></i>'
                        : '<i class="fas fa-sort-down"></i>';

                    // Trigger click on the Grid.js header to sort
                    const headers = document.querySelectorAll('#' + gridId + ' .gridjs-th[data-column-id]');
                    const allHeaders = document.querySelectorAll('#' + gridId + ' .gridjs-th');

                    if (allHeaders[visibleIndex]) {
                        // Reset other sorts first by clicking twice if needed
                        allHeaders[visibleIndex].click();

                        // If we need descending, click again
                        if (currentSort.direction === -1) {
                            setTimeout(function() {
                                allHeaders[visibleIndex].click();
                            }, 50);
                        }
                    }
                });

                sortOptionsContainer.appendChild(btn);
            });
        }

        // Hide the original Grid.js search since we have our own
        setTimeout(function() {
            const gridHead = document.querySelector('#' + gridId + ' .gridjs-head');
            if (gridHead) {
                gridHead.style.display = 'none';
            }
        }, 100);
    }

    // Expose to global scope
    window.FilterPanel = {
        init: initFilterPanel
    };
})();
