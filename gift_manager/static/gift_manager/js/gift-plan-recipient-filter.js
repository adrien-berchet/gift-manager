(function () {
    "use strict";

    const filterState = {};
    let activeButton = null;
    let activePopover = null;

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = String(value || "");
        return div.innerHTML;
    }

    function closePopover() {
        if (activeButton) {
            activeButton.setAttribute("aria-expanded", "false");
        }
        if (activePopover) {
            activePopover.remove();
        }
        activeButton = null;
        activePopover = null;
    }

    function applyFilter(groupKey, recipientKey) {
        const section = document.getElementById(`gift-plan-group-${groupKey}`);
        if (!section) return;

        const cards = section.querySelectorAll(".gift-plan-card[data-recipient-key]");
        let visibleCount = 0;
        cards.forEach((card) => {
            const matches = !recipientKey || card.dataset.recipientKey === recipientKey;
            card.style.display = matches ? "" : "none";
            if (matches) visibleCount += 1;
        });

        const countEl = section.querySelector(`[data-group-count="${groupKey}"]`);
        if (countEl) countEl.textContent = String(visibleCount);

        const emptyMessage = section.querySelector(`[data-group-empty-message="${groupKey}"]`);
        if (emptyMessage) {
            emptyMessage.style.display = visibleCount === 0 && cards.length > 0 ? "block" : "none";
        }
    }

    function currentOptionLabel(select) {
        const option = select.options[select.selectedIndex];
        return option ? option.textContent.trim() : "";
    }

    function updateTriggerLabel(button, select) {
        const labelEl = button.querySelector(".gift-plan-recipient-filter-trigger-label");
        if (labelEl) labelEl.textContent = currentOptionLabel(select);
    }

    function selectRecipient(select, button, value) {
        select.value = value;
        updateTriggerLabel(button, select);
        select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function positionPopover(popover, button) {
        const gap = 6;
        const margin = 8;
        const rect = button.getBoundingClientRect();
        const popoverRect = popover.getBoundingClientRect();
        const maxLeft = Math.max(window.innerWidth - popoverRect.width - margin, margin);
        const left = Math.min(Math.max(rect.left, margin), maxLeft);
        const belowTop = rect.bottom + gap;
        const aboveTop = rect.top - popoverRect.height - gap;
        const top =
            belowTop + popoverRect.height <= window.innerHeight - margin
                ? belowTop
                : Math.max(aboveTop, margin);

        popover.style.left = `${left}px`;
        popover.style.top = `${top}px`;
    }

    function renderOptionList(list, select, searchTerm, emptyLabel) {
        const term = searchTerm.trim().toLowerCase();
        list.innerHTML = "";

        let hasMatch = false;
        Array.from(select.options).forEach((option) => {
            const label = option.textContent.trim();
            if (term && !label.toLowerCase().includes(term)) return;

            hasMatch = true;
            const item = document.createElement("li");
            const itemButton = document.createElement("button");
            itemButton.type = "button";
            itemButton.className = "gift-plan-recipient-filter-option";
            itemButton.dataset.value = option.value;
            itemButton.textContent = label;
            if (option.value === select.value) {
                itemButton.classList.add("gift-plan-recipient-filter-option--active");
                itemButton.setAttribute("aria-selected", "true");
            }
            item.appendChild(itemButton);
            list.appendChild(item);
        });

        if (!hasMatch) {
            const empty = document.createElement("li");
            empty.className = "gift-plan-recipient-filter-empty";
            empty.textContent = emptyLabel;
            list.appendChild(empty);
        }
    }

    function openPopover(button, select) {
        if (activeButton === button) {
            closePopover();
            return;
        }
        closePopover();

        const searchPlaceholder = button.dataset.searchPlaceholder || "";
        const emptyLabel = button.dataset.emptyLabel || "";

        const popover = document.createElement("div");
        popover.className = "gift-plan-recipient-filter-popover";
        popover.setAttribute("role", "dialog");
        popover.setAttribute("aria-modal", "false");
        popover.innerHTML = `
            <input type="text"
                   class="form-control form-control-sm gift-plan-recipient-filter-search"
                   placeholder="${escapeHtml(searchPlaceholder)}"
                   aria-label="${escapeHtml(searchPlaceholder)}">
            <ul class="gift-plan-recipient-filter-list"></ul>
        `;

        const searchInput = popover.querySelector(".gift-plan-recipient-filter-search");
        const list = popover.querySelector(".gift-plan-recipient-filter-list");

        renderOptionList(list, select, "", emptyLabel);

        searchInput.addEventListener("input", function () {
            renderOptionList(list, select, searchInput.value, emptyLabel);
        });

        searchInput.addEventListener("keydown", function (event) {
            if (event.key !== "Enter") return;
            event.preventDefault();
            const firstOption = list.querySelector(".gift-plan-recipient-filter-option");
            if (!firstOption) return;
            selectRecipient(select, button, firstOption.dataset.value);
            closePopover();
            button.focus();
        });

        list.addEventListener("click", function (event) {
            const optionButton = event.target.closest(".gift-plan-recipient-filter-option");
            if (!optionButton) return;
            selectRecipient(select, button, optionButton.dataset.value);
            closePopover();
            button.focus();
        });

        document.body.appendChild(popover);
        activeButton = button;
        activePopover = popover;
        button.setAttribute("aria-expanded", "true");
        positionPopover(popover, button);
        searchInput.focus({ preventScroll: true });
    }

    function buildTrigger(select) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "form-select form-select-sm gift-plan-recipient-filter-trigger";
        button.setAttribute("aria-haspopup", "dialog");
        button.setAttribute("aria-expanded", "false");
        const ariaLabel = select.getAttribute("aria-label");
        if (ariaLabel) button.setAttribute("aria-label", ariaLabel);
        button.dataset.searchPlaceholder = select.dataset.searchPlaceholder || "";
        button.dataset.emptyLabel = select.dataset.emptyLabel || "";

        const label = document.createElement("span");
        label.className = "gift-plan-recipient-filter-trigger-label";
        button.appendChild(label);
        updateTriggerLabel(button, select);

        button.addEventListener("click", function (event) {
            event.preventDefault();
            openPopover(button, select);
        });

        return button;
    }

    function enhanceSelect(select) {
        if (select.dataset.recipientFilterEnhanced === "true") return;
        select.dataset.recipientFilterEnhanced = "true";
        select.classList.add("gift-plan-recipient-filter-select--enhanced");

        const button = buildTrigger(select);
        select.insertAdjacentElement("afterend", button);
    }

    function enhance(root) {
        (root || document).querySelectorAll("[data-group-recipient-filter]").forEach(enhanceSelect);
    }

    function restore(root) {
        const scope = root || document;
        enhance(scope);
        scope.querySelectorAll("[data-group-recipient-filter]").forEach((select) => {
            const groupKey = select.dataset.groupRecipientFilter;
            let storedValue = filterState[groupKey] || "";
            const hasOption = Array.from(select.options).some(
                (option) => option.value === storedValue
            );
            if (!hasOption) {
                storedValue = "";
                filterState[groupKey] = "";
            }
            select.value = storedValue;
            const button = select.nextElementSibling;
            if (button && button.classList.contains("gift-plan-recipient-filter-trigger")) {
                updateTriggerLabel(button, select);
            }
            applyFilter(groupKey, storedValue);
        });
    }

    document.addEventListener("change", function (event) {
        const select = event.target.closest("[data-group-recipient-filter]");
        if (!select) return;
        const groupKey = select.dataset.groupRecipientFilter;
        filterState[groupKey] = select.value;
        applyFilter(groupKey, select.value);
    });

    document.addEventListener("pointerdown", function (event) {
        if (!activePopover) return;
        if (activePopover.contains(event.target)) return;
        if (activeButton && activeButton.contains(event.target)) return;
        closePopover();
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && activePopover) {
            const buttonToFocus = activeButton;
            closePopover();
            if (buttonToFocus) buttonToFocus.focus();
        }
    });

    document.addEventListener("list:update", closePopover);
    document.addEventListener("gift-plan-workspace:refreshed", closePopover);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            enhance(document);
        });
    } else {
        enhance(document);
    }

    window.GiftPlanRecipientFilter = {
        enhance: enhance,
        restore: restore,
    };
})();
