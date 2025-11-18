/**
 * Notification System
 * Provides toast-style notifications for user feedback
 */

let notificationsContainer;

/**
 * Create or get the notifications container
 * @returns {HTMLElement} The notifications container element
 */
function createNotificationsContainer() {
  let container = document.getElementById('notifications-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'notifications-container';
    container.style.position = 'fixed';
    container.style.top = '20px';
    container.style.right = '20px';
    container.style.zIndex = '1050';
    container.style.maxWidth = '400px';
    document.body.appendChild(container);
  }
  return container;
}

/**
 * Show a notification message
 * @param {string} message - The message to display
 * @param {string} type - The type of notification (success, info, warning, danger)
 * @param {number|null} duration - Duration in milliseconds (null for auto-calculated)
 */
function showNotification(message, type = 'success', duration = null) {
  // Ensure container exists
  if (!notificationsContainer) {
    notificationsContainer = createNotificationsContainer();
  }

  // Determine the duration based on the type if not specified
  if (duration === null) {
    // Default durations according to notification type
    switch(type) {
      case 'success': duration = 5000; break; // 5 seconds for successes
      case 'info': duration = 6000; break;    // 6 seconds for info
      case 'warning': duration = 8000; break; // 8 seconds for warnings
      case 'danger': duration = 10000; break; // 10 seconds for errors
      default: duration = 5000;               // 5 seconds by default
    }
  }

  // Create a notification div
  const notification = document.createElement('div');
  notification.className = `alert alert-${type} alert-dismissible fade show`;
  notification.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.2)';
  notification.style.marginBottom = '10px';
  notification.style.opacity = '0';
  notification.style.transition = 'opacity 0.3s';

  // Add the close button and the message in separate elements
  notification.innerHTML = `
    <div class="d-flex justify-content-between align-items-center">
      <div>${message}</div>
      <button type="button" class="btn-close ms-3" aria-label="Close"></button>
    </div>
  `;

  // Add to the notifications container
  notificationsContainer.appendChild(notification);

  // Force rendering before adding opacity
  setTimeout(() => {
    notification.style.opacity = '1';
  }, 10);

  // Delete after specified duration
  let timeoutId;
  if (duration > 0) {
    timeoutId = setTimeout(() => {
      fadeOutAndRemove(notification);
    }, duration);
  }

  // Add an event handler for the close button
  const closeButton = notification.querySelector('.btn-close');
  if (closeButton) {
    closeButton.addEventListener('click', function() {
      if (timeoutId) clearTimeout(timeoutId); // Cancel the auto-delete delay
      fadeOutAndRemove(notification);
    });
  }

  /**
   * Fade out and remove the notification element
   * @param {HTMLElement} element - The element to remove
   */
  function fadeOutAndRemove(element) {
    element.style.opacity = '0';
    setTimeout(() => element.remove(), 300);
  }
}

/**
 * Get CSRF token from the page
 * @returns {string} The CSRF token value
 */
function getCSRFToken() {
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
  return csrfToken ? csrfToken.value : '';
}

// Initialize notifications container on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function() {
    notificationsContainer = createNotificationsContainer();
  });
} else {
  // DOM already loaded
  notificationsContainer = createNotificationsContainer();
}
