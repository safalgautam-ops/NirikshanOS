document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-plan-picker]");
  if (!root) return;

  let state = { plans: [], current_sub: null };
  try { state = JSON.parse(root.querySelector("[data-plan-picker-state]")?.textContent || "{}"); } catch {}
  const plans = new Map((state.plans || []).map((plan) => [String(plan.id), plan]));
  const dialog = root.querySelector("[data-plan-dialog]");
  const form = root.querySelector("[data-plan-form]");
  const planId = root.querySelector("[data-plan-id]");
  const name = root.querySelector("[data-plan-name]");
  const monthly = root.querySelector("[data-monthly-price]");
  const annual = root.querySelector("[data-annual-price]");
  const warning = root.querySelector("[data-switch-warning]");
  const currentName = root.querySelector("[data-current-plan-name]");
  const switchName = root.querySelector("[data-switch-plan-name]");
  const paidOnly = root.querySelector("[data-paid-only]");
  const paymentCopy = root.querySelector("[data-payment-copy]");
  const freeCopy = root.querySelector("[data-free-copy]");
  const submitLabel = root.querySelector("[data-plan-submit-label]");
  let selectedPlan = null;

  function selectedPrice() {
    const period = form.querySelector('[name="billing_period"]:checked')?.value || "monthly";
    return Number(period === "annual" ? selectedPlan?.price_annual : selectedPlan?.price_monthly) || 0;
  }

  function render() {
    if (!selectedPlan) return;
    const isFree = selectedPrice() <= 0;
    const switching = Boolean(state.current_sub && String(state.current_sub.plan_id) !== String(selectedPlan.id));
    planId.value = selectedPlan.id;
    name.textContent = selectedPlan.display_name || "";
    monthly.textContent = `Rs. ${selectedPlan.price_monthly}`;
    annual.textContent = `Rs. ${selectedPlan.price_annual}`;
    form.action = isFree ? form.dataset.freeAction : form.dataset.payAction;
    paidOnly.hidden = isFree;
    paymentCopy.hidden = isFree;
    freeCopy.hidden = !isFree;
    warning.hidden = !switching;
    currentName.textContent = state.current_sub?.plan_snapshot?.display_name || "";
    switchName.textContent = selectedPlan.display_name || "";
    submitLabel.textContent = switching
      ? (isFree ? "Cancel current plan & switch" : "Cancel current plan & pay")
      : (isFree ? "Activate plan" : "Continue to Payment");
    root.querySelectorAll("[data-period-label]").forEach((label) => {
      const active = label.dataset.periodLabel === (form.querySelector('[name="billing_period"]:checked')?.value || "monthly");
      label.classList.toggle("border-primary/40", active);
      label.classList.toggle("bg-primary/5", active);
    });
  }

  root.addEventListener("click", (event) => {
    const open = event.target.closest("[data-plan-open]");
    if (open) {
      selectedPlan = plans.get(String(open.dataset.planOpen));
      if (!selectedPlan) return;
      const monthlyRadio = form.querySelector('[name="billing_period"][value="monthly"]');
      if (monthlyRadio) monthlyRadio.checked = true;
      render();
      window.openAppDialog(dialog);
      return;
    }
    if (event.target.closest("[data-plan-close]")) window.closeAppDialog(dialog);
  });
  form.addEventListener("change", (event) => {
    if (event.target.matches("[data-billing-period]")) render();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !dialog.hidden) window.closeAppDialog(dialog);
  });
});
