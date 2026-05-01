/* Admin-specific UI behaviors */

document.addEventListener("DOMContentLoaded", function () {
  // dead_letters.html - reprocess all failed articles
  var reprocessBtn = document.getElementById("reprocess-all-failed-btn");
  if (reprocessBtn) {
    reprocessBtn.addEventListener("click", function () {
      var hiddenInput = document.getElementById("reprocess-failed-ids");
      if (hiddenInput) {
        hiddenInput.value = getAllFailedIds();
      }
    });
  }
});

// dead_letters.html - getAllFailedIds function
function getAllFailedIds() {
  var ids = [];
  document
    .querySelectorAll(".article-checkbox, [data-article-id]")
    .forEach(function (el) {
      var id = el.value || el.getAttribute("data-article-id");
      if (id) ids.push(parseInt(id, 10));
    });
  return ids;
}
