/**
 * Theme toggle functionality
 * Supports dark/light modes with system preference detection
 */

(function() {
  'use strict';

  var STORAGE_KEY = 'ainews-theme';
  var DARK = 'dark';
  var LIGHT = 'light';

  /**
   * Get preferred theme from localStorage or system preference
   */
  function getPreferredTheme() {
    var stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return stored;
    }
    return window.matchMedia('(prefers-color-scheme: light)').matches ? LIGHT : DARK;
  }

  /**
   * Apply theme to document
   */
  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }

  /**
   * Toggle between dark and light
   */
  window.toggleTheme = function() {
    var current = document.documentElement.getAttribute('data-theme') || DARK;
    var next = current === DARK ? LIGHT : DARK;
    setTheme(next);
  };

  // Initialize on load
  setTheme(getPreferredTheme());

  // Listen for system preference changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
    // Only auto-switch if user hasn't set a manual preference
    if (!localStorage.getItem(STORAGE_KEY)) {
      setTheme(e.matches ? DARK : LIGHT);
    }
  });

})();
