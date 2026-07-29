/**
 * Notification System
 * Provides toast-style notifications for user feedback
 * Enhanced for Requirements: 8.4, 4.4
 */

let notificationsContainer;

/**
 * Create or get the notifications container
 * @returns {HTMLElement} The notifications container element
 */
function createNotificationsContainer() {
    let container = document.getElementById("notifications-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "notifications-container";
        container.className = "toast-container position-fixed top-0 end-0 p-3";
        container.style.zIndex = "1055";
        container.setAttribute("aria-live", "polite");
        container.setAttribute("aria-atomic", "true");
        document.body.appendChild(container);
    }
    return container;
}

/**
 * Show a notification message
 * @param {string} message - The message to display
 * @param {string} type - The type of notification (success, info, warning, danger, error)
 * @param {number|null} duration - Duration in milliseconds (null for auto-calculated)
 * @param {Object} options - Additional options
 */
function showNotification(message, type = "success", duration = null, options = {}) {
    // Ensure container exists
    if (!notificationsContainer) {
        notificationsContainer = createNotificationsContainer();
    }

    // Normalize type (error -> danger for Bootstrap consistency)
    if (type === "error") type = "danger";

    // Determine the duration based on the type if not specified
    if (duration === null) {
        // Default durations according to notification type and message length
        const baseTime = Math.max(3000, Math.min(message.length * 50, 15000));
        switch (type) {
            case "success":
                duration = Math.min(baseTime, 5000);
                break; // 3-5 seconds for successes
            case "info":
                duration = Math.min(baseTime, 6000);
                break; // 3-6 seconds for info
            case "warning":
                duration = Math.min(baseTime, 8000);
                break; // 3-8 seconds for warnings
            case "danger":
                duration = Math.min(baseTime, 12000);
                break; // 3-12 seconds for errors
            default:
                duration = 5000; // 5 seconds by default
        }
    }

    // Get appropriate icon and title
    const notificationConfig = getNotificationConfig(type);
    const { icon, title, soundEnabled } = { ...notificationConfig, ...options };

    // Create unique ID for this notification
    const notificationId =
        "notification-" + Date.now() + "-" + Math.random().toString(36).substr(2, 9);

    // Create a notification div using Bootstrap toast structure
    const notification = document.createElement("div");
    notification.id = notificationId;
    notification.className = `toast align-items-center text-bg-${type} border-0`;
    notification.setAttribute("role", type === "danger" ? "alert" : "status");
    notification.setAttribute("aria-live", type === "danger" ? "assertive" : "polite");
    notification.setAttribute("aria-atomic", "true");
    notification.style.minWidth = "300px";

    // Build notification content
    const hasTitle = title && title !== message;
    notification.innerHTML = `
    <div class="d-flex">
      <div class="toast-body d-flex align-items-start">
        ${icon ? `<i class="${icon} me-2 mt-1 flex-shrink-0"></i>` : ""}
        <div class="flex-grow-1">
          ${hasTitle ? `<div class="fw-semibold mb-1">${title}</div>` : ""}
          <div class="notification-message">${message}</div>
          ${
              options.action
                  ? `
            <div class="mt-2">
              <a href="${options.action.url}" class="btn btn-sm btn-outline-light">
                ${options.action.text}
              </a>
            </div>
          `
                  : ""
          }
        </div>
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto"
              data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
  `;

    // Add to the notifications container
    notificationsContainer.appendChild(notification);

    // Initialize Bootstrap toast
    const bsToast = new bootstrap.Toast(notification, {
        delay: duration > 0 ? duration : false,
        autohide: duration > 0,
    });

    // Show the toast
    bsToast.show();

    // Play sound if enabled and supported
    if (soundEnabled && "Audio" in window) {
        playNotificationSound(type);
    }

    // Remove element after it's hidden
    notification.addEventListener("hidden.bs.toast", function () {
        notification.remove();
    });

    // Store reference for potential programmatic dismissal
    notification._bsToast = bsToast;

    return {
        id: notificationId,
        element: notification,
        dismiss: () => bsToast.hide(),
    };
}

/**
 * Get notification configuration based on type
 * @param {string} type - Notification type
 * @returns {Object} Configuration object
 */
function getNotificationConfig(type) {
    const configs = {
        success: {
            icon: "fas fa-check-circle",
            title: "Success",
            soundEnabled: false,
        },
        info: {
            icon: "fas fa-info-circle",
            title: "Information",
            soundEnabled: false,
        },
        warning: {
            icon: "fas fa-exclamation-triangle",
            title: "Warning",
            soundEnabled: true,
        },
        danger: {
            icon: "fas fa-exclamation-circle",
            title: "Error",
            soundEnabled: true,
        },
    };

    return configs[type] || configs.info;
}

/**
 * Play notification sound
 * @param {string} type - Notification type
 */
function playNotificationSound(type) {
    try {
        // Create audio context if needed (for better browser support)
        if (!window.audioContext && "AudioContext" in window) {
            window.audioContext = new AudioContext();
        }

        // Simple beep sound generation
        if (window.audioContext) {
            const oscillator = window.audioContext.createOscillator();
            const gainNode = window.audioContext.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(window.audioContext.destination);

            // Different frequencies for different types
            const frequencies = {
                success: 800,
                info: 600,
                warning: 400,
                danger: 300,
            };

            oscillator.frequency.setValueAtTime(
                frequencies[type] || 600,
                window.audioContext.currentTime
            );
            oscillator.type = "sine";

            gainNode.gain.setValueAtTime(0.1, window.audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, window.audioContext.currentTime + 0.3);

            oscillator.start(window.audioContext.currentTime);
            oscillator.stop(window.audioContext.currentTime + 0.3);
        }
    } catch (error) {
        // Silently fail if audio is not supported
    }
}

/**
 * Show success notification with common success messages
 * @param {string} action - The action that was successful
 * @param {string} entityName - Name of the entity (optional)
 * @param {Object} options - Additional options
 */
function showSuccessNotification(action, entityName = "", options = {}) {
    const messages = {
        created: `${entityName} has been created successfully.`,
        updated: `${entityName} has been updated successfully.`,
        deleted: `${entityName} has been deleted successfully.`,
        saved: `${entityName} has been saved successfully.`,
        shared: `${entityName} has been shared successfully.`,
        imported: `${entityName} has been imported successfully.`,
        exported: `${entityName} has been exported successfully.`,
        copied: `${entityName} has been copied successfully.`,
        moved: `${entityName} has been moved successfully.`,
        archived: `${entityName} has been archived successfully.`,
        restored: `${entityName} has been restored successfully.`,
    };

    const message = messages[action] || `${action} completed successfully.`;
    return showNotification(message, "success", null, options);
}

/**
 * Show error notification with user-friendly error messages
 * @param {string|Error} error - Error message or Error object
 * @param {string} context - Context where the error occurred
 * @param {Object} options - Additional options
 */
function showErrorNotification(error, context = "", options = {}) {
    let message;
    let title = "Error";

    if (error instanceof Error) {
        message = error.message;
    } else if (typeof error === "string") {
        message = error;
    } else if (error && error.message) {
        message = error.message;
    } else {
        message = "An unexpected error occurred.";
    }

    // Add context if provided
    if (context) {
        title = `Error ${context}`;
    }

    // Make error messages more user-friendly
    const friendlyMessages = {
        "Network Error": "Unable to connect to the server. Please check your internet connection.",
        Timeout: "The request took too long to complete. Please try again.",
        403: "You do not have permission to perform this action.",
        404: "The requested item could not be found.",
        500: "A server error occurred. Please try again later.",
        "Validation Error": "Please check your input and try again.",
        "Authentication Error": "Please sign in again to continue.",
    };

    // Check for known error patterns
    for (const [pattern, friendlyMessage] of Object.entries(friendlyMessages)) {
        if (message.includes(pattern) || message.includes(pattern.toLowerCase())) {
            message = friendlyMessage;
            break;
        }
    }

    return showNotification(message, "danger", null, { title, ...options });
}

/**
 * Show validation error notification
 * @param {Object} errors - Validation errors object
 * @param {string} formName - Name of the form (optional)
 */
function showValidationErrorNotification(errors, formName = "") {
    const errorCount = Object.keys(errors).length;
    const title = formName ? `${formName} Validation Error` : "Validation Error";

    let message;
    if (errorCount === 1) {
        const field = Object.keys(errors)[0];
        const fieldErrors = Array.isArray(errors[field]) ? errors[field] : [errors[field]];
        message = `${field}: ${fieldErrors[0]}`;
    } else {
        message = `Please correct ${errorCount} error${errorCount > 1 ? "s" : ""} in the form.`;
    }

    return showNotification(message, "warning", null, { title });
}

/**
 * Show progress notification for long-running operations
 * @param {string} message - Progress message
 * @param {number} progress - Progress percentage (0-100)
 * @param {string} operationId - Unique ID for this operation
 */
function showProgressNotification(message, progress, operationId) {
    const existingNotification = document.getElementById(`progress-${operationId}`);

    if (existingNotification) {
        // Update existing notification
        const progressBar = existingNotification.querySelector(".progress-bar");
        const messageElement = existingNotification.querySelector(".notification-message");

        if (progressBar) {
            progressBar.style.width = `${progress}%`;
            progressBar.setAttribute("aria-valuenow", progress);
        }

        if (messageElement) {
            messageElement.textContent = message;
        }

        return { id: `progress-${operationId}`, element: existingNotification };
    } else {
        // Create new progress notification
        if (!notificationsContainer) {
            notificationsContainer = createNotificationsContainer();
        }

        const notification = document.createElement("div");
        notification.id = `progress-${operationId}`;
        notification.className = "toast align-items-center text-bg-info border-0";
        notification.setAttribute("role", "status");
        notification.setAttribute("aria-live", "polite");
        notification.style.minWidth = "350px";

        notification.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">
          <div class="d-flex align-items-center mb-2">
            <i class="fas fa-cog fa-spin me-2"></i>
            <div class="notification-message flex-grow-1">${message}</div>
          </div>
          <div class="progress" style="height: 4px;">
            <div class="progress-bar" role="progressbar"
                 style="width: ${progress}%"
                 aria-valuenow="${progress}"
                 aria-valuemin="0"
                 aria-valuemax="100"></div>
          </div>
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto"
                data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    `;

        notificationsContainer.appendChild(notification);

        const bsToast = new bootstrap.Toast(notification, {
            autohide: false, // Don't auto-hide progress notifications
        });

        bsToast.show();
        notification._bsToast = bsToast;

        return { id: `progress-${operationId}`, element: notification };
    }
}

/**
 * Complete a progress notification
 * @param {string} operationId - Operation ID
 * @param {string} successMessage - Success message
 */
function completeProgressNotification(operationId, successMessage) {
    const notification = document.getElementById(`progress-${operationId}`);
    if (notification) {
        notification._bsToast.hide();
    }

    // Show success notification
    showSuccessNotification("completed", successMessage);
}

/**
 * Dismiss all notifications
 */
function dismissAllNotifications() {
    const notifications = document.querySelectorAll(".toast");
    notifications.forEach((notification) => {
        if (notification._bsToast) {
            notification._bsToast.hide();
        }
    });
}

/**
 * Get CSRF token from the page
 * @returns {string} The CSRF token value
 */
function getCSRFToken() {
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");
    return csrfToken ? csrfToken.value : "";
}

// =========================================================================
// HTMX Integration for Automatic Notifications
// =========================================================================

function setupHTMXNotifications() {
    // Success notifications for HTMX requests
    document.body.addEventListener("htmx:afterRequest", function (e) {
        const xhr = e.detail.xhr;
        const element = e.detail.elt;

        if (xhr.status >= 200 && xhr.status < 300) {
            // Check for custom success message in response headers
            const successMessage = xhr.getResponseHeader("X-Success-Message");
            if (successMessage) {
                showNotification(successMessage, "success");
            } else {
                // Auto-generate success message based on HTTP method and element
                const method = element.getAttribute("hx-post")
                    ? "POST"
                    : element.getAttribute("hx-put")
                    ? "PUT"
                    : element.getAttribute("hx-delete")
                    ? "DELETE"
                    : "GET";

                if (method === "POST") {
                    showSuccessNotification("created");
                } else if (method === "PUT") {
                    showSuccessNotification("updated");
                } else if (method === "DELETE") {
                    showSuccessNotification("deleted");
                }
            }
        }
    });

    // Error notifications for HTMX requests
    document.body.addEventListener("htmx:responseError", function (e) {
        const xhr = e.detail.xhr;
        const errorMessage =
            xhr.getResponseHeader("X-Error-Message") || `Request failed with status ${xhr.status}`;

        showErrorNotification(errorMessage, "during request");
    });

    // Network error notifications
    document.body.addEventListener("htmx:sendError", function (e) {
        showErrorNotification("Network Error", "connecting to server");
    });

    // Timeout notifications
    document.body.addEventListener("htmx:timeout", function (e) {
        showErrorNotification("Timeout", "waiting for response");
    });
}

// =========================================================================
// Initialization
// =========================================================================

// Initialize notifications container on DOM ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
        notificationsContainer = createNotificationsContainer();
        setupHTMXNotifications();
    });
} else {
    // DOM already loaded
    notificationsContainer = createNotificationsContainer();
    setupHTMXNotifications();
}

// =========================================================================
// Public API
// =========================================================================

window.Notifications = {
    show: showNotification,
    showSuccess: showSuccessNotification,
    showError: showErrorNotification,
    showValidationError: showValidationErrorNotification,
    showProgress: showProgressNotification,
    completeProgress: completeProgressNotification,
    dismissAll: dismissAllNotifications,
    getCSRFToken,
};

// Backward compatibility
window.showNotification = showNotification;
