/**
 * Touch Gestures Implementation for Modern UX Interface
 * Provides swipe gestures for delete, archive, and other actions
 */

(function() {
    'use strict';

    const TouchGestures = {
        // Configuration
        config: {
            swipeThreshold: 80,        // Minimum distance for swipe
            swipeTimeout: 300,         // Maximum time for swipe
            longPressTimeout: 500,     // Time for long press
            doubleTapTimeout: 300,     // Time between taps for double tap
            velocityThreshold: 0.3,    // Minimum velocity for swipe
        },

        // State tracking
        state: {
            startX: 0,
            startY: 0,
            startTime: 0,
            lastTap: 0,
            isTracking: false,
            element: null,
            swipeDirection: null,
            longPressTimer: null,
        },

        init: function() {
            if (!this.isTouchDevice()) return;

            this.setupEventListeners();
            this.setupSwipeableElements();
            this.setupLongPressElements();
        },

        isTouchDevice: function() {
            return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
        },

        setupEventListeners: function() {
            // Use passive listeners for better performance
            document.addEventListener('touchstart', this.handleTouchStart.bind(this), { passive: false });
            document.addEventListener('touchmove', this.handleTouchMove.bind(this), { passive: false });
            document.addEventListener('touchend', this.handleTouchEnd.bind(this), { passive: false });
            document.addEventListener('touchcancel', this.handleTouchCancel.bind(this), { passive: true });
        },

        setupSwipeableElements: function() {
            // Add swipe indicators to list items
            const listItems = document.querySelectorAll('.list-group-item, .table-row, [data-swipeable]');
            listItems.forEach(item => {
                if (!item.dataset.swipeSetup) {
                    this.makeElementSwipeable(item);
                    item.dataset.swipeSetup = 'true';
                }
            });

            // Re-setup after HTMX updates
            document.body.addEventListener('htmx:afterSwap', () => {
                setTimeout(() => this.setupSwipeableElements(), 100);
            });
        },

        setupLongPressElements: function() {
            // Setup long press for context menus
            const longPressElements = document.querySelectorAll('[data-long-press]');
            longPressElements.forEach(element => {
                if (!element.dataset.longPressSetup) {
                    element.dataset.longPressSetup = 'true';
                }
            });
        },

        makeElementSwipeable: function(element) {
            // Add swipe action buttons if they don't exist
            if (!element.querySelector('.swipe-actions')) {
                this.addSwipeActions(element);
            }

            // Add visual indicators
            element.classList.add('swipeable-item');
        },

        addSwipeActions: function(element) {
            const actions = this.getSwipeActionsForElement(element);
            if (actions.length === 0) return;

            const swipeContainer = document.createElement('div');
            swipeContainer.className = 'swipe-actions';

            const leftActions = document.createElement('div');
            leftActions.className = 'swipe-actions-left';

            const rightActions = document.createElement('div');
            rightActions.className = 'swipe-actions-right';

            actions.forEach(action => {
                const button = document.createElement('button');
                button.className = `swipe-action-btn swipe-action-${action.type}`;
                button.innerHTML = `<i class="${action.icon}"></i>`;
                button.title = action.title;
                button.dataset.action = action.action;
                button.dataset.url = action.url || '';

                if (action.side === 'left') {
                    leftActions.appendChild(button);
                } else {
                    rightActions.appendChild(button);
                }
            });

            swipeContainer.appendChild(leftActions);
            swipeContainer.appendChild(rightActions);

            // Insert swipe actions
            element.style.position = 'relative';
            element.appendChild(swipeContainer);
        },

        getSwipeActionsForElement: function(element) {
            const actions = [];

            // Check for data attributes that define available actions
            if (element.dataset.deleteUrl) {
                actions.push({
                    type: 'delete',
                    action: 'delete',
                    icon: 'fas fa-trash',
                    title: 'Delete',
                    url: element.dataset.deleteUrl,
                    side: 'right'
                });
            }

            if (element.dataset.archiveUrl) {
                actions.push({
                    type: 'archive',
                    action: 'archive',
                    icon: 'fas fa-archive',
                    title: 'Archive',
                    url: element.dataset.archiveUrl,
                    side: 'right'
                });
            }

            if (element.dataset.editUrl) {
                actions.push({
                    type: 'edit',
                    action: 'edit',
                    icon: 'fas fa-edit',
                    title: 'Edit',
                    url: element.dataset.editUrl,
                    side: 'left'
                });
            }

            if (element.dataset.shareUrl) {
                actions.push({
                    type: 'share',
                    action: 'share',
                    icon: 'fas fa-share',
                    title: 'Share',
                    url: element.dataset.shareUrl,
                    side: 'left'
                });
            }

            return actions;
        },

        handleTouchStart: function(e) {
            const touch = e.touches[0];
            const element = this.findSwipeableElement(e.target);

            if (!element) return;

            this.state.startX = touch.clientX;
            this.state.startY = touch.clientY;
            this.state.startTime = Date.now();
            this.state.isTracking = true;
            this.state.element = element;
            this.state.swipeDirection = null;

            // Clear any existing long press timer
            if (this.state.longPressTimer) {
                clearTimeout(this.state.longPressTimer);
            }

            // Start long press timer if element supports it
            if (element.dataset.longPress) {
                this.state.longPressTimer = setTimeout(() => {
                    this.handleLongPress(element, touch.clientX, touch.clientY);
                }, this.config.longPressTimeout);
            }

            // Add visual feedback
            element.classList.add('touch-tracking');
        },

        handleTouchMove: function(e) {
            if (!this.state.isTracking) return;

            const touch = e.touches[0];
            const deltaX = touch.clientX - this.state.startX;
            const deltaY = touch.clientY - this.state.startY;

            // Clear long press if user moves too much
            if (Math.abs(deltaX) > 10 || Math.abs(deltaY) > 10) {
                if (this.state.longPressTimer) {
                    clearTimeout(this.state.longPressTimer);
                    this.state.longPressTimer = null;
                }
            }

            // Determine swipe direction
            if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 20) {
                this.state.swipeDirection = deltaX > 0 ? 'right' : 'left';

                // Prevent vertical scrolling during horizontal swipe
                e.preventDefault();

                // Apply visual feedback
                this.updateSwipeVisual(this.state.element, deltaX);
            }
        },

        handleTouchEnd: function(e) {
            if (!this.state.isTracking) return;

            const touch = e.changedTouches[0];
            const deltaX = touch.clientX - this.state.startX;
            const deltaY = touch.clientY - this.state.startY;
            const deltaTime = Date.now() - this.state.startTime;
            const velocity = Math.abs(deltaX) / deltaTime;

            // Clear long press timer
            if (this.state.longPressTimer) {
                clearTimeout(this.state.longPressTimer);
                this.state.longPressTimer = null;
            }

            // Check for double tap
            const now = Date.now();
            if (now - this.state.lastTap < this.config.doubleTapTimeout) {
                this.handleDoubleTap(this.state.element);
                this.state.lastTap = 0;
            } else {
                this.state.lastTap = now;
            }

            // Process swipe gesture
            if (Math.abs(deltaX) > this.config.swipeThreshold &&
                deltaTime < this.config.swipeTimeout &&
                velocity > this.config.velocityThreshold) {

                this.handleSwipe(this.state.element, this.state.swipeDirection, Math.abs(deltaX));
            } else {
                // Reset visual state if swipe wasn't completed
                this.resetSwipeVisual(this.state.element);
            }

            // Clean up state
            this.state.element.classList.remove('touch-tracking');
            this.resetState();
        },

        handleTouchCancel: function(e) {
            if (!this.state.isTracking) return;

            // Clear long press timer
            if (this.state.longPressTimer) {
                clearTimeout(this.state.longPressTimer);
                this.state.longPressTimer = null;
            }

            // Reset visual state
            if (this.state.element) {
                this.resetSwipeVisual(this.state.element);
                this.state.element.classList.remove('touch-tracking');
            }

            this.resetState();
        },

        findSwipeableElement: function(target) {
            return target.closest('.swipeable-item, [data-swipeable], .list-group-item, .table-row');
        },

        updateSwipeVisual: function(element, deltaX) {
            const maxSwipe = 120;
            const clampedDelta = Math.max(-maxSwipe, Math.min(maxSwipe, deltaX));
            const opacity = Math.abs(clampedDelta) / maxSwipe;

            element.style.transform = `translateX(${clampedDelta}px)`;

            const swipeActions = element.querySelector('.swipe-actions');
            if (swipeActions) {
                swipeActions.style.opacity = opacity;

                // Show appropriate actions based on swipe direction
                const leftActions = swipeActions.querySelector('.swipe-actions-left');
                const rightActions = swipeActions.querySelector('.swipe-actions-right');

                if (deltaX > 0 && leftActions) {
                    leftActions.style.transform = 'translateX(0)';
                    rightActions.style.transform = 'translateX(100%)';
                } else if (deltaX < 0 && rightActions) {
                    rightActions.style.transform = 'translateX(0)';
                    leftActions.style.transform = 'translateX(-100%)';
                }
            }
        },

        resetSwipeVisual: function(element) {
            if (!element) return;

            element.style.transform = '';

            const swipeActions = element.querySelector('.swipe-actions');
            if (swipeActions) {
                swipeActions.style.opacity = '';

                const leftActions = swipeActions.querySelector('.swipe-actions-left');
                const rightActions = swipeActions.querySelector('.swipe-actions-right');

                if (leftActions) leftActions.style.transform = '';
                if (rightActions) rightActions.style.transform = '';
            }
        },

        handleSwipe: function(element, direction, distance) {
            const swipeActions = element.querySelector('.swipe-actions');
            if (!swipeActions) return;

            const actionsContainer = direction === 'right' ?
                swipeActions.querySelector('.swipe-actions-left') :
                swipeActions.querySelector('.swipe-actions-right');

            if (!actionsContainer) {
                this.resetSwipeVisual(element);
                return;
            }

            const actions = actionsContainer.querySelectorAll('.swipe-action-btn');
            if (actions.length === 0) {
                this.resetSwipeVisual(element);
                return;
            }

            // If swipe is far enough, trigger the primary action
            if (distance > this.config.swipeThreshold * 1.5) {
                const primaryAction = actions[0];
                this.executeSwipeAction(primaryAction, element);
            } else {
                // Show actions for user to tap
                this.showSwipeActions(element, direction);
            }
        },

        showSwipeActions: function(element, direction) {
            element.classList.add('swipe-actions-visible');

            // Auto-hide after a delay
            setTimeout(() => {
                if (element.classList.contains('swipe-actions-visible')) {
                    this.hideSwipeActions(element);
                }
            }, 3000);

            // Setup action button handlers
            const swipeActions = element.querySelector('.swipe-actions');
            const actionButtons = swipeActions.querySelectorAll('.swipe-action-btn');

            actionButtons.forEach(button => {
                button.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.executeSwipeAction(button, element);
                });
            });
        },

        hideSwipeActions: function(element) {
            element.classList.remove('swipe-actions-visible');
            this.resetSwipeVisual(element);
        },

        executeSwipeAction: function(actionButton, element) {
            const action = actionButton.dataset.action;
            const url = actionButton.dataset.url;

            // Add loading state
            actionButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            actionButton.disabled = true;

            // Execute action based on type
            switch (action) {
                case 'delete':
                    this.handleDeleteAction(url, element);
                    break;
                case 'archive':
                    this.handleArchiveAction(url, element);
                    break;
                case 'edit':
                    this.handleEditAction(url, element);
                    break;
                case 'share':
                    this.handleShareAction(url, element);
                    break;
                default:
                    console.warn('Unknown swipe action:', action);
                    this.hideSwipeActions(element);
            }
        },

        handleDeleteAction: function(url, element) {
            // Show confirmation modal
            if (url) {
                fetch(url, {
                    headers: {
                        'HX-Request': 'true',
                        'X-CSRFToken': this.getCsrfToken()
                    }
                })
                .then(response => response.text())
                .then(html => {
                    document.getElementById('modalBody').innerHTML = html;
                    const modal = new bootstrap.Modal(document.getElementById('confirmModal'));
                    modal.show();
                    this.hideSwipeActions(element);
                })
                .catch(error => {
                    console.error('Error loading delete confirmation:', error);
                    this.showNotification('Error loading confirmation', 'error');
                    this.hideSwipeActions(element);
                });
            }
        },

        handleArchiveAction: function(url, element) {
            // Implement archive functionality
            if (url) {
                fetch(url, {
                    method: 'POST',
                    headers: {
                        'HX-Request': 'true',
                        'X-CSRFToken': this.getCsrfToken()
                    }
                })
                .then(response => {
                    if (response.ok) {
                        element.style.opacity = '0.5';
                        element.classList.add('archived');
                        this.showNotification('Item archived', 'success');
                    } else {
                        throw new Error('Archive failed');
                    }
                })
                .catch(error => {
                    console.error('Error archiving item:', error);
                    this.showNotification('Error archiving item', 'error');
                })
                .finally(() => {
                    this.hideSwipeActions(element);
                });
            }
        },

        handleEditAction: function(url, element) {
            // Open edit panel
            if (url) {
                const editButton = element.querySelector('[data-action="edit"]');
                if (editButton) {
                    editButton.click();
                } else {
                    // Fallback: navigate to edit URL
                    window.location.href = url;
                }
                this.hideSwipeActions(element);
            }
        },

        handleShareAction: function(url, element) {
            // Open share panel or use Web Share API
            if (navigator.share && url) {
                navigator.share({
                    title: 'Share Item',
                    url: url
                }).then(() => {
                    this.showNotification('Shared successfully', 'success');
                }).catch(error => {
                    console.error('Error sharing:', error);
                });
            } else if (url) {
                // Fallback: open share panel
                const shareButton = element.querySelector('[data-action="share"]');
                if (shareButton) {
                    shareButton.click();
                }
            }
            this.hideSwipeActions(element);
        },

        handleLongPress: function(element, x, y) {
            // Show context menu
            const contextMenu = this.createContextMenu(element);
            if (contextMenu) {
                this.showContextMenu(contextMenu, x, y);
            }

            // Haptic feedback if available
            if (navigator.vibrate) {
                navigator.vibrate(50);
            }
        },

        handleDoubleTap: function(element) {
            // Default double tap action (usually edit or detail view)
            const editButton = element.querySelector('[data-action="edit"]');
            const detailButton = element.querySelector('[data-action="detail"]');

            if (editButton) {
                editButton.click();
            } else if (detailButton) {
                detailButton.click();
            }
        },

        createContextMenu: function(element) {
            // Create context menu based on available actions
            const actions = this.getSwipeActionsForElement(element);
            if (actions.length === 0) return null;

            const menu = document.createElement('div');
            menu.className = 'touch-context-menu';

            actions.forEach(action => {
                const item = document.createElement('button');
                item.className = 'context-menu-item';
                item.innerHTML = `<i class="${action.icon}"></i> ${action.title}`;
                item.dataset.action = action.action;
                item.dataset.url = action.url;

                item.addEventListener('click', () => {
                    this.executeSwipeAction(item, element);
                    this.hideContextMenu();
                });

                menu.appendChild(item);
            });

            return menu;
        },

        showContextMenu: function(menu, x, y) {
            // Remove any existing context menu
            this.hideContextMenu();

            document.body.appendChild(menu);

            // Position menu
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';

            // Adjust position if menu goes off screen
            const rect = menu.getBoundingClientRect();
            if (rect.right > window.innerWidth) {
                menu.style.left = (x - rect.width) + 'px';
            }
            if (rect.bottom > window.innerHeight) {
                menu.style.top = (y - rect.height) + 'px';
            }

            menu.classList.add('show');

            // Hide menu when clicking outside
            setTimeout(() => {
                document.addEventListener('click', this.hideContextMenu.bind(this), { once: true });
            }, 100);
        },

        hideContextMenu: function() {
            const existingMenu = document.querySelector('.touch-context-menu');
            if (existingMenu) {
                existingMenu.remove();
            }
        },

        resetState: function() {
            this.state.startX = 0;
            this.state.startY = 0;
            this.state.startTime = 0;
            this.state.isTracking = false;
            this.state.element = null;
            this.state.swipeDirection = null;
        },

        getCsrfToken: function() {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrftoken') {
                    return decodeURIComponent(value);
                }
            }
            return '';
        },

        showNotification: function(message, type) {
            if (window.showNotification) {
                window.showNotification(message, type);
            } else {
                console.log(`${type.toUpperCase()}: ${message}`);
            }
        }
    };

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => TouchGestures.init());
    } else {
        TouchGestures.init();
    }

    // Expose to global scope
    window.TouchGestures = TouchGestures;

})();
