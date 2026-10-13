/**
 * Permission-based UI utilities
 * Handles permission checking and UI adaptation for action buttons
 */

(function (window) {
    "use strict";

    // Permission level constants (must match Django PermissionLevel)
    const PERMISSION_LEVELS = {
        NONE: 0,
        VIEWER: 10,
        EDITOR: 20,
        OWNER: 30,
    };

    /**
     * Create permission-aware action buttons formatter for Grid.js
     *
     * @param {Object} urls - URL templates or functions for actions
     * @param {Array} actions - Array of action configurations
     * @param {Object} options - Additional options
     * @param {Object} permissions - Permission data for entities {entityId: permissionLevel}
     * @returns {Function} Grid.js formatter function
     */
    function permissionAwareActionFormatter(urls, actions, options = {}, permissions = {}) {
        return function (cell, row) {
            const id = options.idResolver ? options.idResolver(row) : cell;
            const userPermission = permissions[id] || PERMISSION_LEVELS.NONE;

            // Debug logging - only log when permission is NONE (might indicate a problem)
            if (userPermission === PERMISSION_LEVELS.NONE) {
                console.warn(
                    `[PermissionUtils.formatter] id=${id} has permission=NONE. Permissions object has ${
                        Object.keys(permissions).length
                    } keys. id in permissions: ${id in permissions}`
                );
            }

            return gridjs.html(
                window.GridActions.renderActionBar({
                    urls,
                    actions,
                    row,
                    id,
                    permissionLevel: userPermission,
                })
            );
        };
    }

    /**
     * Check if user has permission for a specific action
     *
     * @param {number} userPermission - User's permission level
     * @param {string} action - Action name ('view', 'edit', 'delete', 'share')
     * @returns {boolean} True if user has permission
     */
    function hasPermission(userPermission, action) {
        const requirements = {
            view: PERMISSION_LEVELS.VIEWER,
            edit: PERMISSION_LEVELS.EDITOR,
            delete: PERMISSION_LEVELS.OWNER,
            share: PERMISSION_LEVELS.OWNER,
            create: PERMISSION_LEVELS.NONE, // Create doesn't require object permissions
        };

        const required = requirements[action] || PERMISSION_LEVELS.OWNER;
        return userPermission >= required;
    }

    /**
     * Update UI elements based on permissions
     * Enables or disables elements based on user's permission level
     *
     * @param {string} containerId - Container element ID
     * @param {Object} permissions - Permission data {entityId: permissionLevel}
     */
    function updateUIForPermissions(containerId, permissions) {
        const container = document.getElementById(containerId);
        if (!container) return;

        // Permission requirements for each action
        const actionRequirements = {
            detail: PERMISSION_LEVELS.VIEWER,
            view: PERMISSION_LEVELS.VIEWER,
            create: PERMISSION_LEVELS.EDITOR,
            edit: PERMISSION_LEVELS.EDITOR,
            share: PERMISSION_LEVELS.OWNER,
            delete: PERMISSION_LEVELS.OWNER,
            expand: PERMISSION_LEVELS.VIEWER,
        };

        // Update action buttons. Grid action bars are skipped: their formatter reads the live
        // permissions object at render time and already shows locked or hidden actions.
        const actionButtons = container.querySelectorAll(
            "[data-action][data-entity-id]:not(.grid-action-bar *)"
        );
        actionButtons.forEach((button) => {
            const entityId = button.dataset.entityId;
            const action = button.dataset.action;
            const userPermission = permissions[entityId] || PERMISSION_LEVELS.NONE;
            const requiredPermission = actionRequirements[action] || PERMISSION_LEVELS.OWNER;
            const hasRequiredPermission = userPermission >= requiredPermission;

            if (hasRequiredPermission) {
                // Enable button
                button.disabled = false;
                button.style.opacity = "1";
                button.style.pointerEvents = "";
                button.title = action.charAt(0).toUpperCase() + action.slice(1);
                button.dataset.permissionLevel = userPermission;

                // Restore href for anchor tags if it was removed
                const url =
                    button.dataset.detailUrl || button.dataset.editUrl || button.dataset.deleteUrl;
                if (button.tagName === "A" && !button.getAttribute("href") && url) {
                    button.setAttribute("href", url);
                }
            } else {
                // Disable button
                button.disabled = true;
                button.style.opacity = "0.5";
                button.title = `You do not have permission to ${action} this object`;
                button.dataset.permissionLevel = userPermission;

                // Remove href for anchor tags
                if (button.tagName === "A") {
                    button.removeAttribute("href");
                    button.style.pointerEvents = "none";
                }
            }
        });

        // Update permission level data attribute on containers
        const actionContainers = container.querySelectorAll(
            ".quick-actions-container[data-permission-level]"
        );
        actionContainers.forEach((cont) => {
            const buttons = cont.querySelectorAll("[data-entity-id]");
            if (buttons.length > 0) {
                const entityId = buttons[0].dataset.entityId;
                const userPermission = permissions[entityId] || PERMISSION_LEVELS.NONE;
                cont.dataset.permissionLevel = userPermission;
            }
        });
    }

    /**
     * Initialize permission-based UI for a container
     *
     * @param {string} containerId - Container element ID
     * @param {Object} permissions - Permission data {entityId: permissionLevel}
     */
    function initPermissionUI(containerId, permissions) {
        // Initial update
        updateUIForPermissions(containerId, permissions);

        // Listen for grid updates and reapply permissions
        document.addEventListener("list:update", function () {
            setTimeout(() => {
                updateUIForPermissions(containerId, permissions);
            }, 100);
        });

        // Listen for permission changes
        document.addEventListener("permissions:updated", function (event) {
            const updatedPermissions = event.detail || permissions;
            updateUIForPermissions(containerId, updatedPermissions);
        });
    }

    /**
     * Get permission level name for display
     *
     * @param {number} permissionLevel - Permission level constant
     * @returns {string} Human-readable permission name
     */
    function getPermissionName(permissionLevel) {
        const names = {
            [PERMISSION_LEVELS.NONE]: "None",
            [PERMISSION_LEVELS.VIEWER]: "Viewer",
            [PERMISSION_LEVELS.EDITOR]: "Editor",
            [PERMISSION_LEVELS.OWNER]: "Owner",
        };
        return names[permissionLevel] || "Unknown";
    }

    /**
     * Show/hide UI elements based on permissions
     *
     * @param {Element} element - DOM element to show/hide
     * @param {boolean} show - Whether to show the element
     * @param {string} reason - Reason for hiding (for tooltip)
     */
    function toggleElementVisibility(element, show, reason = "") {
        if (show) {
            element.style.display = "";
            element.disabled = false;
            element.style.opacity = "1";
            element.removeAttribute("title");
        } else {
            if (element.dataset.hideMode === "disable") {
                // Disable instead of hide
                element.disabled = true;
                element.style.opacity = "0.5";
                if (reason) {
                    element.title = reason;
                    element.setAttribute("data-bs-toggle", "tooltip");
                }
            } else {
                // Hide completely
                element.style.display = "none";
            }
        }
    }

    // Export public API
    window.PermissionUtils = {
        PERMISSION_LEVELS: PERMISSION_LEVELS,
        permissionAwareActionFormatter: permissionAwareActionFormatter,
        hasPermission: hasPermission,
        updateUIForPermissions: updateUIForPermissions,
        initPermissionUI: initPermissionUI,
        getPermissionName: getPermissionName,
        toggleElementVisibility: toggleElementVisibility,
    };
})(window);
