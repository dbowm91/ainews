/**
 * AinewsTheme — browser theme preference controller
 *
 * Implements Phase 4 workstreams 1-6, 10-12:
 *   1. Preference schema (ainews-theme-preference-v2)
 *   2. Legacy migration from ainews-theme
 *   3. Registry metadata from #ainews-theme-metadata script tag
 *   4. No-flash bootstrap
 *   5. Stylesheet controller with failure recovery
 *   6. System mode (matchMedia-driven)
 *  10. Cross-tab sync via storage event
 *  11. Accessibility (prefers-reduced-motion)
 *  12. Storage/privacy (localStorage only, no server persistence)
 *
 * localStorage key: ainews-theme-preference-v2
 * Values: "system" | "theme:<normalized-id>"
 * No display names, URLs, or untrusted data stored.
 *
 * ES5 compatible for maximum browser support.
 */
(function () {
  'use strict';

  /* ------------------------------------------------------------------ */
  /* Constants                                                          */
  /* ------------------------------------------------------------------ */

  var PREFERENCE_KEY = 'ainews-theme-preference-v2';
  var LEGACY_KEY = 'ainews-theme';
  var METADATA_SELECTOR = '#ainews-theme-metadata';
  var STYLESHEET_ID = 'ainews-theme-stylesheet';
  var PREFERENCE_PREFIX = 'theme:';
  var TRANSITION_DURATION_MS = 300;
  var INITIAL_TRANSITION_DELAY_MS = 50;

  /* ------------------------------------------------------------------ */
  /* State                                                              */
  /* ------------------------------------------------------------------ */

  var _initialized = false;
  var _preferencesFromStorage = false;
  var _activatedThemeId = null;
  var _initialActivationDone = false;
  var _stylesheetErrorCount = 0;
  var _maxStylesheetErrors = 3;

  var _registry = null;    // { defaults: { dark, light }, themes: { id: { name, appearance, css_url, origin } } }
  var _currentPreference = 'system';
  var _resolvedThemeId = null;

  var _mediaQuery = null;   // matchMedia('(prefers-color-scheme: dark)')
  var _mediaListener = null;

  /* ------------------------------------------------------------------ */
  /* Storage helpers                                                    */
  /* ------------------------------------------------------------------ */

  function storageRead(key) {
    try {
      return localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function storageWrite(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      /* private browsing or storage disabled — non-fatal */
    }
  }

  function storageRemove(key) {
    try {
      localStorage.removeItem(key);
    } catch (e) {
      /* non-fatal */
    }
  }

  /* ------------------------------------------------------------------ */
  /* Preference parsing                                                 */
  /* ------------------------------------------------------------------ */

  /**
   * Parse stored preference string into a normalized value.
   * Returns "system" or "theme:<id>".
   * Unknown/malformed values fall back to "system".
   */
  function parsePreference(raw) {
    if (typeof raw !== 'string' || raw.length === 0) {
      return 'system';
    }
    var trimmed = raw;
    if (trimmed === 'system') {
      return 'system';
    }
    if (trimmed.indexOf(PREFERENCE_PREFIX) === 0) {
      var id = trimmed.substring(PREFERENCE_PREFIX.length);
      if (id.length > 0 && id.length <= 64 && /^[a-zA-Z0-9_\-]+$/.test(id)) {
        return PREFERENCE_PREFIX + id;
      }
    }
    return 'system';
  }

  function isExplicitPreference(pref) {
    return typeof pref === 'string' && pref.indexOf(PREFERENCE_PREFIX) === 0;
  }

  function preferenceThemeId(pref) {
    if (isExplicitPreference(pref)) {
      return pref.substring(PREFERENCE_PREFIX.length);
    }
    return null;
  }

  /* ------------------------------------------------------------------ */
  /* Registry metadata (Workstream 3)                                   */
  /* ------------------------------------------------------------------ */

  function readRegistryMetadata() {
    var el = document.querySelector(METADATA_SELECTOR);
    if (!el) return null;
    try {
      var json = JSON.parse(el.textContent || '');
      if (!json || typeof json !== 'object') return null;
      if (!json.defaults || !json.themes) return null;
      if (typeof json.defaults.dark !== 'string' || typeof json.defaults.light !== 'string') return null;
      if (typeof json.themes !== 'object') return null;
      return json;
    } catch (e) {
      return null;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Legacy migration (Workstream 2)                                    */
  /* ------------------------------------------------------------------ */

  function migrateLegacyPreference(registry) {
    var newRaw = storageRead(PREFERENCE_KEY);
    if (newRaw !== null) {
      _preferencesFromStorage = true;
      return parsePreference(newRaw);
    }

    var legacyValue = storageRead(LEGACY_KEY);
    var defaultDark = (registry && registry.defaults) ? registry.defaults.dark : null;
    var defaultLight = (registry && registry.defaults) ? registry.defaults.light : null;

    var resolved;
    if (legacyValue === 'dark' && defaultDark) {
      resolved = PREFERENCE_PREFIX + defaultDark;
    } else if (legacyValue === 'light' && defaultLight) {
      resolved = PREFERENCE_PREFIX + defaultLight;
    } else {
      resolved = 'system';
    }

    storageWrite(PREFERENCE_KEY, resolved);
    _preferencesFromStorage = true;

    return resolved;
  }

  /* ------------------------------------------------------------------ */
  /* Theme resolution (Workstream 6)                                    */
  /* ------------------------------------------------------------------ */

  function resolveExplicitThemeId(id, registry) {
    if (!registry || !registry.themes) return null;
    if (registry.themes[id]) return id;
    return null;
  }

  function resolveSystemTheme(registry) {
    if (!registry || !registry.defaults) return null;
    var isDark = _mediaQuery ? _mediaQuery.matches : true;
    var targetId = isDark ? registry.defaults.dark : registry.defaults.light;
    if (!targetId) return null;
    if (resolveExplicitThemeId(targetId, registry)) return targetId;
    return targetId;
  }

  function resolveTheme(preference, registry) {
    if (isExplicitPreference(preference)) {
      var id = preferenceThemeId(preference);
      var resolved = resolveExplicitThemeId(id, registry);
      return resolved || id;
    }
    return resolveSystemTheme(registry);
  }

  /* ------------------------------------------------------------------ */
  /* DOM attribute helpers                                              */
  /* ------------------------------------------------------------------ */

  function setDocumentTheme(themeId, appearance) {
    var html = document.documentElement;
    html.setAttribute('data-theme-id', themeId || '');
    html.setAttribute('data-theme-appearance', appearance || '');
    html.setAttribute('data-theme', appearance || '');
  }

  function getThemeAppearance(themeId, registry) {
    if (!registry || !registry.themes || !registry.themes[themeId]) return null;
    return registry.themes[themeId].appearance || null;
  }

  /* ------------------------------------------------------------------ */
  /* Stylesheet controller (Workstream 5)                               */
  /* ------------------------------------------------------------------ */

  function getExistingStylesheet() {
    return document.getElementById(STYLESHEET_ID);
  }

  function activateStylesheet(cssUrl, callback) {
    var existing = getExistingStylesheet();
    var currentHref = existing ? existing.getAttribute('href') : null;

    if (currentHref === cssUrl) {
      if (callback) callback(null);
      return;
    }

    var link = document.createElement('link');
    link.id = STYLESHEET_ID + '-pending';
    link.rel = 'stylesheet';
    link.href = cssUrl;

    var loadHandler = function () {
      cleanup();
      var finalLink = getExistingStylesheet() || existing;
      if (finalLink && finalLink.parentNode) {
        finalLink.parentNode.removeChild(finalLink);
      }
      link.id = STYLESHEET_ID;
      link.removeEventListener('load', loadHandler);
      link.removeEventListener('error', errorHandler);
      if (callback) callback(null);
    };

    var errorHandler = function () {
      cleanup();
      link.removeEventListener('load', loadHandler);
      link.removeEventListener('error', errorHandler);
      if (link.parentNode) link.parentNode.removeChild(link);
      _stylesheetErrorCount++;
      if (callback) callback(new Error('Stylesheet load failed'));
    };

    var cleanup = function () {};

    link.addEventListener('load', loadHandler);
    link.addEventListener('error', errorHandler);

    if (existing && existing.parentNode) {
      existing.parentNode.insertBefore(link, existing.nextSibling);
    } else {
      (document.head || document.getElementsByTagName('head')[0]).appendChild(link);
    }
  }

  function deactivateStylesheet() {
    var link = getExistingStylesheet();
    if (link && link.parentNode) {
      link.parentNode.removeChild(link);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Transition helper (Workstream 11)                                  */
  /* ------------------------------------------------------------------ */

  function addThemeTransition() {
    if (_initialActivationDone) return;
    var prefersReduced = false;
    try {
      prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { /* ignore */ }
    if (prefersReduced) {
      _initialActivationDone = true;
      return;
    }
    var html = document.documentElement;
    html.classList.add('theme-transitioning');
    setTimeout(function () {
      html.classList.remove('theme-transitioning');
      _initialActivationDone = true;
    }, TRANSITION_DURATION_MS);
  }

  /* ------------------------------------------------------------------ */
  /* Activation                                                         */
  /* ------------------------------------------------------------------ */

  function activateTheme(themeId, registry, options) {
    options = options || {};
    var skipPersist = !!options.skipPersist;

    if (!themeId) {
      themeId = (registry && registry.defaults) ? registry.defaults.dark : null;
      if (!themeId) return;
    }

    var appearance = getThemeAppearance(themeId, registry);
    if (!appearance) {
      if (registry && registry.defaults) {
        themeId = registry.defaults.dark;
        appearance = 'dark';
      }
      if (!appearance) return;
    }

    var cssUrl = null;
    if (registry && registry.themes && registry.themes[themeId]) {
      cssUrl = registry.themes[themeId].css_url;
    }
    if (!cssUrl) {
      cssUrl = '/assets/themes/' + themeId + '.css';
    }

    if (_stylesheetErrorCount >= _maxStylesheetErrors) return;

    setDocumentTheme(themeId, appearance);

    activateStylesheet(cssUrl, function (err) {
      if (err) {
        if (_stylesheetErrorCount >= _maxStylesheetErrors) {
          var fallbackAppearance = (registry && registry.defaults) ? 'dark' : null;
          var fallbackId = (registry && registry.defaults) ? registry.defaults.dark : null;
          if (fallbackId) {
            deactivateStylesheet();
            setDocumentTheme(fallbackId, fallbackAppearance || 'dark');
            var fallbackUrl = '/assets/themes/' + fallbackId + '.css';
            activateStylesheet(fallbackUrl, null);
          }
          storageRemove(PREFERENCE_KEY);
          return;
        }
        var fallbackTheme = (registry && registry.defaults) ? registry.defaults.dark : null;
        if (fallbackTheme && fallbackTheme !== themeId) {
          activateTheme(fallbackTheme, registry, { skipPersist: true });
        }
        return;
      }

      if (!skipPersist) {
        storageWrite(PREFERENCE_KEY, _currentPreference);
      }

      _activatedThemeId = themeId;
      _resolvedThemeId = themeId;

      addThemeTransition();
    });
  }

  /* ------------------------------------------------------------------ */
  /* System mode media listener (Workstream 6)                          */
  /* ------------------------------------------------------------------ */

  function onSystemPreferenceChange() {
    if (!isExplicitPreference(_currentPreference) && _registry) {
      var newThemeId = resolveSystemTheme(_registry);
      if (newThemeId && newThemeId !== _activatedThemeId) {
        activateTheme(newThemeId, _registry);
      }
    }
  }

  function startMediaListener() {
    if (!window.matchMedia) return;
    _mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    if (_mediaQuery.addEventListener) {
      _mediaQuery.addEventListener('change', onSystemPreferenceChange);
    } else if (_mediaQuery.addListener) {
      _mediaQuery.addListener(onSystemPreferenceChange);
    }
  }

  function stopMediaListener() {
    if (!_mediaQuery) return;
    if (_mediaQuery.removeEventListener) {
      _mediaQuery.removeEventListener('change', onSystemPreferenceChange);
    } else if (_mediaQuery.removeListener) {
      _mediaQuery.removeListener(onSystemPreferenceChange);
    }
    _mediaQuery = null;
  }

  /* ------------------------------------------------------------------ */
  /* Cross-tab sync (Workstream 10)                                     */
  /* ------------------------------------------------------------------ */

  function onStorageEvent(e) {
    if (e.key !== PREFERENCE_KEY) return;
    var incoming = e.newValue !== null ? parsePreference(e.newValue) : 'system';
    if (incoming === _currentPreference) return;

    _currentPreference = incoming;

    if (isExplicitPreference(incoming)) {
      var id = preferenceThemeId(incoming);
      var resolved = resolveExplicitThemeId(id, _registry);
      if (resolved) {
        activateTheme(resolved, _registry, { skipPersist: true });
      } else {
        _currentPreference = 'system';
        var fallback = resolveSystemTheme(_registry);
        if (fallback) activateTheme(fallback, _registry, { skipPersist: true });
      }
    } else {
      var themeId = resolveSystemTheme(_registry);
      if (themeId) activateTheme(themeId, _registry, { skipPersist: true });
    }
  }

  function startStorageSync() {
    try {
      window.addEventListener('storage', onStorageEvent);
    } catch (e) { /* non-fatal */ }
  }

  /* ------------------------------------------------------------------ */
  /* Public API (Workstream 5)                                          */
  /* ------------------------------------------------------------------ */

  var controller = {
    /**
     * Activate a theme by registry ID.
     * Only known registry IDs are accepted.
     */
    activate: function (themeId) {
      if (!themeId || !_registry) return;
      var resolved = resolveExplicitThemeId(themeId, _registry);
      if (!resolved) return;

      _currentPreference = PREFERENCE_PREFIX + themeId;
      activateTheme(resolved, _registry);
    },

    /**
     * Set preference to system mode (follow OS light/dark).
     */
    setSystem: function () {
      _currentPreference = 'system';
      var themeId = resolveSystemTheme(_registry);
      if (themeId) activateTheme(themeId, _registry);
    },

    /**
     * Get the current resolved theme ID.
     */
    getActiveThemeId: function () {
      return _activatedThemeId;
    },

    /**
     * Get the current preference string.
     */
    getPreference: function () {
      return _currentPreference;
    },

    /**
     * Get the registry metadata.
     */
    getRegistry: function () {
      return _registry;
    },

    /**
     * Check if preference is in system mode.
     */
    isSystemMode: function () {
      return !isExplicitPreference(_currentPreference);
    }
  };

  window.AinewsTheme = controller;

  /* ------------------------------------------------------------------ */
  /* Backward compatibility                                             */
  /* ------------------------------------------------------------------ */

  window.toggleTheme = function () {
    if (!_registry) return;

    if (isExplicitPreference(_currentPreference)) {
      var currentId = preferenceThemeId(_currentPreference);
      var currentAppearance = getThemeAppearance(currentId, _registry);
      if (currentAppearance === 'light') {
        var darkId = (_registry.defaults) ? _registry.defaults.dark : null;
        if (darkId) controller.activate(darkId);
      } else {
        var lightId = (_registry.defaults) ? _registry.defaults.light : null;
        if (lightId) controller.activate(lightId);
      }
    } else {
      var isDark = _mediaQuery ? _mediaQuery.matches : true;
      if (isDark) {
        var lightDefault = (_registry.defaults) ? _registry.defaults.light : null;
        if (lightDefault) controller.activate(lightDefault);
      } else {
        var darkDefault = (_registry.defaults) ? _registry.defaults.dark : null;
        if (darkDefault) controller.activate(darkDefault);
      }
    }
  };

  /* ------------------------------------------------------------------ */
  /* Selector panel (Workstream 7)                                      */
  /* ------------------------------------------------------------------ */

  function initSelectorPanel() {
    var trigger = document.querySelector('.theme-selector-trigger');
    var panel = document.getElementById('theme-selector-panel');
    var searchInput = panel ? panel.querySelector('.theme-selector-search') : null;
    var options = panel ? panel.querySelectorAll('.theme-selector-option') : [];

    if (!trigger || !panel) return;

    function openPanel() {
      panel.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      updateSelectorState();
      if (searchInput) {
        searchInput.value = '';
        filterOptions('');
        searchInput.focus();
      }
    }

    function closePanel() {
      panel.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      trigger.focus();
    }

    function togglePanel() {
      if (panel.hidden) {
        openPanel();
      } else {
        closePanel();
      }
    }

    function filterOptions(query) {
      var q = (query || '').toLowerCase();
      for (var i = 0; i < options.length; i++) {
        var opt = options[i];
        var text = (opt.textContent || '').toLowerCase();
        var id = opt.getAttribute('data-theme-id') || '';
        var match = !q || text.indexOf(q) !== -1 || id.indexOf(q) !== -1;
        opt.style.display = match ? '' : 'none';
      }
      var groups = panel.querySelectorAll('.theme-selector-group-label');
      for (var g = 0; g < groups.length; g++) {
        var group = groups[g];
        var next = group.nextElementSibling;
        var hasVisible = false;
        while (next && !next.classList.contains('theme-selector-group-label')) {
          if (next.style.display !== 'none') hasVisible = true;
          next = next.nextElementSibling;
        }
        group.style.display = hasVisible ? '' : 'none';
      }
    }

    function updateSelectorState() {
      var isSystem = !isExplicitPreference(_currentPreference);
      var activeId = isSystem ? null : preferenceThemeId(_currentPreference);
      for (var i = 0; i < options.length; i++) {
        var opt = options[i];
        var optId = opt.getAttribute('data-theme-id');
        var isSystemOpt = opt.hasAttribute('data-theme-action') && opt.getAttribute('data-theme-action') === 'system';
        var selected = isSystem ? isSystemOpt : (optId === activeId);
        opt.setAttribute('aria-checked', selected ? 'true' : 'false');
        opt.classList.toggle('theme-selector-option-active', selected);
      }
    }

    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      togglePanel();
    });

    trigger.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        togglePanel();
      } else if (e.key === 'Escape' && !panel.hidden) {
        e.preventDefault();
        closePanel();
      }
    });

    panel.addEventListener('click', function (e) {
      e.stopPropagation();
      var option = e.target.closest('.theme-selector-option');
      if (!option) return;
      var themeAction = option.getAttribute('data-theme-action');
      if (themeAction === 'system') {
        controller.setSystem();
      } else {
        var themeId = option.getAttribute('data-theme-id');
        if (themeId) controller.activate(themeId);
      }
      updateSelectorState();
      setTimeout(closePanel, 100);
    });

    panel.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        closePanel();
        return;
      }
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        var focused = document.activeElement;
        if (focused && focused.classList.contains('theme-selector-option')) {
          focused.click();
        }
        return;
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        var visibleOpts = [];
        for (var i = 0; i < options.length; i++) {
          if (options[i].style.display !== 'none') visibleOpts.push(options[i]);
        }
        if (visibleOpts.length === 0) return;
        var currentIdx = visibleOpts.indexOf(document.activeElement);
        var nextIdx;
        if (e.key === 'ArrowDown') {
          nextIdx = currentIdx < visibleOpts.length - 1 ? currentIdx + 1 : 0;
        } else {
          nextIdx = currentIdx > 0 ? currentIdx - 1 : visibleOpts.length - 1;
        }
        visibleOpts[nextIdx].focus();
      }
    });

    if (searchInput) {
      searchInput.addEventListener('input', function () {
        filterOptions(searchInput.value);
      });
      searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          closePanel();
        } else if (e.key === 'ArrowDown') {
          e.preventDefault();
          var firstVisible = null;
          for (var i = 0; i < options.length; i++) {
            if (options[i].style.display !== 'none') {
              firstVisible = options[i];
              break;
            }
          }
          if (firstVisible) firstVisible.focus();
        }
      });
    }

    document.addEventListener('click', function () {
      if (!panel.hidden) closePanel();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) {
        closePanel();
      }
    });

    var origActivate = controller.activate;
    var origSetSystem = controller.setSystem;
    controller.activate = function (themeId) {
      origActivate.call(controller, themeId);
      updateSelectorState();
    };
    controller.setSystem = function () {
      origSetSystem.call(controller);
      updateSelectorState();
    };

    updateSelectorState();
  }

  /* ------------------------------------------------------------------ */
  /* Click delegation (legacy .theme-toggle)                            */
  /* ------------------------------------------------------------------ */

  document.addEventListener('click', function (e) {
    if (e.target.closest('.theme-toggle') && !e.target.closest('.theme-selector')) {
      window.toggleTheme();
    }
  });

  /* ------------------------------------------------------------------ */
  /* Bootstrap                                                          */
  /* ------------------------------------------------------------------ */

  function bootstrap() {
    if (_initialized) return;
    _initialized = true;

    _registry = readRegistryMetadata();

    _currentPreference = migrateLegacyPreference(_registry);

    var themeId = resolveTheme(_currentPreference, _registry);

    if (themeId) {
      activateTheme(themeId, _registry);
    } else {
      var defaultId = (_registry && _registry.defaults) ? _registry.defaults.dark : null;
      if (defaultId) {
        activateTheme(defaultId, _registry);
      } else {
        setDocumentTheme('dark', 'dark');
      }
    }

    startMediaListener();
    startStorageSync();
    initSelectorPanel();
  }

  bootstrap();

})();
