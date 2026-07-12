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

    async toggleActive(instance) {
      const resp = await fetch(`/admin/instances/${instance.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
        body: JSON.stringify({ ...instance, is_active: !instance.is_active }),
      }).catch(() => null);
      if (resp && resp.ok) window.location.reload();
      else window.toast?.error("Failed to update instance.");
    },

    // ── Delete, with a usage preview so nothing changes silently ──────────────
    deleteOpen: false,
    deleteTarget: null,
    deleteUsage: null,
    deleteLoadingUsage: false,
    deleteConfirming: false,
    deleteError: "",

    async openDeleteDialog(instance) {
      this.deleteTarget = instance;
      this.deleteUsage = null;
      this.deleteError = "";
      this.deleteOpen = true;
      this.deleteLoadingUsage = true;
      try {
        const resp = await fetch(`/admin/instances/${instance.id}/usage`);
        this.deleteUsage = resp.ok ? await resp.json() : { modules: 0, plans: 0, test_runs: 0 };
      } finally {
        this.deleteLoadingUsage = false;
      }
    },

    clearingRuns: false,

    async clearTestRuns() {
      if (!this.deleteTarget) return;
      this.clearingRuns = true;
      try {
        const resp = await fetch(`/admin/instances/${this.deleteTarget.id}/clear_test_runs`, {
          method: "POST",
          headers: { "X-CSRF-Token": this.csrf },
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { this.deleteError = data.error || "Failed to clear test runs."; return; }
        window.toast?.info(`Cleared ${data.cleared} test run(s).`);
        // Re-check usage now that the blocking references are gone.
        const usageResp = await fetch(`/admin/instances/${this.deleteTarget.id}/usage`);
        this.deleteUsage = usageResp.ok ? await usageResp.json() : this.deleteUsage;
      } finally {
        this.clearingRuns = false;
      }
    },

    deleteImpactText() {
      if (!this.deleteUsage) return "";
      const parts = [];
      if (this.deleteUsage.modules > 0) parts.push(`unassign ${this.deleteUsage.modules} module(s)`);
      if (this.deleteUsage.plans > 0) parts.push(`remove access from ${this.deleteUsage.plans} plan(s)`);
      const change = parts.length ? parts.join(" and ") : "nothing else — no modules or plans currently reference it";
      return `This will ${change}. This cannot be undone.`;
    },

    async confirmDelete() {
      if (!this.deleteTarget || (this.deleteUsage && this.deleteUsage.test_runs > 0)) return;
      this.deleteConfirming = true;
      this.deleteError = "";
      try {
        const resp = await fetch(`/admin/instances/${this.deleteTarget.id}`, {
          method: "DELETE",
          headers: { "X-CSRF-Token": this.csrf },
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) { this.deleteError = data.error || "Delete failed."; return; }
        window.location.reload();
      } finally {
        this.deleteConfirming = false;
      }
    },
  }));
});
