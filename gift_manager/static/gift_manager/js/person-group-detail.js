(function () {
    "use strict";

    const root = document.querySelector("[data-person-group-detail]");
    if (!root || root.dataset.groupDetailControllerInitialized === "true") return;

    root.dataset.groupDetailControllerInitialized = "true";

    const gridContainers = Array.from(root.querySelectorAll("[data-group-detail-grid]"));
    const gridIds = gridContainers.map((gridContainer) => gridContainer.id);
    const pendingActionWidthFrames = new Map();

    function applyGroupDetailColumnWidths(gridContainer, actionColumnIndex, actionWidth) {
        const table = gridContainer.querySelector(".gridjs-table");
        const headerCells = table?.querySelectorAll("thead tr:first-child th");
        if (!table || !headerCells?.length || actionColumnIndex < 0) return;

        let columns = table.querySelector(":scope > colgroup[data-group-detail-columns]");
        if (!columns || columns.children.length !== headerCells.length) {
            columns?.remove();
            columns = document.createElement("colgroup");
            columns.dataset.groupDetailColumns = "";
            headerCells.forEach(() => columns.append(document.createElement("col")));
            table.insertBefore(columns, table.firstChild);
        }

        headerCells.forEach((header) => header.style.removeProperty("width"));
        const adaptiveColumnCount = headerCells.length - 1;
        const rootFontSize = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
        const minimumAdaptiveColumnWidth = 6 * rootFontSize;
        const minimumTableWidth = actionWidth
            + adaptiveColumnCount * minimumAdaptiveColumnWidth;
        gridContainer.style.setProperty(
            "--group-detail-min-column-width",
            `${minimumAdaptiveColumnWidth}px`
        );
        gridContainer.style.setProperty(
            "--group-detail-min-table-width",
            `${Math.ceil(minimumTableWidth)}px`
        );
        const adaptiveColumnWidth = adaptiveColumnCount > 0
            ? `calc(${100 / adaptiveColumnCount}% - ${actionWidth / adaptiveColumnCount}px)`
            : "";
        Array.from(columns.children).forEach((column, index) => {
            if (index === actionColumnIndex) {
                column.style.width = `${actionWidth}px`;
            } else {
                column.style.width = adaptiveColumnWidth;
            }
        });
    }

    function measureGroupDetailActionsWidth(gridContainer) {
        let measuredWidth = 0;
        let actionColumnIndex = -1;
        gridContainer.querySelectorAll(".quick-actions-container").forEach((buttons) => {
            const cell = buttons.closest(".gridjs-td");
            if (!cell) return;

            const bounds = buttons.getBoundingClientRect();
            if (bounds.width <= 0) return;

            actionColumnIndex = cell.cellIndex;
            const cellStyle = getComputedStyle(cell);
            const horizontalPadding =
                parseFloat(cellStyle.paddingLeft) + parseFloat(cellStyle.paddingRight);
            measuredWidth = Math.max(
                measuredWidth,
                Math.max(buttons.scrollWidth, bounds.width) + horizontalPadding
            );
        });

        if (measuredWidth > 0 && actionColumnIndex >= 0) {
            const actionWidth = Math.ceil(measuredWidth);
            gridContainer.style.setProperty("--group-detail-actions-width", `${actionWidth}px`);
            applyGroupDetailColumnWidths(gridContainer, actionColumnIndex, actionWidth);
        }
    }

    function scheduleGroupDetailActionsWidth(gridContainer) {
        const pendingFrame = pendingActionWidthFrames.get(gridContainer);
        if (pendingFrame) cancelAnimationFrame(pendingFrame);

        pendingActionWidthFrames.set(
            gridContainer,
            requestAnimationFrame(() => {
                pendingActionWidthFrames.delete(gridContainer);
                measureGroupDetailActionsWidth(gridContainer);
            })
        );
    }

    function scheduleAllGroupDetailActionsWidths() {
        gridContainers.forEach(scheduleGroupDetailActionsWidth);
    }

    gridContainers.forEach((gridContainer) => {
        new MutationObserver(() => scheduleGroupDetailActionsWidth(gridContainer)).observe(
            gridContainer,
            { childList: true, subtree: true }
        );
    });

    const tabs = document.querySelector("[data-group-detail-tabs]");
    tabs?.querySelectorAll('[data-bs-toggle="tab"]').forEach((tab) => {
        tab.addEventListener("shown.bs.tab", scheduleAllGroupDetailActionsWidths);
    });
    document.addEventListener("grid:refreshed", (event) => {
        const refreshedGridIndex = gridIds.indexOf(event.detail?.containerId);
        if (refreshedGridIndex >= 0) {
            scheduleGroupDetailActionsWidth(gridContainers[refreshedGridIndex]);
        }
    });
    window.addEventListener("resize", scheduleAllGroupDetailActionsWidths);
    if (document.fonts?.ready) {
        document.fonts.ready.then(scheduleAllGroupDetailActionsWidths);
    }
    scheduleAllGroupDetailActionsWidths();

    // Refresh the server-rendered detail after a contextual create succeeds so
    // member counts and gift-plan grids include the newly created object.
    let refreshAfterGroupDetailCreate = false;
    root.querySelectorAll("[data-group-detail-create]").forEach((button) => {
        button.addEventListener("click", () => {
            refreshAfterGroupDetailCreate = true;
        });
    });

    const editPanelId = root.dataset.groupDetailEditPanelId;
    const editPanel = editPanelId ? document.getElementById(editPanelId) : null;
    editPanel?.addEventListener("hidden.bs.offcanvas", () => {
        refreshAfterGroupDetailCreate = false;
    });

    document.addEventListener("list:update", () => {
        if (refreshAfterGroupDetailCreate) {
            window.location.reload();
        }
    });
})();
