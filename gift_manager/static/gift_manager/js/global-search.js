/**
 * Global search modal (Ctrl+K). URL and labels come from window.GiftManager.
 */
(function () {
    const config = window.GiftManager || {};
    const i18n = config.i18n || {};

    // Global Search functionality
    (function() {
        const searchModal = document.getElementById('searchModal');
        const searchInput = document.getElementById('globalSearchInput');
        const searchResults = document.getElementById('searchResults');

        if (!searchModal || !searchInput || !searchResults) return;

        let searchTimeout = null;
        let searchController = null;
        let searchRequestId = 0;
        let selectedIndex = -1;
        const quickLinksHTML = searchResults.innerHTML;
        let resultIdCounter = 0;
        let currentResults = [];

        // Scoped per user so accounts sharing a browser never see each other's recent items.
        // Without a user id nothing is stored.
        const RECENT_STORAGE_KEY = config.userId ? `giftManager.recentSearchItems.${config.userId}` : null;
        try {
            // Remove the unscoped key written by earlier versions
            localStorage.removeItem('giftManager.recentSearchItems');
        } catch (error) {
            // Storage can be unavailable; recent items are optional.
        }
        const MAX_RECENT_ITEMS = 5;
        const typeLabels = {
            gift_plan: i18n.giftPlans,
            gift: i18n.gifts,
            recipient: i18n.recipients,
            event: i18n.events,
            tag: i18n.tags
        };

        function loadRecentItems() {
            if (!RECENT_STORAGE_KEY) return [];
            try {
                const items = JSON.parse(localStorage.getItem(RECENT_STORAGE_KEY) || '[]');
                return Array.isArray(items) ? items.filter((item) => item && item.url && item.title) : [];
            } catch (error) {
                return [];
            }
        }

        function rememberItem(result) {
            if (!RECENT_STORAGE_KEY) return;
            try {
                const entry = {
                    type: result.type,
                    icon: result.icon,
                    title: result.title,
                    subtitle: result.subtitle || '',
                    url: result.url
                };
                const items = loadRecentItems().filter((item) => item.url !== entry.url);
                items.unshift(entry);
                localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(items.slice(0, MAX_RECENT_ITEMS)));
            } catch (error) {
                // Storage can be unavailable (private mode, quota); recent items are optional.
            }
        }

        function renderResultItem(result, index) {
            return `
                <a href="${safeSearchUrl(result.url)}" class="search-result-item" role="option" aria-selected="false" data-result-index="${index}">
                    <div class="search-result-icon"><i class="fas ${safeIconClass(result.icon)}" aria-hidden="true"></i></div>
                    <div class="search-result-content">
                        <div class="search-result-title">${escapeHtml(result.title)}</div>
                        ${result.subtitle ? `<div class="search-result-subtitle">${escapeHtml(result.subtitle)}</div>` : ''}
                    </div>
                </a>
            `;
        }

        function renderEmptyState() {
            const recent = loadRecentItems();
            currentResults = recent;
            if (recent.length === 0) {
                return quickLinksHTML;
            }
            const recentHtml = `<div class="search-category">${escapeHtml(i18n.recentItems)}</div>`
                + recent.map(renderResultItem).join('');
            return recentHtml + quickLinksHTML;
        }

        function renderCreateActions(query) {
            const actions = [
                { url: config.urls.giftCreate, icon: 'fa-gift', label: i18n.createGiftNamed },
                { url: config.urls.personCreate, icon: 'fa-user-plus', label: i18n.createPersonNamed },
                { url: config.urls.eventCreate, icon: 'fa-calendar-plus', label: i18n.createEventNamed }
            ].filter((action) => action.url);

            return actions.map((action) => `
                <a href="${safeSearchUrl(`${action.url}?name=${encodeURIComponent(query)}`)}"
                   class="search-result-item" role="option" aria-selected="false" data-action="create">
                    <div class="search-result-icon"><i class="fas ${safeIconClass(action.icon)}" aria-hidden="true"></i></div>
                    <div class="search-result-content">
                        <div class="search-result-title">${escapeHtml(action.label)} "${escapeHtml(query)}"</div>
                    </div>
                </a>
            `).join('');
        }

        // Keyboard shortcut to open search (Ctrl+K or Cmd+K)
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const modal = new bootstrap.Modal(searchModal);
                modal.show();
            }
        });

        // Focus input when modal opens
        searchModal.addEventListener('show.bs.modal', () => {
            if (!searchInput.value.trim()) {
                setResultsHtml(renderEmptyState());
            }
        });

        searchModal.addEventListener('shown.bs.modal', () => {
            syncResultSemantics();
            searchInput.focus();
            searchInput.select();
        });

        // Clear input and reset results when modal closes
        searchModal.addEventListener('hidden.bs.modal', () => {
            abortSearch();
            searchInput.value = '';
            setResultsHtml(renderEmptyState());
        });

        // Perform search
        async function performSearch(query) {
            const requestId = ++searchRequestId;

            if (!query || query.length < 2) {
                abortSearch();
                setResultsHtml(renderEmptyState());
                return;
            }

            abortSearch();
            searchController = new AbortController();

            try {
                const response = await fetch(`${config.urls.globalSearch}?q=${encodeURIComponent(query)}`, {
                    signal: searchController.signal,
                    headers: {
                        'Accept': 'application/json'
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json();

                if (requestId !== searchRequestId) {
                    return;
                }

                if (data.results.length === 0) {
                    currentResults = [];
                    setResultsHtml(`
                        <div class="search-no-results">
                            <i class="fas fa-search fa-2x mb-3" style="opacity: 0.3;"></i>
                            <p>${escapeHtml(i18n.noResultsFor)} "<strong>${escapeHtml(query)}</strong>"</p>
                        </div>
                        ${renderCreateActions(query)}
                    `);
                    return;
                }

                // Group results by type, keeping a flat list so clicks can be recorded
                currentResults = [];
                const grouped = {};
                data.results.forEach(result => {
                    if (!grouped[result.type]) {
                        grouped[result.type] = [];
                    }
                    grouped[result.type].push(result);
                });

                let html = '';
                for (const [type, results] of Object.entries(grouped)) {
                    html += `<div class="search-category">${escapeHtml(typeLabels[type] || type)}</div>`;
                    results.forEach(result => {
                        html += renderResultItem(result, currentResults.length);
                        currentResults.push(result);
                    });
                }

                setResultsHtml(html);
            } catch (error) {
                if (error.name === 'AbortError') {
                    return;
                }

                if (requestId !== searchRequestId) {
                    return;
                }

                console.error('Search error:', error);
                setResultsHtml(`
                    <div class="search-no-results">
                        <p>${escapeHtml(i18n.searchError)}</p>
                    </div>
                `);
            } finally {
                if (requestId === searchRequestId) {
                    searchController = null;
                }
            }
        }

        function abortSearch() {
            if (searchController) {
                searchController.abort();
                searchController = null;
            }
        }

        function setResultsHtml(html) {
            searchResults.innerHTML = html;
            selectedIndex = -1;
            searchInput.setAttribute('aria-activedescendant', '');
            syncResultSemantics();
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function safeSearchUrl(url) {
            try {
                const parsed = new URL(url, window.location.origin);
                if (parsed.origin !== window.location.origin) {
                    return '#';
                }
                return escapeHtml(parsed.pathname + parsed.search + parsed.hash);
            } catch (error) {
                return '#';
            }
        }

        function safeIconClass(icon) {
            return String(icon || '')
                .split(/\s+/)
                .filter((token) => /^fa[-a-z0-9]*$/.test(token))
                .join(' ');
        }

        // Remember visited results and close the modal when a create action opens its form
        searchResults.addEventListener('click', (e) => {
            const item = e.target.closest('.search-result-item');
            if (!item) return;

            if (item.dataset.resultIndex !== undefined) {
                const result = currentResults[Number(item.dataset.resultIndex)];
                if (result) rememberItem(result);
            }

            if (item.dataset.action === 'create') {
                const modal = bootstrap.Modal.getInstance(searchModal);
                if (modal) modal.hide();
            }
        });

        // Debounced search on input
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            selectedIndex = -1;
            searchInput.setAttribute('aria-activedescendant', '');

            if (searchTimeout) {
                clearTimeout(searchTimeout);
            }

            searchTimeout = setTimeout(() => {
                performSearch(query);
            }, 200);
        });

        // Keyboard navigation in search results
        const getVisibleItems = () => document.querySelectorAll('#searchResults .search-result-item');

        searchInput.addEventListener('keydown', (e) => {
            const items = getVisibleItems();

            if (e.key === 'ArrowDown') {
                if (items.length === 0) return;
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                updateSelection(items);
            } else if (e.key === 'ArrowUp') {
                if (items.length === 0) return;
                e.preventDefault();
                selectedIndex = selectedIndex <= 0 ? items.length - 1 : selectedIndex - 1;
                updateSelection(items);
            } else if (e.key === 'Enter' && selectedIndex >= 0) {
                e.preventDefault();
                items[selectedIndex].click();
            }
        });

        function updateSelection(items) {
            items.forEach((item, index) => {
                const isSelected = index === selectedIndex;
                item.classList.toggle('selected', isSelected);
                item.setAttribute('aria-selected', isSelected ? 'true' : 'false');

                if (!item.id) {
                    item.id = 'global-search-result-' + (++resultIdCounter);
                }

                if (index === selectedIndex) {
                    searchInput.setAttribute('aria-activedescendant', item.id);
                    item.scrollIntoView({ block: 'nearest' });
                }
            });

            if (selectedIndex < 0) {
                searchInput.setAttribute('aria-activedescendant', '');
            }
        }

        function syncResultSemantics() {
            const items = getVisibleItems();
            items.forEach((item) => {
                if (!item.id) {
                    item.id = 'global-search-result-' + (++resultIdCounter);
                }
                item.setAttribute('role', 'option');
                item.setAttribute('aria-selected', 'false');
            });
            searchInput.setAttribute('aria-expanded', items.length > 0 ? 'true' : 'false');
        }
    })();
})();
