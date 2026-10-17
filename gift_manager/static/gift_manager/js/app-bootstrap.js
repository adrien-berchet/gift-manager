/**
 * Early page bootstrap: CSRF header for HTMX and the reset of
 * stored list-view preferences once per session. Loads before page scripts.
 */
(function () {
    const app = (window.GiftManager = window.GiftManager || {});

    // Configure HTMX to include the CSRF token in headers
    document.body.addEventListener('htmx:configRequest', (event) => {
        event.detail.headers['X-CSRFToken'] = window.GMUtils.getCsrfToken();
    });

    // Clear view preferences localStorage once per session (at login)
    if (app.isAuthenticated && !sessionStorage.getItem('viewPreferencesCleared')) {
        Object.keys(localStorage).forEach((key) => {
            if (key.startsWith('view-preference-')) {
                localStorage.removeItem(key);
            }
        });
        sessionStorage.setItem('viewPreferencesCleared', 'true');
    }
})();
