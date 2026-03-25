/* Shared UI behaviors — CSP-compliant (no inline scripts). */

document.addEventListener("DOMContentLoaded", function () {
  /* Share button: track click + toggle dropdown */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".share-btn");
    if (!btn) return;
    var container = btn.closest(".share-trigger");
    if (!container) return;
    var checkbox = container.querySelector(".share-checkbox");
    if (!checkbox) return;

    var articleId = btn.getAttribute("data-article-id");
    if (articleId) {
      fetch("/api/track/share-click/" + articleId, { method: "POST" });
    }
    checkbox.checked = !checkbox.checked;
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
});
