/**
 * Stop Bootstrap modals and offcanvas panels from shifting the page.
 *
 * theme.css reserves the root scrollbar gutter permanently (`scrollbar-gutter: stable`,
 * or `overflow-y: scroll` as a fallback). When a modal or offcanvas opens, Bootstrap's
 * ScrollBarHelper hides the body overflow and pads the body and fixed elements by the
 * measured scrollbar width. With a stable gutter nothing disappears, so that padding
 * pushes the navbar and page content left. Report a zero width in that case.
 *
 * ScrollBarHelper is not exported by the bundle, so its prototype is reached through
 * a throwaway Modal instance.
 */
(function () {
    "use strict";

    if (!window.bootstrap || !window.bootstrap.Modal) {
        return;
    }

    function rootKeepsScrollbarGutter() {
        const rootStyle = window.getComputedStyle(document.documentElement);
        return (
            (rootStyle.scrollbarGutter || "").includes("stable") ||
            rootStyle.overflowY === "scroll"
        );
    }

    const probe = new window.bootstrap.Modal(document.createElement("div"));
    const scrollBarHelper = probe._scrollBar;
    probe.dispose();

    const helperPrototype = scrollBarHelper && Object.getPrototypeOf(scrollBarHelper);
    if (!helperPrototype || typeof helperPrototype.getWidth !== "function") {
        return;
    }

    const getWidth = helperPrototype.getWidth;
    helperPrototype.getWidth = function () {
        return rootKeepsScrollbarGutter() ? 0 : getWidth.call(this);
    };
})();
