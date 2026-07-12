// Page-specific JS for billing/plan_picker.html — org-facing plan picker + pay dialog.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("planPicker", () => ({
    open: false,
    plan: null,
    billingPeriod: "monthly",

    openDialog(plan) {
      this.plan = plan;
      this.billingPeriod = "monthly";
      this.open = true;
    },
  }));
});
