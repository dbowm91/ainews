/* Shared UI behaviors — CSP-compliant (no inline scripts). */

document.addEventListener("DOMContentLoaded", function () {
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
    var searchInput = document.querySelector('input[name="q"], input[type="search"]');
    if (!searchInput) return;
    searchInput.value = "";
    clearBtn.classList.remove("visible");
    htmx.trigger(searchInput, "search");
  });

  /* Show/hide clear button based on input value */
  document.addEventListener("input", function (e) {
    if (e.target.matches('input[name="q"], input[type="search"]')) {
      var clearBtn = e.target.closest(".search-container").querySelector(".search-clear");
      if (clearBtn) {
        if (e.target.value.length > 0) {
          clearBtn.classList.add("visible");
        } else {
          clearBtn.classList.remove("visible");
        }
      }
    }
  });

  /* Share button: track click + open dropdown via <details> */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".share-btn");
    if (!btn) return;
    var details = btn.closest(".share-details");
    if (!details) return;

    var articleId = details.getAttribute("data-article-id");
    if (articleId) {
      fetch("/api/track/share-click/" + articleId, { method: "POST" });
    }
  });

  /* Update aria-expanded on share details toggle */
  document.addEventListener("toggle", function (e) {
    if (!e.target.classList.contains("share-details")) return;
    var summary = e.target.querySelector("summary");
    if (summary) {
      summary.setAttribute("aria-expanded", e.target.open);
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

  /* Offline detection toast */
  var toast = document.getElementById("offline-toast");
  if (toast) {
    window.addEventListener("offline", function () {
      toast.classList.remove("toast-hidden");
    });
    window.addEventListener("online", function () {
      toast.classList.add("toast-hidden");
    });
    if (!navigator.onLine) {
      toast.classList.remove("toast-hidden");
    }
  }

  /* HTMX error handling - show toast with retry on failed requests */
  document.addEventListener("htmx:responseError", function (e) {
    var container = document.getElementById("toast-container");
    if (!container) return;

    var detail = e.detail;
    var status = detail ? detail.status : 0;
    var statusText = detail ? detail.statusText : "";
    var errorMsg = "Request failed. Please try again.";

    if (detail && detail.xhr && detail.xhr.responseText) {
      try {
        var resp = JSON.parse(detail.xhr.responseText);
        if (resp && resp.error) {
          errorMsg = resp.error;
        }
      } catch (err) {
        if (statusText) errorMsg = statusText;
      }
    }

    var toast = document.createElement("div");
    toast.className = "toast toast-error";

    var msgSpan = document.createElement("span");
    msgSpan.textContent = (status ? "[" + status + "] " : "") + errorMsg;
    toast.appendChild(msgSpan);

    if (detail && detail.requestConfig && detail.requestConfig.requestBody) {
      var retryBtn = document.createElement("button");
      retryBtn.className = "toast-retry-btn";
      retryBtn.textContent = "retry";
      retryBtn.setAttribute("data-hx", "true");
      retryBtn.addEventListener("click", function () {
        var target = detail.target;
        var verb = detail.requestConfig.verb || "get";
        var path = detail.path;
        if (detail.requestConfig.requestBody && verb === "get") {
          path = path + (path.includes("?") ? "&" : "?") + detail.requestConfig.requestBody;
        }
        var hxAttrs = {
          "hx-get": path,
          "hx-target": target,
          "hx-swap": "innerHTML",
          "hx-indicator": ".htmx-indicator",
        };
        for (var attr in hxAttrs) {
          toast.setAttribute(attr, hxAttrs[attr]);
        }
        htmx.process(toast);
        htmx.trigger(toast, "click");
        toast.remove();
      });
      toast.appendChild(retryBtn);
    }

    container.appendChild(toast);

    var dismissTimer = setTimeout(function () {
      if (toast.parentNode) toast.remove();
    }, 8000);

    toast._dismissTimer = dismissTimer;

    toast.addEventListener("click", function (e) {
      if (e.target !== retryBtn) {
        clearTimeout(dismissTimer);
        toast.remove();
      }
    });
  });

  /* Focus management after HTMX content swaps */
  document.addEventListener("htmx:afterSwap", function (e) {
    var content = document.querySelector("#content");
    if (!content) return;
    var heading = content.querySelector("h1, h2, h3");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus();
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

  /* Service worker registration for PWA */
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
      navigator.serviceWorker.register('/static/js/service-worker.js').catch(function() {});
    });
  }
});
