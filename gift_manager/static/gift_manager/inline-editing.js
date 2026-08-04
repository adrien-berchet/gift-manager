/**
 * Inline Editing Functionality
 * Provides double-click to edit functionality for simple fields in Grid.js tables
 */

(function (window) {
    'use strict';

    /**
     * Configuration for inline editing
     */
    const INLINE_EDITING_CONFIG = {
        // Entity types and their editable fields
        entities: {
            'person': {
                fields: ['first_name', 'family_name', 'email_address'],
                urlPattern: '/api/persons/{id}/inline-update/'
            },
            'gift': {
                fields: ['name', 'comment'],
                urlPattern: '/api/gifts/{id}/inline-update/'
            },
            'event': {
                fields: ['name', 'comment'],
                urlPattern: '/api/events/{id}/inline-update/'
            },
            'person_group': {
                fields: ['name', 'comment'],
                urlPattern: '/api/person-groups/{id}/inline-update/'
            },
            'gift_tag': {
                fields: ['name'],
                urlPattern: '/api/gift-tags/{id}/inline-update/'
            },
            'relation': {
                fields: ['comment'],
                urlPattern: '/api/relations/{id}/inline-update/'
            }
        },

        // CSS classes
        classes: {
            editableCell: 'inline-editable',
            editing: 'inline-editing',
            input: 'inline-edit-input',
            saving: 'inline-saving',
            success: 'inline-success',
            error: 'inline-error'
        },

        // Timeouts
        feedbackTimeout: 2000,
        savingTimeout: 5000
    };

    /**
     * Initialize inline editing for a grid
     * @param {string} gridId - The ID of the grid container
     * @param {string} entityType - The type of entity (person, gift, etc.)
     * @param {Object} columnMapping - Mapping of column indices to field names
     */
    function initInlineEditing(gridId, entityType, columnMapping) {
        const config = INLINE_EDITING_CONFIG.entities[entityType];
        if (!config) {
            console.warn(`[InlineEditing] Unknown entity type: ${entityType}`);
            return;
        }

        // Wait for grid to be rendered, then mark cells immediately
        setTimeout(() => {
            setupInlineEditingListeners(gridId, entityType, columnMapping);

            // Force a second pass to ensure all cells are marked
            setTimeout(() => {
                const gridContainer = document.getElementById(gridId);
                if (gridContainer) {
                    markEditableCellsImmediate(gridContainer, entityType, columnMapping);
                }
            }, 100);
        }, 200);
    }

    /**
     * Setup event listeners for inline editing
     */
    function setupInlineEditingListeners(gridId, entityType, columnMapping) {
        const gridContainer = document.getElementById(gridId);
        if (!gridContainer) {
            console.warn(`[InlineEditing] Grid container not found: ${gridId}`);
            return;
        }

        // Add double-click listeners to editable cells
        gridContainer.addEventListener('dblclick', function(event) {
            const cell = event.target.closest('td');
            if (!cell) {
                return;
            }

            const row = cell.closest('tr');
            if (!row) {
                return;
            }

            // Get column index and check if it's editable
            const columnIndex = Array.from(cell.parentNode.children).indexOf(cell);
            const fieldName = columnMapping[columnIndex];

            if (!fieldName || !INLINE_EDITING_CONFIG.entities[entityType].fields.includes(fieldName)) {
                return;
            }

            // Get entity ID from the row
            const entityId = getEntityIdFromRow(row, entityType);

            if (!entityId) {
                console.warn('[InlineEditing] Could not find entity ID in row');
                return;
            }

            // Start inline editing
            startInlineEdit(cell, fieldName, entityId, entityType);
        });

        // Mark editable cells immediately and set up observer for future changes
        markEditableCellsImmediate(gridContainer, entityType, columnMapping);
        setupMutationObserver(gridContainer, entityType, columnMapping);
    }

    /**
     * Mark existing editable cells immediately (synchronous)
     */
    function markEditableCellsImmediate(gridContainer, entityType, columnMapping) {
        const config = INLINE_EDITING_CONFIG.entities[entityType];
        const existingRows = gridContainer.querySelectorAll('tr');
        existingRows.forEach(row => markRowCellsEditable(row, config, columnMapping));
    }

    /**
     * Set up MutationObserver for dynamically added rows
     */
    function setupMutationObserver(gridContainer, entityType, columnMapping) {
        const config = INLINE_EDITING_CONFIG.entities[entityType];

        // Use MutationObserver to handle dynamically added rows
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        const rows = node.querySelectorAll ? node.querySelectorAll('tr') : [];
                        rows.forEach(row => markRowCellsEditable(row, config, columnMapping));

                        // Also check if the node itself is a row
                        if (node.tagName === 'TR') {
                            markRowCellsEditable(node, config, columnMapping);
                        }
                    }
                });
            });
        });

        observer.observe(gridContainer, { childList: true, subtree: true });
    }

    /**
     * Mark cells in a row as editable
     */
    function markRowCellsEditable(row, config, columnMapping) {
        const cells = row.querySelectorAll('td');

        cells.forEach((cell, index) => {
            const fieldName = columnMapping[index];
            if (fieldName && config.fields.includes(fieldName)) {
                cell.classList.add(INLINE_EDITING_CONFIG.classes.editableCell);
                cell.title = 'Double-click to edit';
            }
        });
    }

    /**
     * Get entity ID from a table row
     */
    function getEntityIdFromRow(row, entityType) {
        // Try data attributes first (most reliable)
        const entityId = row.dataset.entityId || row.dataset.personId || row.dataset.id;
        if (entityId) {
            return entityId;
        }

        // Look for hidden ID cell or data attribute
        const cells = row.querySelectorAll('td');

        // For person entities, the ID should be in column index 4 (5th column)
        if (entityType === 'person' && cells.length > 4) {
            const idCell = cells[4];
            const text = idCell.textContent.trim();

            // Check if it looks like a UUID
            if (text.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)) {
                return text;
            }
        }

        // Try to find ID in hidden columns (usually towards the end)
        for (let i = cells.length - 1; i >= 0; i--) {
            const cell = cells[i];
            const text = cell.textContent.trim();

            // Check if it looks like a UUID
            if (text.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)) {
                return text;
            }
        }

        return null;
    }

    /**
     * Start inline editing for a cell
     */
    function startInlineEdit(cell, fieldName, entityId, entityType) {
        // Prevent multiple edits on the same cell
        if (cell.classList.contains(INLINE_EDITING_CONFIG.classes.editing)) {
            return;
        }

        const originalValue = cell.textContent.trim();
        const originalHTML = cell.innerHTML;
        let isSaving = false; // Flag to prevent multiple saves
        let isCancelled = false; // Prevent blur from saving after Escape

        // Create input element
        const input = document.createElement('input');
        input.type = 'text';
        input.value = originalValue;
        input.className = INLINE_EDITING_CONFIG.classes.input;

        // Style the input to fit naturally in the cell
        input.style.width = '100%';
        input.style.border = 'none';
        input.style.background = 'transparent';
        input.style.font = 'inherit';
        input.style.outline = 'none';
        input.style.margin = '0';
        input.style.padding = '0';
        input.style.boxSizing = 'border-box';

        // Mark cell as being edited
        cell.classList.add(INLINE_EDITING_CONFIG.classes.editing);
        cell.innerHTML = '';
        cell.appendChild(input);

        // Focus and select the input
        input.focus();
        input.select();

        // Handle save on Enter or blur
        const saveEdit = () => {
            if (isCancelled) return;
            if (isSaving) return; // Prevent multiple saves

            const newValue = input.value.trim();

            if (newValue === originalValue) {
                // No change, just restore
                cancelEdit();
                return;
            }

            isSaving = true; // Set flag to prevent multiple saves
            // Save the change
            saveInlineEdit(cell, fieldName, entityId, entityType, originalValue, newValue, originalHTML);
        };

        // Handle cancel on Escape
        const cancelEdit = () => {
            if (isSaving) return; // Don't cancel if already saving

            isCancelled = true;
            cell.classList.remove(INLINE_EDITING_CONFIG.classes.editing);
            cell.innerHTML = originalHTML;
        };

        // Event listeners
        input.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                saveEdit();
            } else if (event.key === 'Escape') {
                event.preventDefault();
                cancelEdit();
            }
        });

        input.addEventListener('blur', function() {
            // Small delay to prevent race condition with keydown
            setTimeout(() => {
                if (!isCancelled) saveEdit();
            }, 10);
        });
    }

    /**
     * Save inline edit via AJAX
     */
    function saveInlineEdit(cell, fieldName, entityId, entityType, oldValue, newValue, originalHTML) {
        const config = INLINE_EDITING_CONFIG.entities[entityType];

        // Get current language from URL or document
        const lang = document.documentElement.lang?.split('-')[0] ||
                    window.location.pathname.match(/^\/(en|fr)\//)?.[1] ||
                    'en';

        // Build URL with language prefix
        const url = `/${lang}${config.urlPattern.replace('{id}', entityId)}`;

        // Show saving state
        cell.classList.add(INLINE_EDITING_CONFIG.classes.saving);
        cell.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>${newValue}`;

        // Prepare data
        const data = {
            field: fieldName,
            value: newValue
        };

        // Make AJAX request
        fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            cell.classList.remove(INLINE_EDITING_CONFIG.classes.saving, INLINE_EDITING_CONFIG.classes.editing);

            if (data.success) {
                // Show success state
                cell.textContent = newValue;
                cell.classList.add(INLINE_EDITING_CONFIG.classes.success);

                // Show success notification
                showNotification(data.message || 'Field updated successfully', 'success');

                document.dispatchEvent(new CustomEvent('inline-edit:success', {
                    detail: {
                        entityType: entityType,
                        entityId: entityId,
                        fieldName: fieldName,
                        oldValue: oldValue,
                        newValue: newValue
                    }
                }));

                // Remove success class after timeout
                setTimeout(() => {
                    cell.classList.remove(INLINE_EDITING_CONFIG.classes.success);
                }, INLINE_EDITING_CONFIG.feedbackTimeout);

            } else {
                // Show error state
                cell.classList.add(INLINE_EDITING_CONFIG.classes.error);
                cell.innerHTML = originalHTML;

                // Show error notification
                showNotification(data.error || 'Failed to update field', 'error');

                // Remove error class after timeout
                setTimeout(() => {
                    cell.classList.remove(INLINE_EDITING_CONFIG.classes.error);
                }, INLINE_EDITING_CONFIG.feedbackTimeout);
            }
        })
        .catch(error => {
            console.error('[InlineEditing] Save error:', error);

            cell.classList.remove(INLINE_EDITING_CONFIG.classes.saving, INLINE_EDITING_CONFIG.classes.editing);
            cell.classList.add(INLINE_EDITING_CONFIG.classes.error);
            cell.innerHTML = originalHTML;

            showNotification('Network error occurred while saving', 'error');

            setTimeout(() => {
                cell.classList.remove(INLINE_EDITING_CONFIG.classes.error);
            }, INLINE_EDITING_CONFIG.feedbackTimeout);
        });
    }

    /**
     * Get CSRF token from cookies or meta tag
     */
    function getCsrfToken() {
        // Try to get from meta tag first
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }

        // Try to get from cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }

        return '';
    }

    /**
     * Show notification (integrates with existing notification system)
     */
    function showNotification(message, type) {
        // Try to use existing notification system
        if (window.showNotification && typeof window.showNotification === 'function') {
            window.showNotification(message, type);
            return;
        }

        // Fallback: create simple notification
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'error' ? 'danger' : 'success'} alert-dismissible fade show position-fixed`;
        notification.style.top = '20px';
        notification.style.right = '20px';
        notification.style.zIndex = '9999';
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(notification);

        // Auto-remove after timeout
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, INLINE_EDITING_CONFIG.feedbackTimeout);
    }

    // Expose to global scope
    window.InlineEditing = {
        init: initInlineEditing,
        config: INLINE_EDITING_CONFIG
    };

})(window);
