/**
 * Theme toggle functionality
 * Supports dark/light modes with system preference detection
 */

(function() {
  'use strict';

  var STORAGE_KEY = 'ainews-theme';
  var DARK = 'dark';
  var LIGHT = 'light';
  var FALLBACK_THEME = DARK;

  /**
   * Get preferred theme from localStorage or system preference
   */
  function getPreferredTheme() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        return stored;
      }
    } catch (e) {
      // localStorage unavailable (private browsing, etc.)
    }
    return window.matchMedia('(prefers-color-scheme: light)').matches ? LIGHT : DARK;
  }

  /**
   * Apply theme to document
   */
  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (e) {
      // localStorage unavailable
    }
  }

  /**
   * Toggle between dark and light
   */
  window.toggleTheme = function() {
    var current = document.documentElement.getAttribute('data-theme') || DARK;
    var next = current === DARK ? LIGHT : DARK;
    document.body.classList.add('theme-transitioning');
    setTheme(next);
    requestAnimationFrame(function() {
      document.body.classList.remove('theme-transitioning');
    });
  };

  // Event delegation for theme toggle - CSP compliant
  document.addEventListener('click', function(e) {
    if (e.target.closest('.theme-toggle')) {
      window.toggleTheme();
    }
  });

  // Initialize on load
  setTheme(getPreferredTheme());

  // Listen for system preference changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
    // Only auto-switch if user hasn't set a manual preference
    try {
      if (!localStorage.getItem(STORAGE_KEY)) {
        setTheme(e.matches ? DARK : LIGHT);
      }
    } catch (e) {
      // localStorage unavailable
    }
  });

})();
