/**
 * Theme toggle. The initial theme is applied by a tiny inline script in <head>
 * to prevent flicker.
 */
// Theme toggle (initialization happens in <head> to prevent flicker)
(function() {
    const themeToggle = document.getElementById('theme-toggle');
    if (!themeToggle) return;

    const html = document.documentElement;

    // Apply theme
    function setTheme(theme) {
        html.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }

    // Toggle theme on button click
    themeToggle.addEventListener('click', () => {
        const current = html.getAttribute('data-theme') || 'light';
        setTheme(current === 'dark' ? 'light' : 'dark');
    });

    // Listen for system theme changes (only if no manual preference set)
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('theme')) {
            setTheme(e.matches ? 'dark' : 'light');
        }
    });
})();
