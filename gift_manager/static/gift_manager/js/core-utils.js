/**
 * Core Utilities for Gift Manager
 * Centralizes DOM, HTML escaping, URL sanitization, cookie/CSRF parsing, and notification dispatch.
 * Loads early in the page lifecycle (before other application scripts).
 */
(function (window, document) {
    'use strict';

    const replacements = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    };

    /**
     * Escape untrusted text for safe HTML insertion.
     * @param {*} value
     * @returns {string}
     */
    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, character => replacements[character]);
    }

    /**
     * Escape untrusted text for safe HTML attribute insertion.
     * @param {*} value
     * @returns {string}
     */
    function escapeAttribute(value) {
        return escapeHtml(value);
    }

    /**
     * Sanitize a URL to prevent javascript: and protocol-relative (//) exploits.
     * Allows http(s), mailto, #, and same-origin relative URLs (/...).
     * @param {*} value
     * @returns {string}
     */
    function sanitizeUrl(value) {
        const url = String(value ?? '').trim();
        if (!url) return '';
        if (/^(https?:|mailto:|#)/i.test(url)) return url;
        if (url.startsWith('/') && !url.startsWith('//')) return url;
        return '#';
    }

    /**
     * Sanitize and attribute-escape a URL.
     * @param {*} value
     * @returns {string}
     */
    function safeUrl(value) {
        return escapeAttribute(sanitizeUrl(value));
    }

    /**
     * Get a cookie value by name.
     * @param {string} name
     * @returns {string|null}
     */
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

    /**
     * Retrieve CSRF token.
     * Prefers the csrftoken cookie (always in sync with the session across tabs).
     * Falls back to explicit form input or document form input.
     * @param {HTMLFormElement|null} [form=null]
     * @returns {string}
     */
    function getCsrfToken(form = null) {
        const cookieToken = getCookie('csrftoken');
        if (cookieToken) {
            return cookieToken;
        }
        if (form && typeof form.querySelector === 'function') {
            const input = form.querySelector('input[name="csrfmiddlewaretoken"]');
            if (input && input.value) {
                return input.value;
            }
        }
        const docInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (docInput && docInput.value) {
            return docInput.value;
        }
        return '';
    }

    const notificationQueue = [];

    /**
     * Dispatch or queue a notification. If app-shell's window.showNotification is already installed,
     * calls it directly. Otherwise, queues the notification until app-shell calls flushNotifications().
     * @param {string} message
     * @param {string} [type='info']
     * @param {Object} [options={}]
     */
    function showNotification(message, type = 'info', options = {}) {
        if (typeof window.showNotification === 'function' && window.showNotification !== showNotification) {
            return window.showNotification(message, type, options);
        }
        notificationQueue.push({ message, type, options });
    }

    /**
     * Drain any notifications queued before the full app-shell was initialized.
     */
    function flushNotifications() {
        if (typeof window.showNotification === 'function' && window.showNotification !== showNotification) {
            while (notificationQueue.length > 0) {
                const item = notificationQueue.shift();
                window.showNotification(item.message, item.type, item.options);
            }
        }
    }

    const GMUtils = {
        escapeHtml,
        escapeAttribute,
        sanitizeUrl,
        safeUrl,
        getCookie,
        getCsrfToken,
        showNotification,
        flushNotifications
    };

    // Primary namespace
    window.GMUtils = GMUtils;

    // Attach to window.GiftManager namespace
    const app = (window.GiftManager = window.GiftManager || {});
    app.utils = GMUtils;
    app.escapeHtml = escapeHtml;
    app.escapeAttribute = escapeAttribute;
    app.sanitizeUrl = sanitizeUrl;
    app.safeUrl = safeUrl;
    app.getCookie = getCookie;
    app.getCsrfToken = getCsrfToken;

    // Backward-compatible globals
    if (typeof window.escapeHtml === 'undefined') {
        window.escapeHtml = escapeHtml;
    }
    if (typeof window.escapeAttribute === 'undefined') {
        window.escapeAttribute = escapeAttribute;
    }
    if (typeof window.sanitizeUrl === 'undefined') {
        window.sanitizeUrl = sanitizeUrl;
    }
    if (typeof window.safeUrl === 'undefined') {
        window.safeUrl = safeUrl;
    }
    if (typeof window.getCookie === 'undefined') {
        window.getCookie = getCookie;
    }
    if (typeof window.getCsrfToken === 'undefined') {
        window.getCsrfToken = getCsrfToken;
    }
    if (typeof window.showNotification === 'undefined') {
        window.showNotification = showNotification;
    }

})(window, document);
