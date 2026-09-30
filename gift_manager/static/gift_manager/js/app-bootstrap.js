/**
 * Early page bootstrap: shared helpers, CSRF header for HTMX and the reset of
 * stored list-view preferences once per session. Loads before page scripts.
 */
(function () {
    const app = (window.GiftManager = window.GiftManager || {});

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
    app.getCookie = getCookie;

    // Configure HTMX to include the CSRF token in headers
    document.body.addEventListener('htmx:configRequest', (event) => {
        event.detail.headers['X-CSRFToken'] = getCookie('csrftoken');
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
