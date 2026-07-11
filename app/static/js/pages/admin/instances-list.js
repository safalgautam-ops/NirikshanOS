// Page-specific JS for admin/instances/list.html — register/edit/recheck container instances.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("instancesPage", () => ({
    open: false,
    saving: false,
    error: "",
    csrf: "",
    editingId: null,
    form: {
      id: "",
      display_name: "",
      image_tag: "",
      cpu_limit: "1.0",
      memory_limit: "512m",
      pids_limit: "128",
      queue_name: "standard_queue",
      default_timeout_seconds: "120",
    },

    init() {
      this.csrf = window.getCsrfToken ? window.getCsrfToken() : "";
    },

    openDialog(instance) {
      this.open = true;
      this.error = "";
      if (instance) {
        this.editingId = instance.id;
        this.form = {
          id: instance.id,
          display_name: instance.display_name,
          image_tag: instance.image_tag,
          cpu_limit: instance.cpu_limit,
          memory_limit: instance.memory_limit,
          pids_limit: String(instance.pids_limit),
          queue_name: instance.queue_name,
          default_timeout_seconds: String(instance.default_timeout_seconds),
        };
      } else {
        this.editingId = null;
        this.form = {
          id: "", display_name: "", image_tag: "",
          cpu_limit: "1.0", memory_limit: "512m", pids_limit: "128",
          queue_name: "standard_queue", default_timeout_seconds: "120",
        };
      }
    },

    async submit() {
      this.error = "";
      if (!this.form.display_name.trim() || !this.form.image_tag.trim()) {
        this.error = "Display name and image tag are required.";
        return;
      }
      this.saving = true;
      try {
        const url = this.editingId ? `/admin/instances/${this.editingId}` : "/admin/instances/";
        const method = this.editingId ? "PUT" : "POST";
        const id = this.form.id.trim().toLowerCase().replace(/\s+/g, "_");
        const resp = await fetch(url, {
          method,
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify({ ...this.form, id }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { this.error = data.error || "Save failed."; return; }
        window.location.reload();
      } finally {
        this.saving = false;
      }
    },

    async recheck(instanceId) {
      const resp = await fetch(`/admin/instances/${instanceId}/recheck`, {
        method: "POST",
        headers: { "X-CSRF-Token": this.csrf },
      }).catch(() => null);
      if (resp && resp.ok) {
        window.toast?.info("Recheck queued — refresh in a few seconds to see the updated status.");
      } else {
        window.toast?.error("Recheck request failed.");
      }
    },
  }));
});
