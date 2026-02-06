/**
 * Form Initializer - Centralized system for initializing forms after HTMX swaps
 *
 * This module provides a robust system for initializing form elements after they are
 * dynamically loaded via HTMX. It prevents duplicate initialization and provides
 * a clean API for registering custom initializers.
 *
 * @module FormInitializer
 */
(function(window) {
  'use strict';

  const FormInitializer = {
    // Track initialized forms to prevent duplicates
    initializedForms: new WeakSet(),

    // Registry of initialization functions
    initializers: {},

    /**
     * Register an initialization function
     * @param {string} name - Unique name for the initializer
     * @param {Function} fn - Initialization function that receives the form element
     */
    register: function(name, fn) {
      if (typeof fn !== 'function') {
        console.error(`[FormInitializer] Cannot register ${name}: not a function`);
        return;
      }

      this.initializers[name] = fn;
      console.log(`[FormInitializer] Registered: ${name}`);
    },

    /**
     * Initialize a form element
     * @param {HTMLElement} form - The form element to initialize
     */
    initForm: function(form) {
      if (!form) {
        console.warn('[FormInitializer] No form element provided');
        return;
      }

      // Check if already initialized
      if (this.initializedForms.has(form)) {
        console.log('[FormInitializer] Form already initialized, skipping');
        return;
      }

      const formType = form.dataset.formType || 'unknown';
      console.log(`[FormInitializer] Initializing form: ${formType}`);

      // Mark as initialized
      this.initializedForms.add(form);

      // Run all registered initializers
      Object.keys(this.initializers).forEach(name => {
        try {
          this.initializers[name](form);
        } catch (error) {
          console.error(`[FormInitializer] Error in ${name}:`, error);
        }
      });

      console.log(`[FormInitializer] Form initialization complete: ${formType}`);
    },

    /**
     * Clean up form before removal
     * @param {HTMLElement} form - The form element to clean up
     */
    cleanup: function(form) {
      if (!form) return;

      console.log('[FormInitializer] Cleaning up form');

      // Remove from initialized set
      this.initializedForms.delete(form);

      // Dispatch cleanup event for custom handlers
      form.dispatchEvent(new CustomEvent('form:cleanup', { bubbles: true }));
    }
  };

  // Register default initializers

  /**
   * Group selection buttons initializer
   * Handles "Select All" and "Clear All" buttons for group checkboxes
   */
  FormInitializer.register('groupButtons', function(form) {
    const selectAllBtn = form.querySelector('[data-action="select-all-groups"]');
    const clearAllBtn = form.querySelector('[data-action="clear-all-groups"]');
    const groupsField = form.querySelector('[name="groups"]');

    if (!selectAllBtn || !clearAllBtn || !groupsField) {
      console.log('[FormInitializer.groupButtons] Group buttons not found, skipping');
      return;
    }

    // Get all checkboxes in the groups field
    const getCheckboxes = () => {
      if (groupsField.tagName === 'SELECT') {
        // Multiple select
        return Array.from(groupsField.options);
      } else {
        // Checkbox list - find all checkboxes with name="groups"
        return Array.from(form.querySelectorAll('input[type="checkbox"][name="groups"]'));
      }
    };

    // Select All handler
    selectAllBtn.addEventListener('click', function(e) {
      e.preventDefault();
      const items = getCheckboxes();
      items.forEach(item => {
        if (item.tagName === 'OPTION') {
          item.selected = true;
        } else {
          item.checked = true;
        }
      });
      console.log('[FormInitializer.groupButtons] Selected all groups');
    });

    // Clear All handler
    clearAllBtn.addEventListener('click', function(e) {
      e.preventDefault();
      const items = getCheckboxes();
      items.forEach(item => {
        if (item.tagName === 'OPTION') {
          item.selected = false;
        } else {
          item.checked = false;
        }
      });
      console.log('[FormInitializer.groupButtons] Cleared all groups');
    });

    console.log('[FormInitializer.groupButtons] Initialized');
  });

  /**
   * Date pickers initializer
   * Initializes Flatpickr on date input fields
   */
  FormInitializer.register('datePickers', function(form) {
    const dateInputs = form.querySelectorAll('input[type="date"], .datepicker');

    if (dateInputs.length === 0) {
      console.log('[FormInitializer.datePickers] No date inputs found, skipping');
      return;
    }

    // Initialize Flatpickr if available
    if (window.flatpickr) {
      dateInputs.forEach(input => {
        // Skip if already initialized
        if (input._flatpickr) {
          console.log('[FormInitializer.datePickers] Date picker already initialized, skipping');
          return;
        }

        flatpickr(input, {
          dateFormat: 'Y-m-d',
          allowInput: true
        });
      });
      console.log(`[FormInitializer.datePickers] Initialized ${dateInputs.length} date pickers`);
    } else {
      console.warn('[FormInitializer.datePickers] Flatpickr not available');
    }
  });

  /**
   * Form validation initializer
   * Adds Bootstrap validation classes and behavior
   */
  FormInitializer.register('validation', function(form) {
    // Add Bootstrap validation classes
    form.classList.add('needs-validation');

    // Handle form submission validation
    const handleSubmit = function(e) {
      // Only prevent submission if form is invalid
      if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
        console.log('[FormInitializer.validation] Form invalid, preventing submission');
      } else {
        console.log('[FormInitializer.validation] Form valid, allowing submission');
      }
      form.classList.add('was-validated');
    };

    // Use capture phase to run before HTMX
    form.addEventListener('submit', handleSubmit, true);

    console.log('[FormInitializer.validation] Initialized');
  });

  /**
   * Unsaved changes warning initializer
   * Warns users before closing forms with unsaved changes
   */
  FormInitializer.register('unsavedChanges', function(form) {
    let formModified = false;

    // Track form changes (but not permission selector changes)
    const handleInput = function(e) {
      // Don't mark as modified if it's a permission selector
      if (e.target && e.target.classList.contains('permission-select')) {
        return;
      }
      formModified = true;
      console.log('[FormInitializer.unsavedChanges] Form modified');
    };

    form.addEventListener('input', handleInput);
    form.addEventListener('change', handleInput);

    // Reset on form submission (before HTMX processes it)
    form.addEventListener('submit', function(e) {
      console.log('[FormInitializer.unsavedChanges] Form submitted, clearing modified flag');
      formModified = false;
    });

    // Also reset on successful HTMX request
    form.addEventListener('htmx:afterRequest', function(e) {
      if (e.detail.successful) {
        console.log('[FormInitializer.unsavedChanges] HTMX request successful, clearing modified flag');
        formModified = false;
      }
    });

    // Warn before closing if modified
    const offcanvas = form.closest('.offcanvas');
    if (offcanvas) {
      const handleHide = function(e) {
        if (formModified) {
          console.log('[FormInitializer.unsavedChanges] Showing unsaved changes warning');
          const confirmed = confirm('You have unsaved changes. Are you sure you want to close?');
          if (!confirmed) {
            e.preventDefault();
          }
        } else {
          console.log('[FormInitializer.unsavedChanges] No unsaved changes, allowing close');
        }
      };

      offcanvas.addEventListener('hide.bs.offcanvas', handleHide);

      // Clean up on form cleanup
      form.addEventListener('form:cleanup', function() {
        offcanvas.removeEventListener('hide.bs.offcanvas', handleHide);
      });
    }

    console.log('[FormInitializer.unsavedChanges] Initialized');
  });

  /**
   * Searchable select initializer
   * Adds search functionality to multi-select fields
   */
  FormInitializer.register('searchableSelect', function(form) {
    const searchInputs = form.querySelectorAll('.searchable-select-search');

    if (searchInputs.length === 0) {
      console.log('[FormInitializer.searchableSelect] No searchable selects found, skipping');
      return;
    }

    searchInputs.forEach(searchInput => {
      const wrapper = searchInput.closest('.searchable-select-wrapper');
      if (!wrapper) return;

      const select = wrapper.querySelector('select');
      if (!select) return;

      // Filter options on search
      searchInput.addEventListener('input', function() {
        const filter = this.value.toLowerCase();
        Array.from(select.options).forEach(function(option) {
          const text = option.textContent.toLowerCase();
          option.style.display = text.includes(filter) ? '' : 'none';
        });
      });
    });

    console.log(`[FormInitializer.searchableSelect] Initialized ${searchInputs.length} searchable selects`);
  });

  /**
   * Auto-focus initializer
   * Auto-focuses the first form field
   */
  FormInitializer.register('autoFocus', function(form) {
    const firstField = form.querySelector('input:not([type="hidden"]), select, textarea');
    if (firstField) {
      // Use setTimeout to ensure the offcanvas animation is complete
      setTimeout(() => {
        firstField.focus();
      }, 300);
      console.log('[FormInitializer.autoFocus] Focused first field');
    }
  });

  /**
   * Permission selectors initializer
   * Handles permission selector changes with AJAX
   */
  FormInitializer.register('permissionSelectors', function(form) {
    const permissionSelects = form.querySelectorAll('.permission-select');

    if (permissionSelects.length === 0) {
      console.log('[FormInitializer.permissionSelectors] No permission selectors found, skipping');
      return;
    }

    permissionSelects.forEach(select => {
      select.addEventListener('change', function() {
        const userId = this.dataset.userId;
        const personId = this.dataset.personId;
        const permissionValue = this.value;

        if (!personId) {
          console.log('[FormInitializer.permissionSelectors] No person ID, skipping (create form)');
          return;
        }

        console.log('[FormInitializer.permissionSelectors] Updating permission:', {
          userId,
          personId,
          permissionValue
        });

        // Show loading indicator
        const row = document.getElementById(`permission-row-${userId}`);
        const statusSpan = row ? row.querySelector('.permission-status') : null;
        if (statusSpan) {
          statusSpan.style.display = 'inline-block';
        }

        // Disable select during update
        this.disabled = true;

        // Get CSRF token
        function getCookie(name) {
          let cookieValue = null;
          if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
              const cookie = cookies[i].trim();
              if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
              }
            }
          }
          return cookieValue;
        }

        // Send update request
        const formData = new FormData();
        formData.append('user_id', userId);
        formData.append('permission_level', permissionValue);
        formData.append('csrfmiddlewaretoken', getCookie('csrftoken'));

        fetch(form.action, {
          method: 'POST',
          body: formData,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-Permission-Update': 'true'
          }
        })
        .then(response => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          return response.json();
        })
        .then(data => {
          console.log('[FormInitializer.permissionSelectors] Permission updated successfully');
          // Show success feedback (optional)
          if (statusSpan) {
            statusSpan.innerHTML = '<i class="fas fa-check text-success"></i>';
            setTimeout(() => {
              statusSpan.style.display = 'none';
              statusSpan.innerHTML = '<i class="fas fa-spinner fa-spin text-muted"></i>';
            }, 2000);
          }
        })
        .catch(error => {
          console.error('[FormInitializer.permissionSelectors] Error updating permission:', error);
          // Show error feedback
          if (statusSpan) {
            statusSpan.innerHTML = '<i class="fas fa-exclamation-triangle text-danger"></i>';
            statusSpan.style.display = 'inline-block';
          }
          // Show notification
          if (window.showNotification) {
            window.showNotification('Error updating permission. Please try again.', 'error');
          }
        })
        .finally(() => {
          // Re-enable select
          this.disabled = false;
        });
      });
    });

    console.log(`[FormInitializer.permissionSelectors] Initialized ${permissionSelects.length} permission selectors`);
  });

  // Export to global scope
  window.FormInitializer = FormInitializer;

  // Auto-initialize forms after HTMX swaps
  document.body.addEventListener('htmx:afterSwap', function(e) {
    const target = e.detail.target;

    console.log('[FormInitializer] HTMX afterSwap event detected');

    // Find forms in the swapped content
    const forms = target.querySelectorAll('form[data-form-type]');
    forms.forEach(form => {
      FormInitializer.initForm(form);
    });

    // Check if target itself is a form
    if (target.tagName === 'FORM' && target.dataset.formType) {
      FormInitializer.initForm(target);
    }
  });

  // Initialize forms on page load
  document.addEventListener('DOMContentLoaded', function() {
    console.log('[FormInitializer] DOMContentLoaded - initializing existing forms');

    const forms = document.querySelectorAll('form[data-form-type]');
    forms.forEach(form => {
      FormInitializer.initForm(form);
    });
  });

  console.log('[FormInitializer] Module loaded');

})(window);
