// Small Alpine.data() components that need real JS (DOM measurement, multi-
// statement logic) the CSP build's inline-attribute parser can't run - see
// the comment in layouts/base.html on why that parser only handles simple
// expressions. Lives in a real same-origin file, so CSP (script-src 'self')
// allows it; this is the supported way to do anything non-trivial with the
// CSP build, not a workaround.
document.addEventListener("alpine:init", () => {
  // Drives tabs.html's sliding active-tab indicator (next-app's TabsList).
  // Measures the active trigger's box and writes it as inline style on the
  // indicator element so it can be a plain absolutely-positioned div.
  Alpine.data("tabsIndicator", (initialTab) => ({
    tab: initialTab,
    indicatorStyle: "",

    init() {
      this.moveIndicator();
      window.addEventListener("resize", () => this.moveIndicator());
    },

    selectTab(value) {
      this.tab = value;
      this.$nextTick(() => this.moveIndicator());
    },

    moveIndicator() {
      const active = this.$refs.list.querySelector('[data-active="true"]');
      if (!active) {
        this.indicatorStyle = "";
        return;
      }
      this.indicatorStyle =
        "width:" + active.offsetWidth + "px;" +
        "height:" + active.offsetHeight + "px;" +
        "transform:translateX(" + active.offsetLeft + "px)";
    },
  }));

  // Drives the 3-step organization-registration wizard (onboarding/index.html).
  // Steps are plain sibling <div data-wizard-step="N"> blocks inside one big
  // <form> - this only toggles which one is visible and gates "Next" on the
  // current step's [data-required] fields actually having a value. The real
  // validation authority is server-side (app/features/onboarding/service.py);
  // this is just UX so a half-filled step can't silently advance.
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
