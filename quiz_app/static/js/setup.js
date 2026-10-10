/* Quiz setup page: tell the participant how many questions match their choice. */
(function () {
  "use strict";
  var dataEl = document.getElementById("availability-data");
  var hint = document.getElementById("availability-hint");
  var category = document.getElementById("category");
  var difficulty = document.getElementById("difficulty");
  if (!dataEl || !hint || !category || !difficulty) { return; }
  var table = JSON.parse(dataEl.textContent);

  function update() {
    var row = table[category.value] || table[""];
    var available = row[difficulty.value] !== undefined ? row[difficulty.value] : row.any;
    var checked = document.querySelector('input[name="count"]:checked');
    var wanted = checked ? parseInt(checked.value, 10) : 0;
    if (available === 0) {
      hint.textContent = "No questions match this category and difficulty. Choose different options.";
    } else if (wanted && available < wanted) {
      hint.textContent = "Only " + available + " question" + (available === 1 ? "" : "s") +
        " match this selection, so your quiz will contain " + available + ".";
    } else {
      hint.textContent = available + " question" + (available === 1 ? "" : "s") + " available for this selection.";
    }
  }

  category.addEventListener("change", update);
  difficulty.addEventListener("change", update);
  document.querySelectorAll('input[name="count"]').forEach(function (input) {
    input.addEventListener("change", update);
  });
  update();
})();
