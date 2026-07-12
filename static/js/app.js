/* Shared UI behaviors — CSP-compliant (no inline scripts). */

document.addEventListener("DOMContentLoaded", function () {
  var focusSearchAfterSwap = false;

  /* Keep the mobile navigation usable with keyboard and assistive technology. */
  document.querySelectorAll(".nav-toggle-label").forEach(function (label) {
    var inputId = label.getAttribute("for");
    var checkbox = inputId ? document.getElementById(inputId) : null;
    if (!checkbox) return;

    function syncNavState() {
      label.setAttribute("aria-expanded", checkbox.checked.toString());
    }

    label.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      checkbox.click();
    });
    checkbox.addEventListener("change", syncNavState);
    syncNavState();
  });

  function syncSearchClear(input) {
    var container = input.closest(".search-container");
    var clearBtn = container && container.querySelector(".search-clear");
    if (clearBtn) clearBtn.classList.toggle("visible", input.value.length > 0);
  }

  document.querySelectorAll('input[name="q"], input[type="search"]').forEach(syncSearchClear);

  /* Keyboard shortcut: '/' focuses search input */
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && !e.ctrlKey && !e.metaKey) {
      var tag = document.activeElement.tagName;
      if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        var searchInput = document.querySelector('input[name="q"], input[type="search"]');
        if (searchInput) {
          e.preventDefault();
          searchInput.focus();
        }
      }
    }
  });

  /* Search clear button */
  document.addEventListener("click", function (e) {
    var clearBtn = e.target.closest(".search-clear");
    if (!clearBtn) return;
    var container = clearBtn.closest(".search-container");
    var searchInput = container && container.querySelector('input[name="q"], input[type="search"]');
    if (!searchInput) return;
    searchInput.value = "";
    syncSearchClear(searchInput);
    searchInput.focus();
    htmx.trigger(searchInput, "search");
  });

  /* Show/hide clear button based on input value */
  document.addEventListener("input", function (e) {
    if (e.target.matches('input[name="q"], input[type="search"]')) {
      syncSearchClear(e.target);
    }
  });

  document.addEventListener("htmx:beforeRequest", function () {
    var activeEl = document.activeElement;
    focusSearchAfterSwap = Boolean(activeEl && (
      activeEl.name === "q" ||
      activeEl.classList.contains("search-input") ||
      activeEl.getAttribute("type") === "search"
    ));
  });

  /* Share button: track click + open dropdown via <details> */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".share-btn");
    if (!btn) return;
    var details = btn.closest(".share-details");
    if (!details) return;

    var articleId = details.getAttribute("data-article-id");
    if (articleId) {
      var csrfMeta = document.querySelector('meta[name="csrf-token"]');
      var csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";
      fetch("/api/v1/track/share-click/" + articleId, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
      });
    }
  });

  /* Update aria-expanded on share details toggle */
  document.addEventListener("toggle", function (e) {
    if (!e.target.classList.contains("share-details")) return;
    var summary = e.target.querySelector("summary");
    if (summary) {
      summary.setAttribute("aria-expanded", e.target.open.toString());
    }
    if (e.target.open) {
      var focusable = e.target.querySelector(".share-dropdown input, .share-dropdown button, .share-dropdown a");
      if (focusable) focusable.focus();
    }
    var dropdown = e.target.querySelector(".share-dropdown");
    if (!dropdown) return;
    if (e.target.open) {
      var rect = dropdown.getBoundingClientRect();
      var viewportHeight = window.innerHeight;
      if (rect.bottom > viewportHeight - 20) {
        dropdown.classList.add("flip-top");
      } else {
        dropdown.classList.remove("flip-top");
      }
    } else {
      dropdown.classList.remove("flip-top");
    }
  });

  /* Copy button: copy share URL to clipboard */
  document.addEventListener("click", function (e) {
    var copyBtn = e.target.closest(".share-copy-btn");
    if (!copyBtn) return;
    var input = copyBtn.previousElementSibling;
    if (!input) return;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(input.value).then(function () {
        copyBtn.textContent = "copied!";
        setTimeout(function () {
          copyBtn.textContent = "copy";
        }, 1000);
      }).catch(function () {
        copyBtn.textContent = "failed";
        setTimeout(function () {
          copyBtn.textContent = "copy";
        }, 1000);
      });
    }
  });

  /* Share URL input: select on click for easy copy (with clipboard support) */
  document.addEventListener("click", function (e) {
    var input = e.target.closest(".share-url-input.js-select-on-click");
    if (!input) return;
    input.select();
    if (navigator.clipboard) {
      navigator.clipboard.writeText(input.value).catch(function () {
        // clipboard not available, fall back to just selecting
      });
    }
  });

  /* Focus management after HTMX content swaps */
  document.addEventListener("htmx:afterSwap", function (e) {
    var content = document.querySelector("#content");
    if (!content) return;

    /* If search input was focused before swap, restore focus to it after */
    var wasSearchFocused = focusSearchAfterSwap;
    focusSearchAfterSwap = false;

    if (wasSearchFocused) {
      var searchInput = content.querySelector('input[name="q"], input.search-input, input[type="search"]');
      if (searchInput) {
        searchInput.focus();
        if (searchInput.value) {
          searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);
        }
      }
    } else {
      var heading = content.querySelector("h1, h2, h3");
      if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.focus();
      }
    }

    var cards = content.querySelectorAll(".article-card:not(.article-card-new)");
    cards.forEach(function (card) {
      card.classList.add("article-card-new");
      card.addEventListener("animationend", function () {
        card.classList.remove("article-card-new");
      }, { once: true });
    });

    /* Remove skeleton cards after HTMX swap (8.1) */
    var skeletonTarget = document.querySelector(".htmx-skeleton-target");
    if (skeletonTarget) {
      var skeletons = skeletonTarget.querySelectorAll(".skeleton-card");
      skeletons.forEach(function (sk) {
        sk.remove();
      });
    }
  });

  /* Keyboard navigation for share dropdown (8.11) */
  document.addEventListener("keydown", function (e) {
    var details = e.target.closest(".share-details");
    if (!details || !details.open) return;
    var links = details.querySelectorAll(".share-social-link");
    if (links.length === 0) return;
    var firstLink = links[0];
    var lastLink = links[links.length - 1];
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (document.activeElement === lastLink) {
        firstLink.focus();
      } else {
        var next = document.activeElement.nextElementSibling || firstLink;
        if (next.classList.contains("share-social-link")) next.focus();
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (document.activeElement === firstLink) {
        lastLink.focus();
      } else {
        var prev = document.activeElement.previousElementSibling || lastLink;
        if (prev.classList.contains("share-social-link")) prev.focus();
      }
    }
  });

  /* Close share dropdown on focusout (8.11) */
  document.addEventListener("focusout", function (e) {
    var details = e.target.closest(".share-details");
    if (!details) return;
    var relatedTarget = e.relatedTarget;
    if (relatedTarget && details.contains(relatedTarget)) return;
    details.open = false;
  });

  /* Focus trap for share dropdown — cycle Tab/Shift+Tab within open dropdown */
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Tab") return;
    var openDetails = document.querySelector(".share-details[open]");
    if (!openDetails) return;
    var dropdown = openDetails.querySelector(".share-dropdown");
    if (!dropdown) return;
    var focusable = dropdown.querySelectorAll(
      "a[href], button, input, [tabindex]:not([tabindex='-1'])"
    );
    if (focusable.length === 0) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });

  /* Admin filter button groups: update hidden inputs and active state */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-filter-name]");
    if (!btn) return;
    var filterName = btn.getAttribute("data-filter-name");
    var filterValue = btn.getAttribute("data-filter-value");
    var filterBar = document.getElementById("filter-bar");
    if (!filterBar) return;
    var hiddenInput = filterBar.querySelector("input[name='" + filterName + "']");
    if (!hiddenInput) return;
    hiddenInput.value = filterValue;
    var group = btn.closest(".filter-btn-group");
    if (!group) return;
    group.querySelectorAll(".filter-btn").forEach(function (b) {
      b.classList.remove("active");
    });
    btn.classList.add("active");
  });

  /* Password visibility toggle (8.22) */
  var passwordToggle = document.querySelector(".password-toggle");
  if (passwordToggle) {
    passwordToggle.addEventListener("click", function () {
      var wrapper = passwordToggle.closest(".login-password-wrapper");
      if (!wrapper) return;
      var input = document.querySelector("#login-password");
      if (!input) return;
      if (input.type === "password") {
        input.type = "text";
        wrapper.classList.add("password-visible");
      } else {
        input.type = "password";
        wrapper.classList.remove("password-visible");
      }
    });
  }

/* Read articles: track in localStorage, dim titles */
  (function () {
    var READ_KEY = "read_articles";

    function getReadIds() {
      try {
        return JSON.parse(localStorage.getItem(READ_KEY) || "[]");
      } catch (e) {
        return [];
      }
    }

    function saveReadIds(ids) {
      try {
        localStorage.setItem(READ_KEY, JSON.stringify(ids));
      } catch (e) {}
    }

    function markArticleRead(articleId) {
      var ids = getReadIds();
      if (ids.indexOf(articleId) === -1) {
        ids.push(articleId);
        saveReadIds(ids);
      }
      var card = document.querySelector('.article-card[data-article-id="' + articleId + '"]');
      if (card) card.classList.add("article-read");
    }

    function initReadArticles() {
      var ids = getReadIds();
      ids.forEach(function (id) {
        var card = document.querySelector('.article-card[data-article-id="' + id + '"]');
        if (card) card.classList.add("article-read");
      });
    }

    document.addEventListener("click", function (e) {
      var link = e.target.closest(".article-card a, .article-card");
      if (!link) return;
      var card = link.closest(".article-card");
      if (!card) return;
      var articleId = card.getAttribute("data-article-id");
      if (articleId) markArticleRead(articleId);
    });

    initReadArticles();
  })();

  /* Bookmark articles: save to localStorage */
  (function () {
    var BOOKMARK_KEY = "bookmarked_articles";

    function getBookmarkedIds() {
      try {
        return JSON.parse(localStorage.getItem(BOOKMARK_KEY) || "[]");
      } catch (e) {
        return [];
      }
    }

    function saveBookmarkedIds(ids) {
      try {
        localStorage.setItem(BOOKMARK_KEY, JSON.stringify(ids));
      } catch (e) {}
    }

    function toggleBookmark(articleId) {
      var ids = getBookmarkedIds();
      var idx = ids.indexOf(articleId);
      if (idx === -1) {
        ids.push(articleId);
      } else {
        ids.splice(idx, 1);
      }
      saveBookmarkedIds(ids);
      updateBookmarkUI(articleId);
    }

    function updateBookmarkUI(articleId) {
      var btn = document.querySelector('.bookmark-btn[data-article-id="' + articleId + '"]');
      if (!btn) return;
      var ids = getBookmarkedIds();
      if (ids.indexOf(articleId) !== -1) {
        btn.classList.add("bookmarked");
        btn.setAttribute("aria-label", "Remove bookmark");
      } else {
        btn.classList.remove("bookmarked");
        btn.setAttribute("aria-label", "Bookmark article");
      }
    }

    function initBookmarks() {
      var ids = getBookmarkedIds();
      ids.forEach(function (id) {
        updateBookmarkUI(id);
      });
    }

    document.addEventListener("click", function (e) {
      var btn = e.target.closest(".bookmark-btn");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      var articleId = btn.getAttribute("data-article-id");
      if (articleId) toggleBookmark(articleId);
    });

    initBookmarks();
  })();

  /* Service worker registration for PWA */
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
      navigator.serviceWorker.register('/static/service-worker.js', {scope: '/'}).catch(function() {});
    });
  }
});
