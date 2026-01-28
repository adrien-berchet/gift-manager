/**
 * Detail Views JavaScript for Modern UX Interface
 * Handles detail view buttons and panel interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    // Handle detail view buttons
    document.addEventListener('click', function(e) {
        const detailButton = e.target.closest('[data-action="detail"]');
        if (detailButton) {
            e.preventDefault();
            handleDetailView(detailButton);
        }
    });

    /**
     * Handle detail view button clicks
     * @param {HTMLElement} button - The detail button that was clicked
     */
    function handleDetailView(button) {
        const detailUrl = button.dataset.detailUrl;
        if (!detailUrl) {
            console.error('Detail button missing data-detail-url attribute');
            return;
        }

        // Show loading state
        showOffcanvasLoading('detailPanel');

        // Show the detail panel
        const detailPanel = document.getElementById('detailPanel');
        if (detailPanel) {
            const offcanvasInstance = new bootstrap.Offcanvas(detailPanel);
            offcanvasInstance.show();
        }

        // Load detail content via HTMX
        htmx.ajax('GET', detailUrl, {
            target: '#detailContent',
            swap: 'innerHTML',
            headers: {
                'HX-Request': 'true'
            }
        }).then(function() {
            hideOffcanvasLoading('detailPanel');
        }).catch(function(error) {
            console.error('Failed to load detail view:', error);
            showOffcanvasError('Failed to load details. Please try again.', 'detailPanel');
        });
    }

    /**
     * Handle action buttons within detail views
     */
    document.addEventListener('click', function(e) {
        const actionButton = e.target.closest('.detail-content [data-action]');
        if (actionButton) {
            const action = actionButton.dataset.action;

            switch (action) {
                case 'edit':
                    handleEditFromDetail(actionButton);
                    break;
                case 'delete':
                    handleDeleteFromDetail(actionButton);
                    break;
                default:
                    // Let other handlers deal with it
                    break;
            }
        }
    });

    /**
     * Handle edit button clicks from within detail views
     * @param {HTMLElement} button - The edit button that was clicked
     */
    function handleEditFromDetail(button) {
        const editUrl = button.dataset.editUrl;
        if (!editUrl) {
            console.error('Edit button missing data-edit-url attribute');
            return;
        }

        // Close detail panel
        const detailPanel = document.getElementById('detailPanel');
        if (detailPanel) {
            const detailOffcanvas = bootstrap.Offcanvas.getInstance(detailPanel);
            if (detailOffcanvas) {
                detailOffcanvas.hide();
            }
        }

        // Show edit panel with loading state
        showOffcanvasLoading('editPanel');
        const editPanel = document.getElementById('editPanel');
        if (editPanel) {
            const editOffcanvas = new bootstrap.Offcanvas(editPanel);
            editOffcanvas.show();
        }

        // Load edit form via HTMX
        htmx.ajax('GET', editUrl, {
            target: '#offcanvasContent',
            swap: 'innerHTML',
            headers: {
                'HX-Request': 'true'
            }
        }).then(function() {
            hideOffcanvasLoading('editPanel');
        }).catch(function(error) {
            console.error('Failed to load edit form:', error);
            showOffcanvasError('Failed to load edit form. Please try again.', 'editPanel');
        });
    }

    /**
     * Handle delete button clicks from within detail views
     * @param {HTMLElement} button - The delete button that was clicked
     */
    function handleDeleteFromDetail(button) {
        const deleteUrl = button.dataset.deleteUrl;
        if (!deleteUrl) {
            console.error('Delete button missing data-delete-url attribute');
            return;
        }

        // Close detail panel first
        const detailPanel = document.getElementById('detailPanel');
        if (detailPanel) {
            const detailOffcanvas = bootstrap.Offcanvas.getInstance(detailPanel);
            if (detailOffcanvas) {
                detailOffcanvas.hide();
            }
        }

        // Show delete confirmation modal
        const confirmModal = document.getElementById('confirmModal');
        if (confirmModal) {
            // Load delete confirmation content
            htmx.ajax('GET', deleteUrl, {
                target: '#confirmModal .modal-body',
                swap: 'innerHTML',
                headers: {
                    'HX-Request': 'true'
                }
            }).then(function() {
                const modalInstance = new bootstrap.Modal(confirmModal);
                modalInstance.show();
            }).catch(function(error) {
                console.error('Failed to load delete confirmation:', error);
                showNotification('Failed to load delete confirmation. Please try again.', 'error');
            });
        }
    }

    /**
     * Handle expandable row functionality
     */
    document.addEventListener('click', function(e) {
        const expandButton = e.target.closest('[data-action="expand"]');
        if (expandButton) {
            e.preventDefault();
            handleExpandableRow(expandButton);
        }
    });

    /**
     * Handle expandable row toggle
     * @param {HTMLElement} button - The expand button that was clicked
     */
    function handleExpandableRow(button) {
        const row = button.closest('.expandable-row');
        if (!row) return;

        const detailsContainer = row.querySelector('.expandable-details');
        if (!detailsContainer) return;

        const isExpanded = detailsContainer.style.display !== 'none';

        if (isExpanded) {
            // Collapse
            detailsContainer.style.display = 'none';
            button.innerHTML = '<i class="fas fa-chevron-down"></i>';
            button.setAttribute('aria-expanded', 'false');
            row.classList.remove('expanded');
        } else {
            // Expand
            const detailUrl = button.dataset.detailUrl;
            if (!detailUrl) {
                console.error('Expand button missing data-detail-url attribute');
                return;
            }

            // Check if content is already loaded
            if (!detailsContainer.getAttribute('data-loaded')) {
                detailsContainer.innerHTML = '<div class="text-center p-3"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';

                htmx.ajax('GET', detailUrl, {
                    target: detailsContainer,
                    swap: 'innerHTML',
                    headers: {
                        'HX-Request': 'true'
                    }
                }).then(function() {
                    detailsContainer.setAttribute('data-loaded', 'true');
                }).catch(function(error) {
                    console.error('Failed to load expandable content:', error);
                    detailsContainer.innerHTML = '<div class="text-center p-3 text-danger"><i class="fas fa-exclamation-triangle"></i> Failed to load content</div>';
                });
            }

            detailsContainer.style.display = 'block';
            button.innerHTML = '<i class="fas fa-chevron-up"></i>';
            button.setAttribute('aria-expanded', 'true');
            row.classList.add('expanded');
        }
    }

    /**
     * Handle keyboard navigation in detail views
     */
    document.addEventListener('keydown', function(e) {
        // Only handle if a detail panel is open
        const openDetailPanel = document.querySelector('.offcanvas.show#detailPanel');
        if (!openDetailPanel) return;

        switch (e.key) {
            case 'e':
            case 'E':
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    const editButton = openDetailPanel.querySelector('[data-action="edit"]');
                    if (editButton && !editButton.disabled) {
                        editButton.click();
                    }
                }
                break;
            case 'Delete':
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    const deleteButton = openDetailPanel.querySelector('[data-action="delete"]');
                    if (deleteButton && !deleteButton.disabled) {
                        deleteButton.click();
                    }
                }
                break;
        }
    });

    /**
     * Auto-refresh detail views when list updates
     */
    document.addEventListener('list:update', function() {
        const openDetailPanel = document.querySelector('.offcanvas.show#detailPanel');
        if (openDetailPanel) {
            // Find the current detail URL and refresh
            const currentUrl = openDetailPanel.dataset.currentUrl;
            if (currentUrl) {
                htmx.ajax('GET', currentUrl, {
                    target: '#detailContent',
                    swap: 'innerHTML',
                    headers: {
                        'HX-Request': 'true'
                    }
                }).catch(function(error) {
                    console.error('Failed to refresh detail view:', error);
                });
            }
        }
    });

    /**
     * Store current detail URL for refresh purposes
     */
    document.addEventListener('htmx:beforeRequest', function(e) {
        if (e.detail.target && e.detail.target.id === 'detailContent') {
            const detailPanel = document.getElementById('detailPanel');
            if (detailPanel) {
                detailPanel.dataset.currentUrl = e.detail.requestConfig.url;
            }
        }
    });

    /**
     * Handle smooth animations for expandable content
     */
    function animateExpand(element) {
        element.style.height = '0px';
        element.style.overflow = 'hidden';
        element.style.transition = 'height 0.3s ease-out';

        // Force reflow
        element.offsetHeight;

        element.style.height = element.scrollHeight + 'px';

        element.addEventListener('transitionend', function handler() {
            element.style.height = 'auto';
            element.style.overflow = 'visible';
            element.removeEventListener('transitionend', handler);
        });
    }

    function animateCollapse(element) {
        element.style.height = element.scrollHeight + 'px';
        element.style.overflow = 'hidden';
        element.style.transition = 'height 0.3s ease-out';

        // Force reflow
        element.offsetHeight;

        element.style.height = '0px';

        element.addEventListener('transitionend', function handler() {
            element.style.display = 'none';
            element.style.height = 'auto';
            element.style.overflow = 'visible';
            element.removeEventListener('transitionend', handler);
        });
    }

    /**
     * Initialize detail view enhancements
     */
    function initializeDetailViews() {
        // Add expand buttons to expandable rows
        const expandableRows = document.querySelectorAll('.expandable-row');
        expandableRows.forEach(row => {
            const expandButton = row.querySelector('[data-action="expand"]');
            if (expandButton) {
                expandButton.setAttribute('aria-expanded', 'false');
                expandButton.setAttribute('title', 'Click to expand details');
            }
        });

        // Initialize tooltips for action buttons
        const tooltipElements = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltipElements.forEach(element => {
            new bootstrap.Tooltip(element);
        });
    }

    // Initialize on page load
    initializeDetailViews();

    // Re-initialize after HTMX content swaps
    document.addEventListener('htmx:afterSwap', function() {
        initializeDetailViews();
    });
});
