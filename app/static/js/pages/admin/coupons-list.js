// Page-specific JS for admin/finance/coupons.html — create/edit/delete coupon codes.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("couponsPage", () => ({
    open: false,
    saving: false,
    error: "",
    csrf: "",
    editingId: null,
    form: {
      code: "", discount_type: "percent", discount_value: "10",
      max_redemptions: "", valid_from: "", valid_until: "", is_active: true,
    },

    init() {
      this.csrf = window.getCsrfToken ? window.getCsrfToken() : "";
    },

    openDialog(coupon) {
      this.open = true;
      this.error = "";
      if (coupon) {
        this.editingId = coupon.id;
        this.form = {
          code: coupon.code,
          discount_type: coupon.discount_type,
          discount_value: String(coupon.discount_value),
          max_redemptions: coupon.max_redemptions !== null ? String(coupon.max_redemptions) : "",
          valid_from: coupon.valid_from || "",
          valid_until: coupon.valid_until || "",
          is_active: !!coupon.is_active,
        };
      } else {
        this.editingId = null;
        this.form = {
          code: "", discount_type: "percent", discount_value: "10",
          max_redemptions: "", valid_from: "", valid_until: "", is_active: true,
        };
      }
    },

    async submit() {
      this.error = "";
      if (!this.form.code.trim()) { this.error = "Code is required."; return; }
      if (!this.form.discount_value || Number(this.form.discount_value) <= 0) {
        this.error = "Discount value must be greater than 0.";
        return;
      }
      this.saving = true;
      try {
        const url = this.editingId ? `/admin/finance/coupons/${this.editingId}` : "/admin/finance/coupons";
        const method = this.editingId ? "PUT" : "POST";
        const resp = await fetch(url, {
          method,
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify({
            ...this.form,
            discount_value: Number(this.form.discount_value),
            max_redemptions: this.form.max_redemptions ? Number(this.form.max_redemptions) : null,
          }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { this.error = data.error || "Save failed."; return; }
        window.location.reload();
      } finally {
        this.saving = false;
      }
    },

    async remove(couponId) {
      if (!confirm("Delete this coupon? It can no longer be redeemed.")) return;
      const resp = await fetch(`/admin/finance/coupons/${couponId}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": this.csrf },
      });
      if (resp.ok) window.location.reload();
      else window.toast?.error("Delete failed.");
    },
  }));
});
