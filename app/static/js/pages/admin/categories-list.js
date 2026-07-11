// Page-specific JS for admin/categories/list.html — create/edit/delete module categories.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("categoriesPage", () => ({
    open: false,
    saving: false,
    error: "",
    csrf: "",
    editingId: null,
    form: { name: "", description: "", sort_order: "0" },

    init() {
      this.csrf = window.getCsrfToken ? window.getCsrfToken() : "";
    },

    openDialog(category) {
      this.open = true;
      this.error = "";
      if (category) {
        this.editingId = category.id;
        this.form = {
          name: category.name,
          description: category.description || "",
          sort_order: String(category.sort_order),
        };
      } else {
        this.editingId = null;
        this.form = { name: "", description: "", sort_order: "0" };
      }
    },

    async submit() {
      this.error = "";
      if (!this.form.name.trim()) { this.error = "Name is required."; return; }
      this.saving = true;
      try {
        const url = this.editingId ? `/admin/categories/${this.editingId}` : "/admin/categories/";
        const method = this.editingId ? "PUT" : "POST";
        const resp = await fetch(url, {
          method,
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify(this.form),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { this.error = data.error || "Save failed."; return; }
        window.location.reload();
      } finally {
        this.saving = false;
      }
    },

    async remove(categoryId) {
      if (!confirm("Delete this category? Modules using it will lose their category.")) return;
      const resp = await fetch(`/admin/categories/${categoryId}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": this.csrf },
      });
      if (resp.ok) window.location.reload();
      else window.toast?.error("Delete failed.");
    },
  }));
});
