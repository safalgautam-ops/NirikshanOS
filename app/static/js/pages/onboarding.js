document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-org-wizard]");
  if (!form) return;
  const panels = Array.from(form.querySelectorAll("[data-wizard-step]"));
  const progress = Array.from(form.querySelectorAll("[data-wizard-progress]"));
  const error = form.querySelector("[data-wizard-error]");
  let step = 1;

  function setError(message = "") {
    error.textContent = message;
    error.hidden = !message;
  }

  function render() {
    panels.forEach((panel) => { panel.hidden = Number(panel.dataset.wizardStep) !== step; });
    progress.forEach((bar) => { bar.hidden = Number(bar.dataset.wizardProgress) > step; });
  }

  function validateCurrent() {
    const panel = panels.find((item) => Number(item.dataset.wizardStep) === step);
    if (!panel) return true;
    for (const field of panel.querySelectorAll("[data-required]")) {
      const emptyFile = field.type === "file" && (!field.files || field.files.length === 0);
      if (emptyFile || !String(field.value || "").trim()) {
        setError("Fill in every required field before continuing.");
        field.focus();
        return false;
      }
    }
    setError();
    return true;
  }

  form.addEventListener("click", (event) => {
    if (event.target.closest("[data-wizard-next]")) {
      if (validateCurrent()) { step = Math.min(3, step + 1); render(); }
      return;
    }
    if (event.target.closest("[data-wizard-back]")) {
      step = Math.max(1, step - 1);
      setError();
      render();
    }
  });
  render();
});
