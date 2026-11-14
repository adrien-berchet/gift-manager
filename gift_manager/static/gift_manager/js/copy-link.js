// Copy the value of the input named by a button's data-copy-target to the clipboard.
(function () {
    'use strict';

    document.addEventListener('click', function (event) {
        const button = event.target.closest('[data-copy-target]');
        if (!button) return;
        const input = document.getElementById(button.dataset.copyTarget);
        if (!input) return;
        input.select();
        const done = function () {
            const label = button.querySelector('[data-copy-label]');
            if (label && button.dataset.copiedLabel) label.textContent = button.dataset.copiedLabel;
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(input.value).then(done, function () {});
        } else if (document.execCommand('copy')) {
            done();
        }
    });
})();
