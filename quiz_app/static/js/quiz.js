/* Quiz screen: one question at a time, server-synchronised countdown,
   autosave, confirmation before leaving and automatic submission. */
(function () {
  "use strict";

  var dataEl = document.getElementById("quiz-data");
  if (!dataEl) { return; }
  var cfg = JSON.parse(dataEl.textContent);
  var csrf = document.querySelector('meta[name="csrf-token"]').getAttribute("content");
  var questions = cfg.questions;
  var total = questions.length;

  var answers = {};
  Object.keys(cfg.answers || {}).forEach(function (id) { answers[id] = cfg.answers[id]; });

  var state = {
    index: 0,
    submitting: false,
    finished: false,
    pendingSaves: 0,
    autoRetries: 0,
    deadline: performance.now() + cfg.remaining_seconds * 1000
  };

  function $(id) { return document.getElementById(id); }
  var el = {
    text: $("question-text"), tags: $("question-tags"), options: $("options"),
    prev: $("prev-btn"), next: $("next-btn"), clear: $("clear-btn"),
    progressText: $("progress-text"), progressBar: $("progress-bar"),
    navigator: $("navigator"), answeredCount: $("answered-count"),
    timer: $("timer"), timerBox: $("timer-box"), announcer: $("time-announcer"),
    saveState: $("save-state"), submit: $("submit-btn"),
    modal: $("confirm-modal"), modalBody: $("confirm-body"), confirmSubmit: $("confirm-submit"),
    overlay: $("submit-overlay"), overlayTitle: $("overlay-title"), overlayText: $("overlay-text"),
    overlaySpinner: $("overlay-spinner"), retry: $("retry-btn")
  };

  // ---------------------------------------------------------------- helpers
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function answeredTotal() {
    return questions.filter(function (q) { return answers[q.id] !== undefined; }).length;
  }
  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Accept": "application/json" },
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { status: res.status, data: data };
      });
    });
  }

  // ---------------------------------------------------------------- rendering
  function renderQuestion(moveFocus) {
    var q = questions[state.index];
    el.text.textContent = q.text;
    el.tags.textContent = q.category + ", " + q.difficulty;
    el.options.replaceChildren();
    q.options.forEach(function (optionText, i) {
      var wrap = document.createElement("div");
      wrap.className = "option";
      var input = document.createElement("input");
      input.type = "radio";
      input.name = "answer";
      input.id = "opt-" + i;
      input.value = String(i);
      input.className = "option-input";
      input.checked = answers[q.id] === i;
      input.addEventListener("change", function () { setAnswer(q.id, i); });
      var label = document.createElement("label");
      label.className = "option-label";
      label.htmlFor = input.id;
      var bubble = document.createElement("span");
      bubble.className = "bubble";
      bubble.setAttribute("aria-hidden", "true");
      bubble.textContent = String.fromCharCode(65 + i);
      var text = document.createElement("span");
      text.className = "option-text";
      text.textContent = optionText;
      label.append(bubble, text);
      wrap.append(input, label);
      el.options.append(wrap);
    });
    el.progressText.textContent = "Question " + (state.index + 1) + " of " + total;
    el.prev.disabled = state.index === 0;
    el.next.disabled = state.index === total - 1;
    el.clear.disabled = answers[q.id] === undefined;
    updateNavigator();
    if (moveFocus) {
      el.text.setAttribute("tabindex", "-1");
      el.text.focus();
    }
  }

  function buildNavigator() {
    questions.forEach(function (q, i) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "nav-q";
      btn.textContent = String(i + 1);
      btn.addEventListener("click", function () { goTo(i); });
      el.navigator.append(btn);
    });
  }

  function updateNavigator() {
    var buttons = el.navigator.children;
    questions.forEach(function (q, i) {
      var btn = buttons[i];
      var answered = answers[q.id] !== undefined;
      btn.classList.toggle("is-answered", answered);
      btn.classList.toggle("is-current", i === state.index);
      btn.setAttribute("aria-label", "Question " + (i + 1) + ", " + (answered ? "answered" : "not answered"));
      if (i === state.index) { btn.setAttribute("aria-current", "step"); } else { btn.removeAttribute("aria-current"); }
    });
    var count = answeredTotal();
    el.answeredCount.textContent = String(count);
    el.progressBar.value = count;
  }

  function goTo(i) {
    if (i < 0 || i >= total || state.submitting) { return; }
    state.index = i;
    renderQuestion(true);
  }

  // ------------------------------------------------------------------ answers
  function setSaveState(message, isError) {
    el.saveState.textContent = message;
    el.saveState.classList.toggle("is-error", !!isError);
  }

  function setAnswer(questionId, optionIndex) {
    if (state.submitting) { return; }
    if (optionIndex === null) { delete answers[questionId]; } else { answers[questionId] = optionIndex; }
    el.clear.disabled = answers[questionId] === undefined;
    updateNavigator();
    saveAnswer(questionId, optionIndex);
  }

  function saveAnswer(questionId, optionIndex) {
    state.pendingSaves += 1;
    setSaveState("Saving answer...", false);
    postJson(cfg.urls.answer, { question_id: questionId, option_index: optionIndex })
      .then(function (r) {
        if (r.data && r.data.redirect && !state.finished) {
          state.finished = true;
          window.location.assign(r.data.redirect);
          return;
        }
        if (r.status === 200 && r.data.ok) {
          if (typeof r.data.remaining_seconds === "number") {
            state.deadline = performance.now() + r.data.remaining_seconds * 1000;
          }
          setSaveState("Answer saved.", false);
        } else {
          setSaveState((r.data && r.data.error) || "Answer not saved. It will be sent when you submit.", true);
        }
      })
      .catch(function () {
        setSaveState("Answer not saved. Check your connection; it will be sent when you submit.", true);
      })
      .then(function () { state.pendingSaves -= 1; });
  }

  function collectAnswers() {
    var out = {};
    questions.forEach(function (q) { out[q.id] = answers[q.id] === undefined ? null : answers[q.id]; });
    return out;
  }

  // ------------------------------------------------------------------- submit
  function showOverlay(title, text, isError) {
    el.overlay.hidden = false;
    el.overlayTitle.textContent = title;
    el.overlayText.textContent = text;
    el.overlaySpinner.hidden = !!isError;
    el.retry.hidden = !isError;
    if (isError) { el.retry.focus(); }
  }

  function submit(auto) {
    if (state.submitting || state.finished) { return; }
    state.submitting = true;
    showOverlay(
      "Submitting your answers",
      auto ? "Time is up. Your answers are being submitted." : "Please wait. Do not close this page.",
      false
    );
    postJson(cfg.urls.submit, { answers: collectAnswers() })
      .then(function (r) {
        if (r.data && r.data.redirect) {
          state.finished = true;
          window.location.assign(r.data.redirect);
          return;
        }
        throw new Error((r.data && r.data.error) || "The server could not accept the submission.");
      })
      .catch(function (err) {
        state.submitting = false;
        showOverlay("Submission failed", err.message + " Your answers are still on this page.", true);
        if (auto && state.autoRetries < 5) {
          state.autoRetries += 1;
          window.setTimeout(function () { submit(true); }, 3000);
        }
      });
  }

  function requestSubmit() {
    var unanswered = total - answeredTotal();
    var message = unanswered > 0
      ? "You have " + unanswered + " unanswered question" + (unanswered === 1 ? "" : "s") + ". "
      : "All questions are answered. ";
    message += "You cannot change your answers after submitting.";
    if (window.bootstrap && window.bootstrap.Modal) {
      el.modalBody.textContent = message;
      window.bootstrap.Modal.getOrCreateInstance(el.modal).show();
    } else if (window.confirm(message)) {
      submit(false);
    }
  }

  // -------------------------------------------------------------------- timer
  var announced = {};
  var thresholds = [
    [300, "5 minutes remaining"], [60, "1 minute remaining"],
    [30, "30 seconds remaining"], [10, "10 seconds remaining"]
  ];
  function remaining() { return Math.max(0, Math.ceil((state.deadline - performance.now()) / 1000)); }

  function tick() {
    var r = remaining();
    el.timer.textContent = pad(Math.floor(r / 60)) + ":" + pad(r % 60);
    el.timerBox.classList.toggle("timer-warning", r <= 60 && r > 20);
    el.timerBox.classList.toggle("timer-critical", r <= 20);
    thresholds.forEach(function (t) {
      if (r <= t[0] && !announced[t[0]]) {
        announced[t[0]] = true;
        if (cfg.remaining_seconds > t[0]) { el.announcer.textContent = t[1]; }
      }
    });
    if (r <= 0 && !state.submitting && !state.finished) { submit(true); }
  }

  // ------------------------------------------------------------------- wiring
  el.prev.addEventListener("click", function () { goTo(state.index - 1); });
  el.next.addEventListener("click", function () { goTo(state.index + 1); });
  el.clear.addEventListener("click", function () { setAnswer(questions[state.index].id, null); renderQuestion(false); });
  el.submit.addEventListener("click", requestSubmit);
  el.confirmSubmit.addEventListener("click", function () {
    var instance = window.bootstrap && window.bootstrap.Modal.getInstance(el.modal);
    if (instance) { instance.hide(); }
    submit(false);
  });
  el.retry.addEventListener("click", function () { submit(remaining() <= 0); });

  window.addEventListener("beforeunload", function (event) {
    if (state.finished) { return; }
    event.preventDefault();
    event.returnValue = "";
  });

  buildNavigator();
  renderQuestion(false);
  tick();
  window.setInterval(tick, 250);
})();
