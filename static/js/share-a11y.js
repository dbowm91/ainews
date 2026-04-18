/* Share dropdown accessibility enhancements. */
/* Used by both public and admin templates. */

document.addEventListener("DOMContentLoaded", function () {
  document.addEventListener("toggle", function (e) {
    if (!e.target.classList.contains("share-details")) return;
    var dropdown = e.target.querySelector(".share-dropdown");
    if (dropdown && e.target.open) {
      var focusable = dropdown.querySelector("input, button, a");
      if (focusable) focusable.focus();
    }
  });
});
