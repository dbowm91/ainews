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
    navigator.clipboard.writeText(input.value).then(function () {
      copyBtn.textContent = "copied!";
      setTimeout(function () {
        copyBtn.textContent = "copy";
      }, 1000);
    });
  });

  /* Share URL input: select on click for easy copy */
  document.addEventListener("click", function (e) {
    var input = e.target.closest(".share-url-input");
    if (!input) return;
    input.select();
    navigator.clipboard.writeText(input.value);
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
});
