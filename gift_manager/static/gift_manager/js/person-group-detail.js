(function () {
    "use strict";

    // The section is replaced after changes, so it is always looked up again
    const SECTION_SELECTOR = "[data-group-detail-section]";
    if (!document.querySelector(SECTION_SELECTOR) || window.groupDetailControllerInitialized) {
        return;
    }
    window.groupDetailControllerInitialized = true;

    const pendingActionWidthFrames = new Map();

    function currentSection() {
        return document.querySelector(SECTION_SELECTOR);
    }

    function currentGridContainers() {
        return Array.from(
            currentSection()?.querySelectorAll("[data-group-detail-grid]") || []
        );
    }

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
        currentGridContainers().forEach(scheduleGroupDetailActionsWidth);
    }

    function bindSection(section) {
        section.querySelectorAll("[data-group-detail-grid]").forEach((gridContainer) => {
            new MutationObserver(() => scheduleGroupDetailActionsWidth(gridContainer)).observe(
                gridContainer,
                { childList: true, subtree: true }
            );
        });
        section
            .querySelectorAll('[data-group-detail-tabs] [data-bs-toggle="tab"]')
            .forEach((tab) => {
                tab.addEventListener("shown.bs.tab", scheduleAllGroupDetailActionsWidths);
            });
        scheduleAllGroupDetailActionsWidths();
    }

    document.addEventListener("grid:refreshed", (event) => {
        const gridContainer = document.getElementById(event.detail?.containerId || "");
        if (gridContainer && currentGridContainers().includes(gridContainer)) {
            scheduleGroupDetailActionsWidth(gridContainer);
        }
    });
    window.addEventListener("resize", scheduleAllGroupDetailActionsWidths);
    if (document.fonts?.ready) {
        document.fonts.ready.then(scheduleAllGroupDetailActionsWidths);
    }
    bindSection(currentSection());

    // Member counts and several grids of the section depend on each other and are
    // rendered by the server: after a change made from this page (contextual create,
    // edit, delete or member removal), fetch the page again and swap the section in
    // place. Status changes also emit list:update but only touch their own row, so
    // only a click on one of these actions arms the refresh.
    const REFRESHING_ACTIONS = [
        "[data-group-detail-create]",
        '[data-action="create"]',
        '[data-action="edit"]',
        '[data-action="delete"]',
    ].join(", ");
    let refreshPending = false;
    let refreshController = null;

    // Capture phase: the global action handlers may stop the click from bubbling
    document.addEventListener(
        "click",
        (event) => {
            if (event.target.closest?.(REFRESHING_ACTIONS)) {
                refreshPending = true;
            }
        },
        true
    );

    // A cancelled form or confirmation must not refresh on a later, unrelated update.
    // On success list:update is handled before these panels finish hiding.
    const editPanelId = document.querySelector("[data-group-detail-edit-panel-id]")?.dataset
        .groupDetailEditPanelId;
    document.getElementById(editPanelId || "")?.addEventListener("hidden.bs.offcanvas", () => {
        refreshPending = false;
    });
    document.getElementById("confirmModal")?.addEventListener("hidden.bs.modal", () => {
        refreshPending = false;
    });

    document.addEventListener("list:update", () => {
        if (!refreshPending) return;
        refreshPending = false;
        refreshSection();
    });

    function keepActiveTab(section, freshSection) {
        const activeTab = section.querySelector('[data-bs-toggle="tab"].active');
        const freshActiveTab = activeTab && freshSection.querySelector(`#${CSS.escape(activeTab.id)}`);
        if (!freshActiveTab) return;

        freshSection.querySelectorAll('[data-bs-toggle="tab"]').forEach((tab) => {
            const isActive = tab === freshActiveTab;
            tab.classList.toggle("active", isActive);
            tab.setAttribute("aria-selected", String(isActive));
        });
        freshSection.querySelectorAll(".tab-pane").forEach((pane) => {
            const isActive = `#${pane.id}` === freshActiveTab.dataset.bsTarget;
            pane.classList.toggle("active", isActive);
            pane.classList.toggle("show", isActive);
        });
    }

    function runScripts(container) {
        // Scripts inserted from a parsed document never run: replace them with live copies
        container.querySelectorAll("script").forEach((parsedScript) => {
            const script = document.createElement("script");
            Array.from(parsedScript.attributes).forEach((attribute) => {
                script.setAttribute(attribute.name, attribute.value);
            });
            script.textContent = parsedScript.textContent;
            parsedScript.replaceWith(script);
        });
    }

    async function refreshSection() {
        refreshController?.abort();
        const controller = new AbortController();
        refreshController = controller;

        try {
            // A plain request: an HTMX one is answered with the detail panel partial
            const response = await fetch(window.location.href, {
                cache: "no-store",
                credentials: "same-origin",
                signal: controller.signal,
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const html = await response.text();
            if (controller.signal.aborted) return;

            const freshSection = new DOMParser()
                .parseFromString(html, "text/html")
                .querySelector(SECTION_SELECTOR);
            const section = currentSection();
            if (!freshSection || !section) throw new Error("Section not found");

            keepActiveTab(section, freshSection);
            const newSection = document.importNode(freshSection, true);
            // Keep the page height while the grids render, so the scroll position holds
            newSection.style.minHeight = `${section.offsetHeight}px`;
            section.replaceWith(newSection);
            runScripts(newSection);
            bindSection(newSection);
            window.setTimeout(() => newSection.style.removeProperty("min-height"), 500);
        } catch (error) {
            if (error.name === "AbortError") return;
            console.error("[PersonGroupDetail] Section refresh failed, reloading:", error);
            window.location.reload();
        }
    }
})();
