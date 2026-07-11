// Page-specific JS for onboarding/index.html — the org-registration wizard.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("orgWizard", () => ({
    step: 1,
    totalSteps: 3,
    error: "",

    next() {
      if (this.validateStep(this.step)) {
        this.error = "";
        this.step = Math.min(this.step + 1, this.totalSteps);
      }
    },

    back() {
      this.error = "";
      this.step = Math.max(this.step - 1, 1);
    },

    validateStep(n) {
      const container = this.$root.querySelector('[data-wizard-step="' + n + '"]');
      if (!container) return true;
      const fields = container.querySelectorAll("[data-required]");
      for (const field of fields) {
        if (!field.value || !field.value.trim()) {
          this.error = "Fill in every required field before continuing.";
          field.focus();
          return false;
        }
      }
      return true;
    },
  }));
});
