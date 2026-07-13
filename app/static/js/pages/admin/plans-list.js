// Page-specific JS for admin/plans/list.html — plan cards grid + create/edit dialog.
// Must load BEFORE alpine.min.js (via {% block scripts %}).
//
// Both components MUST be registered via Alpine.data() rather than called as
// plain global functions in x-data — the vendored @alpinejs/csp build only
// evaluates x-data expressions that reference a registered Alpine.data()
// component; it has no unsafe-eval fallback to call an arbitrary global
// function directly. Before this fix, x-data="plansPage(...)" silently
// failed to initialize under the CSP build (a bare `function plansPage(){}`
// declaration was never registered), so nothing on this page was ever
// actually reactive — not the plan grid, not New Plan, nothing.

document.addEventListener("alpine:init", () => {
  Alpine.data("plansPage", (initialPlans, allTiers, allInstances) => ({
    // price_monthly/price_annual come back from MySQL DECIMAL columns as
    // JSON strings (e.g. "49.00") - coerced to numbers here, once, so every
    // template expression below (>, ===, .toFixed()) works without each
    // one needing its own Number()/parseFloat() call.
    planList: initialPlans.map((p) => ({
      ...p,
      price_monthly: Number(p.price_monthly),
      price_annual: Number(p.price_annual),
    })),
    allTiers,
    allInstances,

    openCreate() {
      window.dispatchEvent(new CustomEvent("open-plan-dialog", { detail: { plan: null, allTiers: this.allTiers, allInstances: this.allInstances } }));
    },

    openEdit(plan) {
      window.dispatchEvent(new CustomEvent("open-plan-dialog", { detail: { plan, allTiers: this.allTiers, allInstances: this.allInstances } }));
    },

    async deletePlan(plan) {
      if (!confirm(`Delete "${plan.display_name}"? Existing subscribers will be grandfathered until their subscription expires.`)) return;
      const csrf = window.getCsrfToken ? window.getCsrfToken() : "";
      const resp = await fetch(`/admin/plans/${plan.id}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": csrf },
      });
      if (resp.ok) {
        this.planList = this.planList.filter((p) => p.id !== plan.id);
      }
    },
  }));

  Alpine.data("plansDialog", () => {
    const TIER_DESC = {
      basic: "Imaging, hashing, identification, metadata, and basic searching",
      core_forensics: "File-system analysis, recovery, carving, and basic timelines",
      specialized_forensics: "Memory, network, Windows artifacts, mobile, and advanced timelines",
      enterprise: "Threat hunting, reverse engineering, and distributed acquisition",
    };

    return {
      open: false,
      isEdit: false,
      editId: null,
      allTiers: [],
      allInstances: [],
      tab: "general",
      saving: false,
      error: "",
      form: {
        id: "", display_name: "", description: "",
        price_monthly: 0, price_annual: 0,
        ram_gb: 2, vcpu: 2, storage_gb: 20,
        allowed_tiers: ["basic"], allowed_instance_ids: [], is_active: true, sort_order: 0,
      },
      tierDesc: TIER_DESC,

      receive({ plan, allTiers, allInstances }) {
        this.allTiers = allTiers;
        this.allInstances = allInstances || [];
        this.tab = "general";
        this.error = "";
        if (plan) {
          this.isEdit = true;
          this.editId = plan.id;
          this.form = {
            id: plan.id,
            display_name: plan.display_name || "",
            description: plan.description || "",
            price_monthly: plan.price_monthly || 0,
            price_annual: plan.price_annual || 0,
            ram_gb: plan.resources?.ram_gb || 2,
            vcpu: plan.resources?.vcpu || 2,
            storage_gb: plan.resources?.storage_gb || 20,
            allowed_tiers: Array.isArray(plan.allowed_tiers) ? [...plan.allowed_tiers] : [],
            allowed_instance_ids: Array.isArray(plan.allowed_instance_ids) ? [...plan.allowed_instance_ids] : [],
            is_active: plan.is_active !== undefined ? !!plan.is_active : true,
            sort_order: plan.sort_order || 0,
          };
        } else {
          this.isEdit = false;
          this.editId = null;
          this.form = {
            id: "", display_name: "", description: "",
            price_monthly: 0, price_annual: 0,
            ram_gb: 2, vcpu: 2, storage_gb: 20,
            allowed_tiers: ["basic"], allowed_instance_ids: [], is_active: true, sort_order: 0,
          };
        }
        this.open = true;
      },

      close() { this.open = false; },

      toggleTier(tier) {
        const idx = this.form.allowed_tiers.indexOf(tier);
        if (idx === -1) this.form.allowed_tiers.push(tier);
        else this.form.allowed_tiers.splice(idx, 1);
      },

      toggleInstance(instanceId) {
        const idx = this.form.allowed_instance_ids.indexOf(instanceId);
        if (idx === -1) this.form.allowed_instance_ids.push(instanceId);
        else this.form.allowed_instance_ids.splice(idx, 1);
      },

      async submit() {
        this.error = "";
        this.saving = true;
        const csrf = window.getCsrfToken ? window.getCsrfToken() : "";
        try {
          if (this.isEdit) {
            const resp = await fetch(`/admin/plans/${this.editId}`, {
              method: "PUT",
              headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
              body: JSON.stringify({
                display_name: this.form.display_name,
                description: this.form.description,
                price_monthly: this.form.price_monthly,
                price_annual: this.form.price_annual,
                ram_gb: this.form.ram_gb,
                vcpu: this.form.vcpu,
                storage_gb: this.form.storage_gb,
                allowed_tiers: this.form.allowed_tiers,
                allowed_instance_ids: this.form.allowed_instance_ids,
                is_active: this.form.is_active,
                sort_order: this.form.sort_order,
              }),
            });
            if (!resp.ok) { this.error = "Save failed. Please try again."; return; }
            this.close();
            window.location.reload();
          } else {
            const fd = new FormData();
            fd.append("id", this.form.id);
            fd.append("display_name", this.form.display_name);
            fd.append("description", this.form.description);
            fd.append("price_monthly", this.form.price_monthly);
            fd.append("price_annual", this.form.price_annual);
            fd.append("ram_gb", this.form.ram_gb);
            fd.append("vcpu", this.form.vcpu);
            fd.append("storage_gb", this.form.storage_gb);
            fd.append("is_active", this.form.is_active ? "1" : "0");
            fd.append("sort_order", this.form.sort_order);
            this.form.allowed_tiers.forEach((t) => fd.append("allowed_tiers", t));
            this.form.allowed_instance_ids.forEach((id) => fd.append("allowed_instance_ids", id));
            const resp = await fetch("/admin/plans/", {
              method: "POST",
              headers: { "X-CSRF-Token": csrf },
              body: fd,
            });
            if (!resp.ok) { this.error = "Create failed. Check that the Plan ID is unique."; return; }
            this.close();
            window.location.reload();
          }
        } finally {
          this.saving = false;
        }
      },
    };
  });
});
