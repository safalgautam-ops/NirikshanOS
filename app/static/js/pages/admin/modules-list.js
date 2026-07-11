// Page-specific JS for admin/modules/list.html — the create-module dialog.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("createModuleDialog", () => ({
    open: false,
    saving: false,
    error: "",
    csrf: "",
    form: {
      id: "",
      display_name: "",
      description: "",
      category: "",
      tier: "free",
      runtime_image: "nirikshan/base:1.0",
    },

    init() {
      const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
      this.csrf = m ? decodeURIComponent(m[1]) : "";
    },

    openDialog() {
      this.open = true;
      this.error = "";
      this.form = {
        id: "",
        display_name: "",
        description: "",
        category: "",
        tier: "free",
        runtime_image: "nirikshan/base:1.0",
      };
    },

    async submit() {
      this.error = "";
      const id = this.form.id.trim().toLowerCase().replace(/\s+/g, "_");
      if (!id || !this.form.display_name.trim() || !this.form.category.trim()) {
        this.error = "ID, name, and category are required.";
        return;
      }
      this.saving = true;
      try {
        const resp = await fetch("/admin/modules/", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify({ ...this.form, id }),
        });
        const data = await resp.json();
        if (!resp.ok) { this.error = data.error || "Create failed."; return; }
        window.location.href = `/admin/modules/${data.id}/ide`;
      } finally {
        this.saving = false;
      }
    },
  }));
});
