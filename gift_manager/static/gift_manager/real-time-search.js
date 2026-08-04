/**
 * Real-time search functionality for Grid.js tables
 * Provides debounced client-side search with loading states
 */

(function () {
    "use strict";

    // Configuration
    const DEBOUNCE_DELAY = 200; // milliseconds

    /**
     * Initialize real-time search for a grid
     * @param {string} gridId - The ID of the grid container
     * @param {object} grid - The Grid.js instance
     * @param {Array} originalData - The original data array
     */
    function initRealTimeSearch(gridId, grid, originalData) {
        const searchInput = document.getElementById(gridId + "-search");

        if (!searchInput) {
            console.warn("[RealTimeSearch] Missing search input for grid:", gridId);
            return;
        }

        let searchTimeout;

        // Determine which column indices contain searchable text
        // (visible columns that are not checkbox/hidden/actions)
        const searchableIndices = [];
        const columns = grid.config.columns;
        if (columns) {
            columns.forEach((col, index) => {
                const columnName = typeof col.name === "string" ? col.name.trim().toLowerCase() : "";
                const isCheckboxColumn = col.id === "checkbox" || columnName === "";
                const isActionsColumn = col.id === "actions" || columnName === "actions";

                // Skip hidden/control columns, but keep visible data columns even when unsortable.
                if (col.hidden || isCheckboxColumn || isActionsColumn) return;
                searchableIndices.push(index);
            });
        }
        if (searchableIndices.length === 0 && originalData.length > 0) {
            originalData[0].forEach((_, index) => {
                searchableIndices.push(index);
            });
        }

        /**
         * Filter originalData rows matching the search term
         * Searches across all visible text columns (case-insensitive)
         */
        const filterData = (searchTerm) => {
            if (!searchTerm.trim()) return originalData;

            const term = searchTerm.trim().toLowerCase();

            return originalData.filter((row) => {
                return searchableIndices.some((colIndex) => {
                    const cellValue = row[colIndex];
                    if (cellValue == null) return false;

                    // Handle arrays of objects (e.g. groups_info, tags_info)
                    if (Array.isArray(cellValue)) {
                        return cellValue.some((item) => {
                            if (typeof item === "object" && item.name) {
                                return item.name.toLowerCase().includes(term);
                            }
                            return String(item).toLowerCase().includes(term);
                        });
                    }

                    return String(cellValue).toLowerCase().includes(term);
                });
            });
        };

        /**
         * Perform client-side search and update the grid
         */
        const performSearch = (searchTerm) => {
            const filtered = filterData(searchTerm);

            try {
                grid.updateConfig({ data: filtered }).forceRender();

                // Handle empty state
                updateEmptyState(gridId, filtered.length > 0, searchTerm);

                // Update result count
                updateResultCount(gridId, filtered.length, searchTerm);

                // Dispatch event for other components
                document.dispatchEvent(
                    new CustomEvent("search:complete", {
                        detail: {
                            gridId: gridId,
                            searchTerm: searchTerm,
                            resultCount: filtered.length,
                            data: filtered,
                        },
                    })
                );
            } catch (error) {
                console.error("[RealTimeSearch] Error updating grid:", error);
            }
        };

        // Update result count display
        const updateResultCount = (gridId, count, searchTerm) => {
            const countElement = document.querySelector(`#${gridId}-result-count`);
            if (countElement) {
                if (searchTerm.trim()) {
                    countElement.textContent = `${count} result${count !== 1 ? "s" : ""} found`;
                    countElement.style.display = "block";
                } else {
                    countElement.style.display = "none";
                }
            }
        };

        // Update empty state display
        const updateEmptyState = (gridId, hasData, searchTerm) => {
            const gridContainer = document.getElementById(gridId);
            if (!gridContainer) return;

            // Remove existing empty state
            const existing = gridContainer.querySelector(".grid-empty-state");
            if (existing) existing.remove();

            // Hide/show the entire grid wrapper (prevents Grid.js built-in
            // "No matching records found" from flashing before our custom message)
            const gridWrapper = gridContainer.querySelector(".gridjs-wrapper");
            if (gridWrapper) {
                gridWrapper.style.display = hasData ? "" : "none";
            }

            // Hide/show footer (pagination)
            const gridFooter = gridContainer.querySelector(".gridjs-footer");
            if (gridFooter) {
                gridFooter.style.display = hasData ? "" : "none";
            }

            if (!hasData) {
                const emptyState = document.createElement("div");
                emptyState.className = "grid-empty-state";

                let message, icon;
                if (searchTerm && searchTerm.trim() !== "") {
                    icon = "fa-search";
                    message =
                        window.gridTranslations?.noSearchResults ||
                        "No results match your current search";
                } else {
                    icon = "fa-inbox";
                    message = window.gridTranslations?.noData || "No data available";
                }

                emptyState.innerHTML = `
                    <div class="empty-state-content">
                        <i class="fas ${icon} empty-state-icon"></i>
                        <p class="empty-state-message">${message}</p>
                    </div>
                `;

                if (gridFooter) {
                    gridFooter.parentNode.insertBefore(emptyState, gridFooter);
                } else {
                    gridContainer.appendChild(emptyState);
                }
            }
        };

        // Set up debounced search
        searchInput.addEventListener("input", (e) => {
            const searchTerm = e.target.value;
            clearTimeout(searchTimeout);

            searchTimeout = setTimeout(() => {
                performSearch(searchTerm);
            }, DEBOUNCE_DELAY);
        });

        // Handle Escape key to clear search
        searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                searchInput.value = "";
                performSearch("");
                searchInput.blur();
            }
        });

        // Add result count element if it doesn't exist
        if (!document.querySelector(`#${gridId}-result-count`)) {
            const countElement = document.createElement("div");
            countElement.id = `${gridId}-result-count`;
            countElement.className = "search-result-count";
            countElement.style.display = "none";

            const searchSection = searchInput.closest(".search-section");
            if (searchSection) {
                searchSection.appendChild(countElement);
            }
        }
    }

    // Expose to global scope
    window.RealTimeSearch = {
        init: initRealTimeSearch,
    };
})();
