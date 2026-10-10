/* Shared behaviour: confirmation prompts and loading states on forms. */
(function () {
  "use strict";

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) { return; }
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || event.defaultPrevented) { return; }
    var label = form.getAttribute("data-loading");
    if (!label) { return; }
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "true";
    form.setAttribute("aria-busy", "true");
    var button = form.querySelector('button[type="submit"]');
    if (button) {
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      var spinner = document.createElement("span");
      spinner.className = "spinner-border spinner-border-sm me-2";
      spinner.setAttribute("aria-hidden", "true");
      var text = document.createElement("span");
      text.textContent = label + "...";
      button.replaceChildren(spinner, text);
    }
  }, false);

  // Restore forms when the page is shown again from the back/forward cache.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) { return; }
    document.querySelectorAll("form[data-loading]").forEach(function (form) {
      form.dataset.submitting = "false";
      form.removeAttribute("aria-busy");
      var button = form.querySelector('button[type="submit"]');
      if (button && button.dataset.originalHtml) {
        button.innerHTML = button.dataset.originalHtml;
        button.disabled = false;
      }
    });
  });
})();
