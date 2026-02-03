/**
 * Permission-based UI utilities
 * Handles permission checking and UI adaptation for action buttons
 */

(function (window) {
    'use strict';

    // Permission level constants (must match Django PermissionLevel)
    const PERMISSION_LEVELS = {
        NONE: 0,
        VIEWER: 10,
        EDITOR: 20,
        OWNER: 30
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
        const actionConfig = {
            give: {
                class: 'btn-primary',
                icon: 'fa-hand-holding-heart',
                title: 'Give',
                action: 'create',
                requiredPermission: PERMISSION_LEVELS.EDITOR
            },
            details: {
                class: 'btn-info',
                icon: 'fa-eye',
                title: 'Details',
                action: 'detail',
                requiredPermission: PERMISSION_LEVELS.VIEWER
            },
            edit: {
                class: 'btn-warning',
                icon: 'fa-edit',
                title: 'Edit',
                action: 'edit',
                requiredPermission: PERMISSION_LEVELS.EDITOR
            },
            delete: {
                class: 'btn-danger',
                icon: 'fa-trash',
                title: 'Delete',
                action: 'delete',
                requiredPermission: PERMISSION_LEVELS.OWNER
            },
            share: {
                class: 'btn-success',
                icon: 'fa-share-alt',
                title: 'Share',
                action: 'share',
                requiredPermission: PERMISSION_LEVELS.EDITOR
            },
            expand: {
                class: 'btn-outline-secondary',
                icon: 'fa-chevron-down',
                title: 'Expand',
                action: 'expand',
                requiredPermission: PERMISSION_LEVELS.VIEWER
            }
        };

        return function (cell, row) {
            const id = options.idResolver ? options.idResolver(row) : cell;
            const userPermission = permissions[id] || PERMISSION_LEVELS.NONE;

            // Debug logging - only log when permission is NONE (might indicate a problem)
            if (userPermission === PERMISSION_LEVELS.NONE) {
                console.warn(`[PermissionUtils.formatter] id=${id} has permission=NONE. Permissions object has ${Object.keys(permissions).length} keys. id in permissions: ${id in permissions}`);
                console.log(`[PermissionUtils.formatter] Available permission keys (first 5):`, Object.keys(permissions).slice(0, 5));
            }

            const resolveUrl = (urlTemplate, actionId) => {
                if (typeof urlTemplate === 'function') return urlTemplate(row);
                return urlTemplate ? urlTemplate.replace('{id}', actionId || id) : null;
            };

            const shouldDisplay = (action) => {
                if (typeof action === 'string') return true;
                return !action.condition || action.condition(row);
            };

            const buttons = actions
                .filter(shouldDisplay)
                .map(action => {
                    const actionType = typeof action === 'string' ? action : action.type;
                    const urlTemplate = urls[actionType];
                    const config = actionConfig[actionType];

                    if (!urlTemplate || !config) return null;

                    const url = resolveUrl(urlTemplate, typeof action === 'object' ? action.id : null);
                    if (!url) return null;

                    // Check if user has required permission
                    const hasPermission = userPermission >= config.requiredPermission;
                    const isEnabled = hasPermission;

                    // Generate tooltip message
                    let tooltip = config.title;
                    if (!hasPermission) {
                        tooltip = `You do not have permission to ${config.title.toLowerCase()} this object`;
                    }

                    // Create button HTML
                    if (isEnabled) {
                        return `<a href="${url}"
                                  class="btn ${config.class} btn-sm quick-action-btn"
                                  title="${tooltip}"
                                  data-action="${config.action}"
                                  data-entity-id="${id}"
                                  data-permission-level="${userPermission}"
                                  ${config.action === 'detail' ? 'data-detail-url="' + url + '"' : ''}
                                  ${config.action === 'edit' ? 'data-edit-url="' + url + '"' : ''}
                                  ${config.action === 'delete' ? 'data-delete-url="' + url + '"' : ''}
                                  ${config.action === 'expand' ? 'data-detail-url="' + url + '"' : ''}
                                  data-bs-toggle="tooltip"
                                  data-bs-placement="top">
                            <i class="fas ${config.icon}"></i>
                            <span class="btn-text d-none d-lg-inline ms-1">${config.title}</span>
                        </a>`;
                    } else {
                        return `<button class="btn ${config.class} btn-sm quick-action-btn"
                                       disabled
                                       title="${tooltip}"
                                       data-action="${config.action}"
                                       data-entity-id="${id}"
                                       data-permission-level="${userPermission}"
                                       data-bs-toggle="tooltip"
                                       data-bs-placement="top"
                                       style="opacity: 0.5;">
                            <i class="fas ${config.icon}"></i>
                            <span class="btn-text d-none d-lg-inline ms-1">${config.title}</span>
                        </button>`;
                    }
                })
                .filter(Boolean);

            return gridjs.html(`<div class="quick-actions-container" data-permission-level="${userPermission}">${buttons.join('')}</div>`);
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
            'view': PERMISSION_LEVELS.VIEWER,
            'edit': PERMISSION_LEVELS.EDITOR,
            'delete': PERMISSION_LEVELS.OWNER,
            'share': PERMISSION_LEVELS.EDITOR,
            'create': PERMISSION_LEVELS.NONE // Create doesn't require object permissions
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

        console.log(`[PermissionUtils.updateUIForPermissions] Updating UI for container ${containerId} with ${Object.keys(permissions).length} permission entries`);

        // Permission requirements for each action
        const actionRequirements = {
            'detail': PERMISSION_LEVELS.VIEWER,
            'view': PERMISSION_LEVELS.VIEWER,
            'create': PERMISSION_LEVELS.EDITOR,
            'edit': PERMISSION_LEVELS.EDITOR,
            'share': PERMISSION_LEVELS.EDITOR,
            'delete': PERMISSION_LEVELS.OWNER,
            'expand': PERMISSION_LEVELS.VIEWER
        };

        // Update action buttons
        const actionButtons = container.querySelectorAll('[data-action][data-entity-id]');
        actionButtons.forEach(button => {
            const entityId = button.dataset.entityId;
            const action = button.dataset.action;
            const userPermission = permissions[entityId] || PERMISSION_LEVELS.NONE;
            const requiredPermission = actionRequirements[action] || PERMISSION_LEVELS.OWNER;
            const hasRequiredPermission = userPermission >= requiredPermission;

            console.log(`[PermissionUtils.updateUIForPermissions] Button action=${action}, entityId=${entityId}, userPerm=${userPermission}, required=${requiredPermission}, hasPermission=${hasRequiredPermission}`);

            if (hasRequiredPermission) {
                // Enable button
                button.disabled = false;
                button.style.opacity = '1';
                button.style.pointerEvents = '';
                button.title = action.charAt(0).toUpperCase() + action.slice(1);
                button.dataset.permissionLevel = userPermission;

                // Restore href for anchor tags if it was removed
                const url = button.dataset.detailUrl || button.dataset.editUrl || button.dataset.deleteUrl;
                if (button.tagName === 'A' && !button.getAttribute('href') && url) {
                    button.setAttribute('href', url);
                }
            } else {
                // Disable button
                button.disabled = true;
                button.style.opacity = '0.5';
                button.title = `You do not have permission to ${action} this object`;
                button.dataset.permissionLevel = userPermission;

                // Remove href for anchor tags
                if (button.tagName === 'A') {
                    button.removeAttribute('href');
                    button.style.pointerEvents = 'none';
                }
            }
        });

        // Update permission level data attribute on containers
        const actionContainers = container.querySelectorAll('.quick-actions-container[data-permission-level]');
        actionContainers.forEach(cont => {
            const buttons = cont.querySelectorAll('[data-entity-id]');
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
        document.addEventListener('list:update', function() {
            setTimeout(() => {
                updateUIForPermissions(containerId, permissions);
            }, 100);
        });

        // Listen for permission changes
        document.addEventListener('permissions:updated', function(event) {
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
            [PERMISSION_LEVELS.NONE]: 'None',
            [PERMISSION_LEVELS.VIEWER]: 'Viewer',
            [PERMISSION_LEVELS.EDITOR]: 'Editor',
            [PERMISSION_LEVELS.OWNER]: 'Owner'
        };
        return names[permissionLevel] || 'Unknown';
    }

    /**
     * Show/hide UI elements based on permissions
     *
     * @param {Element} element - DOM element to show/hide
     * @param {boolean} show - Whether to show the element
     * @param {string} reason - Reason for hiding (for tooltip)
     */
    function toggleElementVisibility(element, show, reason = '') {
        if (show) {
            element.style.display = '';
            element.disabled = false;
            element.style.opacity = '1';
            element.removeAttribute('title');
        } else {
            if (element.dataset.hideMode === 'disable') {
                // Disable instead of hide
                element.disabled = true;
                element.style.opacity = '0.5';
                if (reason) {
                    element.title = reason;
                    element.setAttribute('data-bs-toggle', 'tooltip');
                }
            } else {
                // Hide completely
                element.style.display = 'none';
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
        toggleElementVisibility: toggleElementVisibility
    };

})(window);
