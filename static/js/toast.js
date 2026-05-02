/* Toast notification system */

document.addEventListener("DOMContentLoaded", function () {
  var container = document.getElementById("toast-container");
  if (!container) return;

  /* Offline detection toast */
  var offlineToast = document.getElementById("offline-toast");
  if (offlineToast) {
    window.addEventListener("offline", function () {
      offlineToast.classList.remove("toast-hidden");
    });
    window.addEventListener("online", function () {
      offlineToast.classList.add("toast-hidden");
    });
    if (!navigator.onLine) {
      offlineToast.classList.remove("toast-hidden");
    }
  }

  /* HTMX error handling - show toast with retry on failed requests */
  document.addEventListener("htmx:responseError", function (e) {
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

  /* Generic toast function for programmatic use */
  window.showToast = function (message, type, duration) {
    type = type || "info";
    duration = duration || 4000;

    var toast = document.createElement("div");
    toast.className = "toast toast-" + type;

    var msgSpan = document.createElement("span");
    msgSpan.textContent = message;
    toast.appendChild(msgSpan);

    container.appendChild(toast);

    var dismissTimer = setTimeout(function () {
      if (toast.parentNode) {
        toast.style.opacity = "0";
        setTimeout(function () {
          if (toast.parentNode) toast.remove();
        }, 200);
      }
    }, duration);

    toast.addEventListener("click", function () {
      clearTimeout(dismissTimer);
      toast.style.opacity = "0";
      setTimeout(function () {
        if (toast.parentNode) toast.remove();
      }, 200);
    });
  };
});
