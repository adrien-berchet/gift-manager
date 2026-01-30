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
     * Hides or disables elements that user doesn't have permission for
     *
     * @param {string} containerId - Container element ID
     * @param {Object} permissions - Permission data {entityId: permissionLevel}
     */
    function updateUIForPermissions(containerId, permissions) {
        const container = document.getElementById(containerId);
        if (!container) return;

        // Update action buttons
        const actionButtons = container.querySelectorAll('[data-action][data-entity-id]');
        actionButtons.forEach(button => {
            const entityId = button.dataset.entityId;
            const action = button.dataset.action;
            const userPermission = permissions[entityId] || PERMISSION_LEVELS.NONE;

            if (!hasPermission(userPermission, action)) {
                // Disable button and add tooltip
                button.disabled = true;
                button.style.opacity = '0.5';
                button.title = `You do not have permission to ${action} this object`;

                // Remove href for anchor tags
                if (button.tagName === 'A') {
                    button.removeAttribute('href');
                    button.style.pointerEvents = 'none';
                }
            }
        });

        // Update create buttons (these don't require object permissions)
        const createButtons = container.querySelectorAll('[data-action="create"]');
        createButtons.forEach(button => {
            // Create buttons are always enabled unless explicitly disabled
            if (!button.hasAttribute('disabled')) {
                button.disabled = false;
                button.style.opacity = '1';
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
