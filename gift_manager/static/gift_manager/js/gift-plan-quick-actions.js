(function () {
    "use strict";

    let activeButton = null;
    let activeInput = null;
    let activePicker = null;
    let activePickerScrollPosition = null;
    let activePlanPanel = null;
    let activePlanPicker = null;
    let isSubmitting = false;
    let pendingScrollPosition = null;
    let pendingScrollTimer = null;

    function getCookie(name) {
        if (!document.cookie) return null;

        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i += 1) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === `${name}=`) {
                return decodeURIComponent(cookie.substring(name.length + 1));
            }
        }
        return null;
    }

    function getCsrfToken(form) {
        const input = form.querySelector('input[name="csrfmiddlewaretoken"]');
        return (input && input.value) || getCookie("csrftoken") || "";
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = String(value || "");
        return div.innerHTML;
    }

    function parseHxTriggerEvents(headerValue) {
        if (!headerValue) return {};

        const trimmed = headerValue.trim();
        if (trimmed.startsWith("{")) {
            try {
                return JSON.parse(trimmed);
            } catch (error) {
                console.error("Could not parse HX-Trigger header:", error);
                return {};
            }
        }

        return trimmed
            .split(",")
            .map((eventName) => eventName.trim())
            .filter(Boolean)
            .reduce((events, eventName) => {
                events[eventName] = {};
                return events;
            }, {});
    }

    function dispatchHxTriggerEvents(response) {
        [
            "HX-Trigger",
            "HX-Trigger-After-Swap",
            "HX-Trigger-After-Settle",
        ].forEach((headerName) => {
            const events = parseHxTriggerEvents(response.headers.get(headerName));
            Object.keys(events).forEach((eventName) => {
                document.dispatchEvent(
                    new CustomEvent(eventName, { detail: events[eventName] || {} })
                );
            });
        });
    }

    function resetActiveButton() {
        if (!activeButton) return;

        activeButton.disabled = false;
        activeButton.setAttribute("aria-expanded", "false");
    }

    function rememberScrollPosition(scrollPosition) {
        pendingScrollPosition = scrollPosition || {
            left: window.scrollX,
            top: window.scrollY,
        };
        window.clearTimeout(pendingScrollTimer);
        pendingScrollTimer = window.setTimeout(function () {
            pendingScrollPosition = null;
        }, 3000);
    }

    function scrollToPosition(scrollPosition) {
        window.scrollTo({
            left: scrollPosition.left,
            top: scrollPosition.top,
            behavior: "instant",
        });
    }

    function restorePendingScrollPosition() {
        if (!pendingScrollPosition) return;

        const scrollPosition = pendingScrollPosition;
        // Refresh listeners should observe the restored position immediately.
        scrollToPosition(scrollPosition);
        window.requestAnimationFrame(function () {
            scrollToPosition(scrollPosition);
            window.requestAnimationFrame(function () {
                scrollToPosition(scrollPosition);
            });
        });
    }

    function finishPendingScrollRestore() {
        if (!pendingScrollPosition) return;

        restorePendingScrollPosition();
        window.clearTimeout(pendingScrollTimer);
        pendingScrollTimer = window.setTimeout(function () {
            pendingScrollPosition = null;
        }, 150);
    }

    function cancelPendingScrollRestore() {
        pendingScrollPosition = null;
        window.clearTimeout(pendingScrollTimer);
    }

    function blurActiveElement() {
        if (document.activeElement && typeof document.activeElement.blur === "function") {
            document.activeElement.blur();
        }
    }

    function closePicker() {
        resetActiveButton();

        if (activePicker) {
            activePicker.destroy();
        }
        if (activeInput) {
            activeInput.remove();
        }

        activeButton = null;
        activeInput = null;
        activePicker = null;
        activePickerScrollPosition = null;
        isSubmitting = false;
    }

    function closePlanningPanel() {
        resetActiveButton();

        if (activePlanPicker) {
            activePlanPicker.destroy();
        }
        if (activePlanPanel) {
            activePlanPanel.remove();
        }

        activePlanPicker = null;
        activePlanPanel = null;
        activeButton = null;
        isSubmitting = false;
    }

    function closeQuickActionControls() {
        closePicker();
        closePlanningPanel();
    }

    function isActivePlanCalendarTarget(target) {
        const calendar = target.closest(".flatpickr-calendar");
        if (!calendar || !activePlanPicker) return false;

        return calendar === activePlanPicker.calendarContainer;
    }

    function notifyError(message) {
        if (typeof window.showNotification === "function") {
            window.showNotification(message, "error");
        }
    }

    function getQuickActionUrl(form) {
        return form.dataset.quickActionUrl || form.getAttribute("action");
    }

    function buildRequestBody(form, dateValue) {
        const formData = new FormData(form);
        const actionInput = form.querySelector('input[name="action"]');

        formData.set("action", (actionInput && actionInput.value) || "set_date");
        formData.set("due_date", dateValue);

        return new URLSearchParams(formData);
    }

    function submitDate(form, button, dateValue) {
        const url = getQuickActionUrl(form);
        if (!url || isSubmitting) return;

        isSubmitting = true;
        button.disabled = true;
        rememberScrollPosition(activePickerScrollPosition);
        restorePendingScrollPosition();

        fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "HX-Request": "true",
                "X-CSRFToken": getCsrfToken(form),
            },
            body: buildRequestBody(form, dateValue).toString(),
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                blurActiveElement();
                closePicker();
                dispatchHxTriggerEvents(response);
            })
            .catch((error) => {
                console.error("Could not update gift plan due date:", error);
                resetActiveButton();
                isSubmitting = false;
                cancelPendingScrollRestore();
                notifyError("Could not update the due date. Please try again.");
            });
    }

    function buildPlanningRequestBody(form, panelForm) {
        const formData = new FormData(form);
        const actionInput = form.querySelector('input[name="action"]');
        const eventInput = panelForm.querySelector('[name="event"]');
        const dueDateInput = panelForm.querySelector('[name="due_date"]');

        formData.set("action", (actionInput && actionInput.value) || "plan");
        formData.set("event", eventInput ? eventInput.value : "");
        formData.set("due_date", dueDateInput ? dueDateInput.value : "");

        return new URLSearchParams(formData);
    }

    function submitPlanning(form, panelForm, button) {
        const url = getQuickActionUrl(form);
        if (!url || isSubmitting) return;

        isSubmitting = true;
        button.disabled = true;
        rememberScrollPosition();

        fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "HX-Request": "true",
                "X-CSRFToken": getCsrfToken(form),
            },
            body: buildPlanningRequestBody(form, panelForm).toString(),
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                blurActiveElement();
                closePlanningPanel();
                dispatchHxTriggerEvents(response);
            })
            .catch((error) => {
                console.error("Could not plan gift:", error);
                resetActiveButton();
                isSubmitting = false;
                cancelPendingScrollRestore();
                notifyError("Could not plan this gift. Please try again.");
            });
    }

    function updatePlanningSaveState(panel) {
        const eventInput = panel.querySelector('[name="event"]');
        const dueDateInput = panel.querySelector('[name="due_date"]');
        const saveButton = panel.querySelector("[data-gift-plan-plan-save]");

        if (!saveButton) return;
        saveButton.disabled = !(
            eventInput &&
            eventInput.value &&
            dueDateInput &&
            dueDateInput.value
        );
    }

    function positionPlanningPanel(panel, button) {
        const gap = 8;
        const margin = 8;
        const rect = button.getBoundingClientRect();
        const panelRect = panel.getBoundingClientRect();
        const maxLeft = Math.max(window.innerWidth - panelRect.width - margin, margin);
        const left = Math.min(Math.max(rect.left, margin), maxLeft);
        const belowTop = rect.bottom + gap;
        const aboveTop = rect.top - panelRect.height - gap;
        const top =
            belowTop + panelRect.height <= window.innerHeight - margin
                ? belowTop
                : Math.max(aboveTop, margin);

        panel.style.left = `${left}px`;
        panel.style.top = `${top}px`;
    }

    function getDefaultDate(button) {
        return button.dataset.currentDueDate || new Date();
    }

    function getFlatpickrLocale() {
        const language = document.documentElement.lang || "en";
        return language.toLowerCase().startsWith("fr") ? "fr" : "default";
    }

    function openDatePicker(button) {
        const form = button.closest(".gift-plan-date-action-form");
        if (!form || typeof window.flatpickr !== "function") {
            notifyError("The date picker could not be opened.");
            return;
        }

        if (activeButton === button && activePicker && activePicker.isOpen) {
            closePicker();
            return;
        }

        closePicker();

        activeButton = button;
        activePickerScrollPosition = {
            left: window.scrollX,
            top: window.scrollY,
        };
        activeInput = document.createElement("input");
        activeInput.type = "text";
        activeInput.className = "gift-plan-date-picker-source";
        activeInput.setAttribute("aria-hidden", "true");
        activeInput.setAttribute("tabindex", "-1");
        document.body.appendChild(activeInput);

        activePicker = window.flatpickr(activeInput, {
            appendTo: document.body,
            clickOpens: false,
            dateFormat: "Y-m-d",
            defaultDate: getDefaultDate(button),
            disableMobile: true,
            locale: getFlatpickrLocale(),
            positionElement: button,
            onReady: function (_selectedDates, _dateStr, instance) {
                instance.calendarContainer.classList.add(
                    "modern-datepicker",
                    "gift-plan-quick-date-picker"
                );
            },
            onChange: function (_selectedDates, dateStr) {
                if (dateStr) {
                    submitDate(form, button, dateStr);
                }
            },
            onClose: function () {
                if (!isSubmitting) {
                    resetActiveButton();
                }
            },
        });

        button.setAttribute("aria-expanded", "true");
        activePicker.open();
    }

    function getPlanningOptionHtml(form) {
        const template = form.querySelector("[data-gift-plan-event-options]");
        return template ? template.innerHTML : "";
    }

    function createPlanningPanel(form, button) {
        const labels = {
            event: button.dataset.eventLabel || "Event",
            dueDate: button.dataset.dueDateLabel || "Due date",
            chooseEvent: button.dataset.chooseEventLabel || "Choose event",
            cancel: button.dataset.cancelLabel || "Cancel",
            save: button.dataset.saveLabel || "Save",
        };

        const panel = document.createElement("div");
        panel.className = "gift-plan-plan-popover";
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-modal", "false");
        panel.innerHTML = `
            <form class="gift-plan-plan-panel-form">
                <div class="gift-plan-plan-field">
                    <label class="form-label" for="gift-plan-plan-event">${escapeHtml(
                        labels.event
                    )}</label>
                    <select id="gift-plan-plan-event"
                            name="event"
                            class="form-select form-select-sm"
                            required>
                        <option value="">${escapeHtml(labels.chooseEvent)}</option>
                        ${getPlanningOptionHtml(form)}
                    </select>
                </div>
                <div class="gift-plan-plan-field">
                    <label class="form-label" for="gift-plan-plan-due-date">${escapeHtml(
                        labels.dueDate
                    )}</label>
                    <input id="gift-plan-plan-due-date"
                           name="due_date"
                           type="text"
                           class="form-control form-control-sm"
                           required>
                </div>
                <div class="gift-plan-plan-actions">
                    <button type="button"
                            class="btn btn-sm btn-outline-secondary"
                            data-gift-plan-plan-cancel>${escapeHtml(labels.cancel)}</button>
                    <button type="submit"
                            class="btn btn-sm btn-primary"
                            data-gift-plan-plan-save>${escapeHtml(labels.save)}</button>
                </div>
            </form>
        `;

        const panelForm = panel.querySelector(".gift-plan-plan-panel-form");
        const eventInput = panel.querySelector('[name="event"]');
        const dueDateInput = panel.querySelector('[name="due_date"]');
        const cancelButton = panel.querySelector("[data-gift-plan-plan-cancel]");

        if (eventInput && button.dataset.currentEvent) {
            eventInput.value = button.dataset.currentEvent;
        }
        if (dueDateInput && button.dataset.currentDueDate) {
            dueDateInput.value = button.dataset.currentDueDate;
        }

        panelForm.addEventListener("submit", function (event) {
            event.preventDefault();
            submitPlanning(form, panelForm, button);
        });
        eventInput.addEventListener("change", function () {
            updatePlanningSaveState(panel);
        });
        dueDateInput.addEventListener("input", function () {
            updatePlanningSaveState(panel);
            if (activePlanPicker && dueDateInput.value) {
                activePlanPicker.close();
            }
        });
        cancelButton.addEventListener("click", closePlanningPanel);

        document.body.appendChild(panel);

        if (window.flatpickr && dueDateInput) {
            activePlanPicker = window.flatpickr(dueDateInput, {
                allowInput: true,
                appendTo: document.body,
                dateFormat: "Y-m-d",
                defaultDate: button.dataset.currentDueDate || null,
                disableMobile: true,
                locale: getFlatpickrLocale(),
                positionElement: dueDateInput,
                onChange: function (_selectedDates, dateStr, instance) {
                    dueDateInput.value = dateStr;
                    updatePlanningSaveState(panel);
                    if (dateStr) {
                        instance.close();
                    }
                },
                onReady: function (_selectedDates, _dateStr, instance) {
                    instance.calendarContainer.classList.add(
                        "modern-datepicker",
                        "gift-plan-quick-date-picker"
                    );
                },
            });
        }

        updatePlanningSaveState(panel);
        return panel;
    }

    function openPlanningPanel(button) {
        const form = button.closest(".gift-plan-planning-action-form");
        if (!form) return;

        if (activeButton === button && activePlanPanel) {
            closePlanningPanel();
            return;
        }

        closeQuickActionControls();

        activeButton = button;
        activePlanPanel = createPlanningPanel(form, button);
        button.setAttribute("aria-expanded", "true");
        positionPlanningPanel(activePlanPanel, button);

        const eventInput = activePlanPanel.querySelector('[name="event"]');
        if (eventInput) {
            eventInput.focus({ preventScroll: true });
        }
    }

    document.addEventListener("click", function (event) {
        const button = event.target.closest("[data-gift-plan-date-picker-button]");
        if (button) {
            event.preventDefault();
            openDatePicker(button);
        }

        const planningButton = event.target.closest("[data-gift-plan-planning-button]");
        if (planningButton) {
            event.preventDefault();
            openPlanningPanel(planningButton);
        }
    });

    document.addEventListener("pointerdown", function (event) {
        if (!activePlanPanel) return;
        if (activePlanPanel.contains(event.target)) return;
        if (isActivePlanCalendarTarget(event.target)) return;
        if (event.target.closest("[data-gift-plan-planning-button]")) return;

        closePlanningPanel();
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && (activePicker || activePlanPanel)) {
            closeQuickActionControls();
        }
    });

    document.addEventListener("list:update", closeQuickActionControls);
    document.addEventListener("gift-plan-workspace:refreshed", function () {
        closeQuickActionControls();
        finishPendingScrollRestore();
    });
    document.addEventListener("dashboard-live:refreshed", function () {
        closeQuickActionControls();
        finishPendingScrollRestore();
    });
    document.body.addEventListener("htmx:afterSwap", function (event) {
        if (event.detail && event.detail.target && event.detail.target.id === "dashboard-live") {
            finishPendingScrollRestore();
        }
    });
})();
