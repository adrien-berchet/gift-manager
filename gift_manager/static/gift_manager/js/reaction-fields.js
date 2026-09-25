(function () {
    "use strict";

    // Show the reaction section of the gift plan form only for given or abandoned statuses.
    document.addEventListener("change", function (event) {
        const select = event.target;
        if (!(select instanceof HTMLSelectElement) || select.name !== "status") return;

        const rateableStatuses = select.dataset.rateableStatuses;
        if (rateableStatuses === undefined) return;

        const form = select.closest("form");
        const section = form && form.querySelector("[data-reaction-fields]");
        if (!section) return;

        section.hidden = !rateableStatuses.split(",").includes(select.value);
    });
})();
