// Contact import preview: "Select all" / "Select none" and the live selected count.
// Without JavaScript the controls stay hidden and the checkboxes work on their own.
(function () {
    'use strict';

    function init() {
        const form = document.querySelector('[data-contact-import]');
        if (!form) return;
        const boxes = Array.from(form.querySelectorAll('input[type="checkbox"][name="selected"]'));
        const count = form.querySelector('[data-selected-count]');
        const controls = form.querySelector('[data-contact-import-controls]');

        function updateCount() {
            if (count) count.textContent = String(boxes.filter((box) => box.checked).length);
        }

        if (controls) {
            controls.hidden = false;
            controls.addEventListener('click', function (event) {
                const button = event.target.closest('[data-select]');
                if (!button) return;
                const checked = button.dataset.select === 'all';
                boxes.forEach((box) => { box.checked = checked; });
                updateCount();
            });
        }
        form.addEventListener('change', function (event) {
            if (event.target.matches('input[name="selected"]')) updateCount();
        });
        updateCount();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
