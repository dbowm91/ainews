/**
 * AinewsTheme — browser theme preference controller
 *
 * Manages two independent stylesheet roles:
 *   1. Application stylesheet (id="ainews-app-stylesheet") — permanent, never touched
 *   2. Theme palette stylesheet (id="ainews-theme-stylesheet") — replaceable palette vars only
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
  var APP_STYLESHEET_ID = 'ainews-app-stylesheet';
  var PALETTE_STYLESHEET_ID = 'ainews-theme-stylesheet';
  var PREFERENCE_PREFIX = 'theme:';
  var TRANSITION_DURATION_MS = 300;

  /* ------------------------------------------------------------------ */
  /* State                                                              */
  /* ------------------------------------------------------------------ */

  var _initialized = false;
  var _preferencesFromStorage = false;
  var _activatedThemeId = null;
  var _stylesheetErrorCount = 0;
  var _maxStylesheetErrors = 3;
  var _activationGeneration = 0;

  var _registry = null;
  var _currentPreference = 'system';
  var _resolvedThemeId = null;

  var _mediaQuery = (typeof window !== 'undefined' && window.matchMedia) ? window.matchMedia('(prefers-color-scheme: dark)') : null;

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
  /* Registry metadata                                                  */
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
  /* Legacy migration                                                   */
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
  /* Theme resolution                                                   */
  /* ------------------------------------------------------------------ */

  function isRegisteredThemeId(id, registry) {
    return !!(registry && registry.themes && registry.themes[id]);
  }

  function resolveExplicitThemeId(id, registry) {
    if (!isRegisteredThemeId(id, registry)) return null;
    return id;
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
      if (resolved) return resolved;
      _currentPreference = 'system';
      return resolveSystemTheme(registry);
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
  /* Palette stylesheet controller                                       */
  /* ------------------------------------------------------------------ */

  function getPaletteStylesheet() {
    return document.getElementById(PALETTE_STYLESHEET_ID);
  }

  function ensurePaletteLink() {
    var link = getPaletteStylesheet();
    if (link) return link;
    link = document.createElement('link');
    link.id = PALETTE_STYLESHEET_ID;
    link.rel = 'stylesheet';
    link.href = '';
    var appLink = document.getElementById(APP_STYLESHEET_ID);
    if (appLink && appLink.parentNode) {
      appLink.parentNode.insertBefore(link, appLink.nextSibling);
    } else {
      (document.head || document.getElementsByTagName('head')[0]).appendChild(link);
    }
    return link;
  }

  function activateStylesheet(cssUrl, generation, callback) {
    var currentLink = getPaletteStylesheet();
    var currentHref = currentLink ? currentLink.getAttribute('href') : null;

    if (currentHref === cssUrl) {
      if (callback) callback(null);
      return;
    }

    var link = document.createElement('link');
    link.id = PALETTE_STYLESHEET_ID + '-pending';
    link.rel = 'stylesheet';
    link.href = cssUrl;

    var loadHandler = function () {
      cleanup();
      if (generation !== _activationGeneration) {
        if (link.parentNode) link.parentNode.removeChild(link);
        return;
      }
      var oldLink = getPaletteStylesheet();
      if (oldLink && oldLink !== link && oldLink.parentNode) {
        oldLink.parentNode.removeChild(oldLink);
      }
      link.id = PALETTE_STYLESHEET_ID;
      link.removeEventListener('load', loadHandler);
      link.removeEventListener('error', errorHandler);
      _stylesheetErrorCount = 0;
      if (callback) callback(null);
    };

    var errorHandler = function () {
      cleanup();
      link.removeEventListener('load', loadHandler);
      link.removeEventListener('error', errorHandler);
      if (link.parentNode) link.parentNode.removeChild(link);
      if (generation === _activationGeneration) {
        _stylesheetErrorCount++;
      }
      if (callback) callback(new Error('Stylesheet load failed'));
    };

    var cleanup = function () {};

    link.addEventListener('load', loadHandler);
    link.addEventListener('error', errorHandler);

    if (currentLink && currentLink.parentNode) {
      currentLink.parentNode.insertBefore(link, currentLink.nextSibling);
    } else {
      ensurePaletteLink();
      var palette = getPaletteStylesheet();
      if (palette && palette !== link && palette.parentNode) {
        palette.parentNode.insertBefore(link, palette.nextSibling);
      } else {
        (document.head || document.getElementsByTagName('head')[0]).appendChild(link);
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* Transition helper                                                  */
  /* ------------------------------------------------------------------ */

  function addThemeTransition(skipTransition) {
    if (skipTransition) return;
    var prefersReduced = false;
    try {
      prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) { /* ignore */ }
    if (prefersReduced) return;
    var html = document.documentElement;
    html.classList.add('theme-transitioning');
    setTimeout(function () {
      html.classList.remove('theme-transitioning');
    }, TRANSITION_DURATION_MS);
  }

  /* ------------------------------------------------------------------ */
  /* Activation                                                         */
  /* ------------------------------------------------------------------ */

  function activateTheme(themeId, registry, options) {
    options = options || {};
    var skipPersist = !!options.skipPersist;
    var skipTransition = !!options.skipTransition;

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

    var generation = ++_activationGeneration;

    setDocumentTheme(themeId, appearance);

    activateStylesheet(cssUrl, generation, function (err) {
      if (generation !== _activationGeneration) return;

      if (err) {
        if (_stylesheetErrorCount >= _maxStylesheetErrors) {
          storageRemove(PREFERENCE_KEY);
          return;
        }
        return;
      }

      if (!skipPersist) {
        storageWrite(PREFERENCE_KEY, _currentPreference);
      }

      _activatedThemeId = themeId;
      _resolvedThemeId = themeId;

      addThemeTransition(skipTransition);
    });
  }

  /* ------------------------------------------------------------------ */
  /* System mode media listener                                         */
  /* ------------------------------------------------------------------ */

  function onSystemPreferenceChange() {
    if (!isExplicitPreference(_currentPreference) && _registry) {
      var newThemeId = resolveSystemTheme(_registry);
      if (newThemeId && newThemeId !== _activatedThemeId) {
        activateTheme(newThemeId, _registry, { skipTransition: false });
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
  /* Cross-tab sync                                                     */
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
  /* Public API                                                         */
  /* ------------------------------------------------------------------ */

  var controller = {
    activate: function (themeId) {
      if (!themeId || !_registry) return;
      var resolved = resolveExplicitThemeId(themeId, _registry);
      if (!resolved) return;

      _currentPreference = PREFERENCE_PREFIX + themeId;
      activateTheme(resolved, _registry);
    },

    setSystem: function () {
      _currentPreference = 'system';
      var themeId = resolveSystemTheme(_registry);
      if (themeId) activateTheme(themeId, _registry);
    },

    getActiveThemeId: function () {
      return _activatedThemeId;
    },

    getPreference: function () {
      return _currentPreference;
    },

    getRegistry: function () {
      return _registry;
    },

    isSystemMode: function () {
      return !isExplicitPreference(_currentPreference);
    }
  };

  window.AinewsTheme = controller;

  /* ------------------------------------------------------------------ */
  /* Selector panel                                                     */
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
  /* Bootstrap                                                          */
  /* ------------------------------------------------------------------ */

  function bootstrap() {
    if (_initialized) return;
    _initialized = true;

    _registry = readRegistryMetadata();

    _currentPreference = migrateLegacyPreference(_registry);

    var themeId = resolveTheme(_currentPreference, _registry);

    if (themeId) {
      activateTheme(themeId, _registry, { skipTransition: true });
    } else {
      var defaultId = (_registry && _registry.defaults) ? _registry.defaults.dark : null;
      if (defaultId) {
        activateTheme(defaultId, _registry, { skipTransition: true });
      } else {
        setDocumentTheme('dark', 'dark');
      }
    }

    startMediaListener();
    startStorageSync();

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initSelectorPanel);
    } else {
      initSelectorPanel();
    }
  }

  bootstrap();

})();
