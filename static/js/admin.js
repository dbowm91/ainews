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

  // settings.html - test that a provider works
  document.querySelectorAll(".settings-test-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var providerId = btn.getAttribute("data-provider-id");
      var url = btn.getAttribute("data-test-url");
      var result = document.querySelector(
        '[data-result-for="' + providerId + '"]'
      );
      if (!url || !result) return;

      btn.disabled = true;
      result.classList.remove("is-ok", "is-fail");
      result.textContent = "testing…";

      fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
        },
        credentials: "same-origin",
      })
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          var text = data.ok ? "ok" : "failed";
          if (data.latency_ms) text += " (" + data.latency_ms + "ms)";
          if (data.models && data.models.length) {
            text += " — " + data.models.length +
              (data.models.length === 1 ? " model" : " models");
          }
          if (!data.ok && data.detail) text += ": " + data.detail;
          result.textContent = text;
          result.classList.add(data.ok ? "is-ok" : "is-fail");
        })
        .catch(function (err) {
          result.textContent = "failed: " + err;
          result.classList.add("is-fail");
        })
        .finally(function () {
          btn.disabled = false;
        });
    });
  });
});

// Destructive actions ask first.
//
// `hx-confirm` only works on an HTMX request, so a plain form post carrying
// it silently skipped the question. `data-confirm` works on both: the
// button asks here, and the HTMX request asks again through hx-confirm.
document.addEventListener("submit", function (event) {
  var form = event.target;
  if (!form || !form.getAttribute) return;
  var message = form.getAttribute("data-confirm");
  if (!message) return;
  if (!window.confirm(message)) {
    event.preventDefault();
    event.stopPropagation();
  }
});

document.addEventListener("click", function (event) {
  var button = event.target;
  if (!button || !button.getAttribute) return;
  var message = button.getAttribute("data-confirm");
  if (!message) return;
  if (!window.confirm(message)) {
    event.preventDefault();
    event.stopPropagation();
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

// The CSRF token the page was rendered with.
function getCsrfToken() {
  var meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute("content") : "";
}
