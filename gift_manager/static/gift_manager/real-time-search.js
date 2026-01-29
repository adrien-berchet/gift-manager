/**
 * Real-time search functionality with HTMX integration
 * Provides debounced search with loading states and error handling
 */

(function() {
    'use strict';

    // Configuration
    const DEBOUNCE_DELAY = 300; // milliseconds
    const MIN_SEARCH_LENGTH = 0; // minimum characters to trigger search

    // Search endpoints mapping
    const SEARCH_ENDPOINTS = {
        'person-grid': '/api/search/persons/',
        'gift-grid': '/api/search/gifts/',
        'event-grid': '/api/search/events/',
        'relation-grid': '/api/search/relations/',
        'person_group-grid': '/api/search/person-groups/',
        'gift_tag-grid': '/api/search/gift-tags/'
    };

    /**
     * Initialize real-time search for a grid
     * @param {string} gridId - The ID of the grid container
     * @param {object} grid - The Grid.js instance
     * @param {Array} originalData - The original data array
     */
    function initRealTimeSearch(gridId, grid, originalData) {
        const searchInput = document.getElementById(gridId + '-search');
        const endpoint = SEARCH_ENDPOINTS[gridId];

        if (!searchInput || !endpoint) {
            console.warn('Real-time search: Missing search input or endpoint for grid:', gridId);
            return;
        }

        let searchTimeout;
        let currentRequest;

        // Add loading state management
        const addLoadingState = () => {
            searchInput.classList.add('searching');
            searchInput.setAttribute('data-loading', 'true');

            // Add spinner if not present
            if (!searchInput.parentNode.querySelector('.search-spinner')) {
                const spinner = document.createElement('div');
                spinner.className = 'search-spinner';
                spinner.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                searchInput.parentNode.appendChild(spinner);
            }
        };

        const removeLoadingState = () => {
            searchInput.classList.remove('searching');
            searchInput.removeAttribute('data-loading');

            // Remove spinner
            const spinner = searchInput.parentNode.querySelector('.search-spinner');
            if (spinner) {
                spinner.remove();
            }
        };

        // Add error state management
        const showError = (message) => {
            searchInput.classList.add('search-error');

            // Show error message
            let errorMsg = searchInput.parentNode.querySelector('.search-error-message');
            if (!errorMsg) {
                errorMsg = document.createElement('div');
                errorMsg.className = 'search-error-message';
                searchInput.parentNode.appendChild(errorMsg);
            }
            errorMsg.textContent = message || 'Search failed. Please try again.';

            // Auto-hide error after 3 seconds
            setTimeout(() => {
                clearError();
            }, 3000);
        };

        const clearError = () => {
            searchInput.classList.remove('search-error');
            const errorMsg = searchInput.parentNode.querySelector('.search-error-message');
            if (errorMsg) {
                errorMsg.remove();
            }
        };

        // Perform search request
        const performSearch = async (searchTerm) => {
            // Cancel previous request
            if (currentRequest) {
                currentRequest.abort();
            }

            // Clear previous errors
            clearError();

            try {
                addLoadingState();

                // Create new request
                const controller = new AbortController();
                currentRequest = controller;

                const url = new URL(endpoint, window.location.origin);
                if (searchTerm.trim()) {
                    url.searchParams.set('search', searchTerm.trim());
                }

                const response = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Content-Type': 'application/json',
                    },
                    signal: controller.signal
                });

                if (!response.ok) {
                    throw new Error(`Search failed: ${response.status} ${response.statusText}`);
                }

                const result = await response.json();

                // Update grid with search results
                updateGridWithResults(grid, result.data, searchTerm);

                // Update result count if element exists
                updateResultCount(gridId, result.count, searchTerm);

            } catch (error) {
                if (error.name === 'AbortError') {
                    // Request was cancelled, ignore
                    return;
                }

                console.error('Search error:', error);
                showError(error.message);

                // Fall back to original data on error
                if (searchTerm.trim() === '') {
                    updateGridWithResults(grid, originalData, '');
                }

            } finally {
                removeLoadingState();
                currentRequest = null;
            }
        };

        // Update grid with search results
        const updateGridWithResults = (grid, data, searchTerm) => {
            try {
                // Update grid data
                grid.updateConfig({
                    data: data
                }).forceRender();

                // Show/hide empty state
                updateEmptyState(gridId, data.length > 0, searchTerm);

                // Trigger custom event for other components
                const event = new CustomEvent('search:complete', {
                    detail: {
                        gridId: gridId,
                        searchTerm: searchTerm,
                        resultCount: data.length,
                        data: data
                    }
                });
                document.dispatchEvent(event);

            } catch (error) {
                console.error('Error updating grid with search results:', error);
                showError('Failed to update search results');
            }
        };

        // Update result count display
        const updateResultCount = (gridId, count, searchTerm) => {
            const countElement = document.querySelector(`#${gridId}-result-count`);
            if (countElement) {
                if (searchTerm.trim()) {
                    countElement.textContent = `${count} result${count !== 1 ? 's' : ''} found`;
                    countElement.style.display = 'block';
                } else {
                    countElement.style.display = 'none';
                }
            }
        };

        // Update empty state
        const updateEmptyState = (gridId, hasData, searchTerm) => {
            const gridContainer = document.getElementById(gridId);
            if (!gridContainer) return;

            // Remove existing empty state
            let emptyState = gridContainer.querySelector('.grid-empty-state');
            if (emptyState) {
                emptyState.remove();
            }

            // Find Grid.js elements
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
                if (searchTerm && searchTerm.trim() !== '') {
                    // No search results
                    icon = 'fa-search';
                    message = window.gridTranslations?.noSearchResults ||
                             `No results found for "${searchTerm.trim()}"`;
                } else {
                    // No data at all
                    icon = 'fa-inbox';
                    message = window.gridTranslations?.noData || 'No data available';
                }

                emptyState.innerHTML = `
                    <div class="empty-state-content">
                        <i class="fas ${icon} empty-state-icon"></i>
                        <p class="empty-state-message">${message}</p>
                        ${searchTerm.trim() ? '<button class="btn btn-sm btn-outline-secondary clear-search-btn">Clear search</button>' : ''}
                    </div>
                `;

                // Add clear search functionality
                const clearBtn = emptyState.querySelector('.clear-search-btn');
                if (clearBtn) {
                    clearBtn.addEventListener('click', () => {
                        searchInput.value = '';
                        performSearch('');
                    });
                }

                // Insert before footer if it exists, otherwise just append
                const gridFooter = gridContainer.querySelector('.gridjs-footer');
                if (gridFooter) {
                    gridFooter.parentNode.insertBefore(emptyState, gridFooter);
                } else {
                    gridContainer.appendChild(emptyState);
                }
            }
        };

        // Set up debounced search
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value;

            // Clear previous timeout
            clearTimeout(searchTimeout);

            // Set new timeout for debounced search
            searchTimeout = setTimeout(() => {
                if (searchTerm.length >= MIN_SEARCH_LENGTH) {
                    performSearch(searchTerm);
                } else if (searchTerm.length === 0) {
                    // Clear search - show original data
                    performSearch('');
                }
            }, DEBOUNCE_DELAY);
        });

        // Handle search input focus/blur for better UX
        searchInput.addEventListener('focus', () => {
            searchInput.parentNode.classList.add('search-focused');
        });

        searchInput.addEventListener('blur', () => {
            searchInput.parentNode.classList.remove('search-focused');
        });

        // Handle Escape key to clear search
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                searchInput.value = '';
                performSearch('');
                searchInput.blur();
            }
        });

        // Add result count element if it doesn't exist
        if (!document.querySelector(`#${gridId}-result-count`)) {
            const countElement = document.createElement('div');
            countElement.id = `${gridId}-result-count`;
            countElement.className = 'search-result-count';
            countElement.style.display = 'none';

            // Insert after search input
            const searchSection = searchInput.closest('.search-section');
            if (searchSection) {
                searchSection.appendChild(countElement);
            }
        }

        console.log(`[RealTimeSearch] Initialized for grid: ${gridId}`);
    }

    // Expose to global scope
    window.RealTimeSearch = {
        init: initRealTimeSearch
    };

})();
