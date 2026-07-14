// Page-specific JS for billing/plan_picker.html — org-facing plan picker + pay dialog.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("planPicker", (currentSub) => ({
    open: false,
    plan: null,
    billingPeriod: "monthly",
    currentSub,

    openDialog(plan) {
      this.plan = plan;
      this.billingPeriod = "monthly";
      this.open = true;
    },

    // Cost for the currently selected billing period — drives whether this
    // dialog activates the plan directly or hands off to eSewa.
    get selectedPrice() {
      if (!this.plan) return 0;
      const raw = this.billingPeriod === "annual" ? this.plan.price_annual : this.plan.price_monthly;
      return Number(raw) || 0;
    },

    get isFree() {
      return this.selectedPrice <= 0;
    },

    // True when confirming would replace a different, already-active plan —
    // this is what the cancellation warning and button wording key off of.
    get isSwitchingPlan() {
      return !!(this.currentSub && this.plan && this.currentSub.plan_id !== this.plan.id);
    },
  }));
});
