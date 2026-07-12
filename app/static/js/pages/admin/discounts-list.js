// Page-specific JS for admin/finance/discounts.html — create/edit/delete
// standing org discounts. Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("discountsPage", (orgs) => ({
    orgs,
    open: false,
    saving: false,
    error: "",
    csrf: "",
    editingId: null,
    form: {
      org_id: "", discount_type: "percent", discount_value: "10",
      reason: "", valid_until: "", is_active: true,
    },

    init() {
      this.csrf = window.getCsrfToken ? window.getCsrfToken() : "";
    },

    openDialog(discount) {
      this.open = true;
      this.error = "";
      if (discount) {
        this.editingId = discount.id;
        this.form = {
          org_id: discount.org_id,
          discount_type: discount.discount_type,
          discount_value: String(discount.discount_value),
          reason: discount.reason || "",
          valid_until: discount.valid_until || "",
          is_active: !!discount.is_active,
        };
      } else {
        this.editingId = null;
        this.form = {
          org_id: "", discount_type: "percent", discount_value: "10",
          reason: "", valid_until: "", is_active: true,
        };
      }
    },

    async submit() {
      this.error = "";
      if (!this.form.org_id) { this.error = "Organization is required."; return; }
      if (!this.form.discount_value || Number(this.form.discount_value) <= 0) {
        this.error = "Discount value must be greater than 0.";
        return;
      }
      this.saving = true;
      try {
        const url = this.editingId ? `/admin/finance/discounts/${this.editingId}` : "/admin/finance/discounts";
        const method = this.editingId ? "PUT" : "POST";
        const resp = await fetch(url, {
          method,
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify({ ...this.form, discount_value: Number(this.form.discount_value) }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { this.error = data.error || "Save failed."; return; }
        window.location.reload();
      } finally {
        this.saving = false;
      }
    },

    async remove(discountId) {
      if (!confirm("Delete this discount?")) return;
      const resp = await fetch(`/admin/finance/discounts/${discountId}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": this.csrf },
      });
      if (resp.ok) window.location.reload();
      else window.toast?.error("Delete failed.");
    },
  }));
});
