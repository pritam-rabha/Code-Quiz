/* Admin question form: reveal extra option rows one at a time. */
(function () {
  "use strict";
  var button = document.getElementById("add-option");
  if (!button) { return; }
  button.addEventListener("click", function () {
    var next = document.querySelector(".option-row[data-extra][hidden]");
    if (next) {
      next.hidden = false;
      var input = next.querySelector('input[type="text"]');
      if (input) { input.focus(); }
    }
    if (!document.querySelector(".option-row[data-extra][hidden]")) {
      button.hidden = true;
    }
  });
})();
