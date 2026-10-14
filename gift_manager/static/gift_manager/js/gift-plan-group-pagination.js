(function () {
    "use strict";

    const defaultRowsPerPage = 2;
    const pageState = {};
    let resizeTimer = null;

    function getColumnCount(list) {
        const columns = window.getComputedStyle(list).gridTemplateColumns
            .split(" ")
            .filter((column) => column && column !== "none").length;

        return Math.max(columns || 1, 1);
    }

    function cardMatchesFilter(card, recipientKey) {
        return !recipientKey || card.dataset.recipientKey === recipientKey;
    }

    function updateSection(section) {
        const groupKey = section.dataset.giftPlanGroupPaginated;
        const list = section.querySelector("[data-gift-plan-group-list]");
        const pagination = section.querySelector("[data-gift-plan-group-pagination]");
        if (!list) return;

        // The recipient filter hides non-matching cards itself; only page through the rest.
        const filter = section.querySelector("[data-group-recipient-filter]");
        const recipientKey = filter ? filter.value : "";
        const cards = Array.from(list.querySelectorAll(".gift-plan-card"));
        const matchingCards = cards.filter((card) => cardMatchesFilter(card, recipientKey));

        const rowsPerPage = Number.parseInt(
            section.dataset.giftPlanGroupRowsPerPage || defaultRowsPerPage.toString(),
            10
        ) || defaultRowsPerPage;
        const pageSize = Math.max(getColumnCount(list) * rowsPerPage, 1);
        const pageCount = Math.max(Math.ceil(matchingCards.length / pageSize), 1);
        const currentPage = Math.min(Math.max(pageState[groupKey] || 0, 0), pageCount - 1);
        const firstVisibleIndex = currentPage * pageSize;
        const firstHiddenIndex = firstVisibleIndex + pageSize;

        pageState[groupKey] = currentPage;
        section.dataset.giftPlanGroupPageSize = pageSize.toString();

        cards.forEach((card) => {
            card.hidden = false;
        });
        matchingCards.forEach((card, index) => {
            card.hidden = index < firstVisibleIndex || index >= firstHiddenIndex;
        });

        // Reserve every row of a page, even when the last page is short, so paging never
        // moves the controls or the sections below.
        list.style.gridTemplateRows = pageCount > 1
            ? `repeat(${rowsPerPage}, var(--gift-plan-card-height))`
            : "";

        if (!pagination) return;

        pagination.hidden = pageCount <= 1;
        const previousButton = pagination.querySelector('[data-gift-plan-group-page="previous"]');
        const nextButton = pagination.querySelector('[data-gift-plan-group-page="next"]');
        const status = pagination.querySelector("[data-gift-plan-group-page-status]");
        if (previousButton) previousButton.disabled = currentPage <= 0;
        if (nextButton) nextButton.disabled = currentPage >= pageCount - 1;
        if (status) status.textContent = `${currentPage + 1} / ${pageCount}`;
    }

    function init(root) {
        (root || document).querySelectorAll("[data-gift-plan-group-paginated]").forEach(updateSection);
    }

    document.addEventListener("click", function (event) {
        const button = event.target.closest("[data-gift-plan-group-page]");
        if (!button) return;

        const section = button.closest("[data-gift-plan-group-paginated]");
        if (!section) return;

        const groupKey = section.dataset.giftPlanGroupPaginated;
        const direction = button.dataset.giftPlanGroupPage === "next" ? 1 : -1;
        pageState[groupKey] = (pageState[groupKey] || 0) + direction;
        updateSection(section);
    });

    document.addEventListener("change", function (event) {
        const select = event.target.closest("[data-group-recipient-filter]");
        if (!select) return;

        const section = select.closest("[data-gift-plan-group-paginated]");
        if (!section) return;

        pageState[section.dataset.giftPlanGroupPaginated] = 0;
        updateSection(section);
    });

    window.addEventListener("resize", function () {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(function () {
            init(document);
        }, 120);
    });

    document.addEventListener("gift-plan-workspace:refreshed", function () {
        init(document);
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            init(document);
        });
    } else {
        init(document);
    }

    window.GiftPlanGroupPagination = {
        init: init,
    };
})();
