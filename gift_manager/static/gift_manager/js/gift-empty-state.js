/**
 * Gift list: switch between the grid and the "No gifts yet" empty state as gifts are created
 * or deleted, without reloading the page.
 *
 * The page renders both and the server hides one of them. After a create, edit or delete the
 * grid refreshes in place; this then shows the grid when it has rows. An empty grid does not
 * mean "no gifts" (the search and the "Not in a plan yet" filter empty it too), so in that case
 * the server render of the page decides, through the empty state's hidden attribute.
 */
(function () {
    'use strict';

    function init(options) {
        const grid = options.grid;
        const listBody = document.getElementById(options.listBodyId);
        const emptyState = document.getElementById(options.emptyStateId);
        if (!grid || !listBody || !emptyState) return;

        let waitingForRefresh = false;

        function show(hasGifts) {
            listBody.hidden = !hasGifts;
            emptyState.hidden = hasGifts;
        }

        function askServer() {
            const url = new URL(window.location.href);
            url.searchParams.set('_t', Date.now());
            fetch(url.toString(), { cache: 'no-store', credentials: 'same-origin' })
                .then(response => response.text())
                .then(html => {
                    const doc = new DOMParser().parseFromString(html, 'text/html');
                    const serverEmptyState = doc.getElementById(options.emptyStateId);
                    if (serverEmptyState) show(serverEmptyState.hidden);
                })
                .catch(error => console.warn('[GiftList] Could not check for gifts:', error));
        }

        // Only refreshes that follow a data change count: paging and resizing also send
        // grid:refreshed without changing which gifts exist
        document.addEventListener('list:update', function () {
            waitingForRefresh = true;
        });
        document.addEventListener('grid:refreshed', function (event) {
            if (!waitingForRefresh || event.detail?.containerId !== options.gridId) return;
            waitingForRefresh = false;
            const rows = Array.isArray(grid.config.data) ? grid.config.data.length : 0;
            if (rows > 0) {
                show(true);
            } else {
                askServer();
            }
        });
    }

    window.GiftEmptyState = { init: init };
})();
