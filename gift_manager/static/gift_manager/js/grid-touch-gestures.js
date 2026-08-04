/**
 * Grid Touch Gestures Enhancement
 * Adds touch gesture support to Grid.js tables
 */

(function() {
    'use strict';

    const GridTouchGestures = {
        init: function(gridId, entityType, urls) {
            this.gridId = gridId;
            this.entityType = entityType;
            this.urls = urls || {};

            // Wait for grid to be ready
            this.waitForGrid(() => {
                this.enhanceGridRows();
                this.setupGridObserver();
            });
        },

        waitForGrid: function(callback) {
            const checkGrid = () => {
                const gridContainer = document.getElementById(this.gridId);
                const rows = gridContainer ? gridContainer.querySelectorAll('tbody tr') : [];

                if (rows.length > 0) {
                    callback();
                } else {
                    setTimeout(checkGrid, 100);
                }
            };

            checkGrid();
        },

        setupGridObserver: function() {
            const gridContainer = document.getElementById(this.gridId);
            if (!gridContainer) return;

            // Observe changes to the grid (pagination, sorting, filtering)
            const observer = new MutationObserver((mutations) => {
                let shouldEnhance = false;

                mutations.forEach((mutation) => {
                    if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                        // Check if new rows were added
                        const hasNewRows = Array.from(mutation.addedNodes).some(node =>
                            node.nodeType === Node.ELEMENT_NODE &&
                            (node.tagName === 'TR' || node.querySelector('tr'))
                        );

                        if (hasNewRows) {
                            shouldEnhance = true;
                        }
                    }
                });

                if (shouldEnhance) {
                    setTimeout(() => this.enhanceGridRows(), 50);
                }
            });

            observer.observe(gridContainer, {
                childList: true,
                subtree: true
            });
        },

        enhanceGridRows: function() {
            const gridContainer = document.getElementById(this.gridId);
            if (!gridContainer) return;

            const rows = gridContainer.querySelectorAll('tbody tr');

            rows.forEach((row, index) => {
                if (row.dataset.touchEnhanced) return; // Already enhanced

                const entityId = this.extractEntityId(row, index);
                if (!entityId) return;

                // Add touch gesture data attributes
                this.addTouchGestureAttributes(row, entityId);

                // Mark as enhanced
                row.dataset.touchEnhanced = 'true';
            });
        },

        extractEntityId: function(row, index) {
            // Try to get entity ID from existing data attributes
            let entityId = row.dataset.entityId || row.dataset[this.entityType + 'Id'];

            if (!entityId) {
                // Try to extract from action buttons
                const actionButton = row.querySelector('[data-entity-id]');
                if (actionButton) {
                    entityId = actionButton.dataset.entityId;
                }
            }

            if (!entityId) {
                // Try to extract from URLs in action buttons
                const editButton = row.querySelector('[data-edit-url]');
                if (editButton) {
                    const url = editButton.dataset.editUrl;
                    const match = url.match(/\/([a-f0-9-]{36})\//); // UUID pattern
                    if (match) {
                        entityId = match[1];
                    }
                }
            }

            return entityId;
        },

        addTouchGestureAttributes: function(row, entityId) {
            // Make row swipeable
            row.classList.add('swipeable-item');
            row.dataset.swipeable = 'true';
            row.dataset.entityId = entityId;
            row.dataset.entityType = this.entityType;

            // Add swipe action URLs based on available action buttons
            const actionButtons = row.querySelectorAll('.quick-action-btn');

            actionButtons.forEach(button => {
                const action = button.dataset.action;
                const url = button.getAttribute('href') || button.dataset[action + 'Url'];

                if (url) {
                    switch (action) {
                        case 'edit':
                            row.dataset.editUrl = url;
                            break;
                        case 'delete':
                            row.dataset.deleteUrl = url;
                            break;
                        case 'detail':
                            row.dataset.detailUrl = url;
                            break;
                        case 'share':
                            row.dataset.shareUrl = url;
                            break;
                    }
                }
            });

            // Add long press support for context menu
            row.dataset.longPress = 'true';

            // Add touch-friendly styling
            row.style.minHeight = '60px';
            row.style.cursor = 'pointer';
        },

        // Static method to initialize for common entity types
        initForEntityType: function(gridId, entityType) {
            const urlPatterns = {
                person: {
                    edit: '/persons/{id}/edit/',
                    delete: '/persons/{id}/delete/',
                    detail: '/persons/{id}/',
                    share: '/share/'
                },
                gift: {
                    edit: '/gifts/{id}/edit/',
                    delete: '/gifts/{id}/delete/',
                    detail: '/gifts/{id}/',
                    share: '/share/'
                },
                event: {
                    edit: '/events/{id}/edit/',
                    delete: '/events/{id}/delete/',
                    detail: '/events/{id}/',
                    share: '/share/'
                },
                relation: {
                    edit: '/relations/{id}/edit/',
                    delete: '/relations/{id}/delete/',
                    detail: '/relations/{id}/',
                    share: '/share/'
                },
                person_group: {
                    edit: '/person-groups/{id}/edit/',
                    delete: '/person-groups/{id}/delete/',
                    detail: '/person-groups/{id}/',
                    share: '/share/'
                }
            };

            const urls = urlPatterns[entityType] || {};
            this.init(gridId, entityType, urls);
        }
    };

    // Expose to global scope
    window.GridTouchGestures = GridTouchGestures;

    // Auto-initialize for known grids when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        // Common grid IDs and their entity types
        const gridConfigs = [
            { id: 'person-grid', type: 'person' },
            { id: 'gift-grid', type: 'gift' },
            { id: 'event-grid', type: 'event' },
            { id: 'relation-grid', type: 'relation' },
            { id: 'person-group-grid', type: 'person_group' }
        ];

        gridConfigs.forEach(config => {
            const gridElement = document.getElementById(config.id);
            if (gridElement) {
                GridTouchGestures.initForEntityType(config.id, config.type);
            }
        });
    });

    // Also initialize after HTMX updates
    document.body.addEventListener('htmx:afterSwap', function(e) {
        // Re-initialize touch gestures for any grids in the updated content
        const grids = e.detail.target.querySelectorAll('[id$="-grid"]');
        grids.forEach(grid => {
            const gridId = grid.id;
            const entityType = gridId.replace('-grid', '').replace('-', '_');

            setTimeout(() => {
                GridTouchGestures.initForEntityType(gridId, entityType);
            }, 100);
        });
    });

})();
