/**
 * Guided gift plan flow: asks before the "Use an empty full form" link discards what the user
 * entered in the guided steps (earlier steps travel as hidden inputs, so the generic unsaved
 * changes tracking does not see them).
 */
(function () {
    "use strict";

    const IGNORED_FIELDS = ["csrfmiddlewaretoken", "step", "nav"];

    function hasEnteredData(form) {
        return Array.from(form.elements).some(function (element) {
            if (!element.name || IGNORED_FIELDS.includes(element.name)) {
                return false;
            }
            if (element.type === "submit" || element.type === "button") {
                return false;
            }
            return element.value !== "";
        });
    }

    // Capture phase: runs before the shell's create-link handler, which would load the form
    document.addEventListener(
        "click",
        function (event) {
            const link = event.target.closest && event.target.closest("[data-guided-full-form]");
            if (!link) {
                return;
            }

            const form = link.closest("form");
            if (!form || !hasEnteredData(form)) {
                return;
            }

            if (!window.confirm(link.dataset.confirmMessage)) {
                event.preventDefault();
                event.stopPropagation();
                return;
            }

            // The user agreed to discard: do not ask again through the unsaved changes prompt
            if (window.UnsavedChanges && window.UnsavedChanges.clearForm) {
                window.UnsavedChanges.clearForm(form);
            }
        },
        true
    );
})();
