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

  /* HTMX error handling - show toast on failed requests */
  document.addEventListener("htmx:responseError", function (e) {
    var container = document.getElementById("toast-container");
    if (!container) return;
    var toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = "Request failed. Please try again.";
    container.appendChild(toast);
    setTimeout(function () {
      toast.remove();
    }, 5000);
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
  });
});
