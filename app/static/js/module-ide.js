/* Alpine components for the module admin pages (list + IDE).
 * Loaded as a deferred same-origin script so CSP 'self' allows it in
 * both dev and production modes. Must appear before alpine.min.js in
 * the HTML so the alpine:init listener registers before Alpine starts. */

document.addEventListener("alpine:init", () => {
  // ── fileTree ──────────────────────────────────────────────────────────────
  // Manages the left-panel file list in the module IDE.
  // Communicates with ideEditor via the 'file-opened' window event.
  Alpine.data("fileTree", (moduleId, initialFiles) => ({
    moduleId,
    fileList: (initialFiles || []).map((f) => ({
      ...f,
      is_entry_point: !!f.is_entry_point,
    })),
    activeFileId: null,
    showNewFile: false,
    newFilename: "",
    newFileError: "",
    csrf: "",

    init() {
      const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
      this.csrf = m ? decodeURIComponent(m[1]) : "";
      const entry =
        this.fileList.find((f) => f.is_entry_point) || this.fileList[0];
      if (entry) this.openFile(entry.id);
    },

    fileIcon(filename) {
      const ext = (filename || "").split(".").pop().toLowerCase();
      const icons = {
        py: "py",
        yaml: "≋",
        yml: "≋",
        sh: "$",
        json: "{}",
        md: "#",
        txt: "T",
        toml: "⊞",
        conf: "⚙",
        ini: "⚙",
      };
      return icons[ext] || "·";
    },

    openFile(fileId) {
      this.activeFileId = fileId;
      const f = this.fileList.find((f) => f.id === fileId);
      window.dispatchEvent(
        new CustomEvent("file-opened", {
          detail: { fileId, filename: f ? f.filename : "" },
        })
      );
    },

    promptNewFile() {
      this.showNewFile = true;
      this.newFilename = "";
      this.newFileError = "";
      this.$nextTick(() => this.$refs.newFilename && this.$refs.newFilename.focus());
    },

    async createFile() {
      this.newFileError = "";
      const name = this.newFilename.trim();
      if (!name) return;
      const resp = await fetch(`/admin/modules/${this.moduleId}/files`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": this.csrf,
        },
        body: JSON.stringify({ filename: name }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        this.newFileError = data.error || "Create failed.";
        return;
      }
      this.fileList.push({
        id: data.id,
        filename: name,
        is_entry_point: data.is_entry_point,
      });
      this.showNewFile = false;
      this.newFilename = "";
      this.openFile(data.id);
    },

    async deleteFile(fileId, filename) {
      if (!confirm(`Delete "${filename}"?`)) return;
      const resp = await fetch(
        `/admin/modules/${this.moduleId}/files/${fileId}`,
        { method: "DELETE", headers: { "X-CSRF-Token": this.csrf } }
      );
      if (!resp.ok) return;
      this.fileList = this.fileList.filter((f) => f.id !== fileId);
      if (this.activeFileId === fileId) {
        this.activeFileId = null;
        window.dispatchEvent(
          new CustomEvent("file-opened", {
            detail: { fileId: null, filename: "" },
          })
        );
      }
    },

    async setEntryPoint(fileId) {
      const resp = await fetch(
        `/admin/modules/${this.moduleId}/files/${fileId}/set-entry`,
        { method: "POST", headers: { "X-CSRF-Token": this.csrf } }
      );
      if (!resp.ok) return;
      this.fileList = this.fileList.map((f) => ({
        ...f,
        is_entry_point: f.id === fileId,
      }));
    },
  }));

  // ── ideEditor ─────────────────────────────────────────────────────────────
  // Manages the right-panel CodeMirror editor and save/toggle actions.
  // Receives file selection via the 'file-opened' window event from fileTree.
  Alpine.data("ideEditor", (moduleId, existingSchema) => {
    function modeForFilename(filename) {
      const ext = (filename || "").split(".").pop().toLowerCase();
      const map = {
        py: "python",
        yaml: "yaml",
        yml: "yaml",
        sh: "shell",
        json: "javascript",
        js: "javascript",
      };
      return map[ext] || null;
    }

    const SCHEMA_PLACEHOLDER = JSON.stringify(
      [
        {
          key: "example_flag",
          label: "Example Flag",
          type: "checkbox",
          default: false,
          description: "A boolean option shown in the Analyze dialog",
        },
      ],
      null,
      2
    );

    return {
      moduleId,
      editor: null,
      schemaEditor: null,
      activeFileId: null,
      activeFilename: "",
      editorTab: "code",
      saving: false,
      testing: false,
      isDirty: false,
      flash: "",
      schemaError: "",
      _flashTimer: null,
      csrf: "",

      init() {
        const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
        this.csrf = m ? decodeURIComponent(m[1]) : "";

        const wrapper = document.getElementById("cm-wrapper");
        if (!wrapper) return;
        this.editor = CodeMirror(wrapper, {
          value: "",
          mode: null,
          theme: "material-darker",
          lineNumbers: true,
          lineWrapping: false,
          indentUnit: 2,
          tabSize: 2,
          indentWithTabs: false,
          extraKeys: {
            "Ctrl-S": () => this.save(),
            "Cmd-S": () => this.save(),
          },
        });
        this.editor.setSize("100%", "100%");
        this.editor.on("change", () => {
          if (this.activeFileId) this.isDirty = true;
        });

        this.$nextTick(() => {
          // Re-measure after Alpine finishes the render cycle.
          // CodeMirror reads container dimensions during init; flex layout
          // may not be finalised yet, causing a 0-height editor.
          if (this.editor) this.editor.refresh();

          const sw = document.getElementById("cm-schema-wrapper");
          if (!sw) return;
          let initialSchema = SCHEMA_PLACEHOLDER;
          if (existingSchema !== null && existingSchema !== undefined) {
            try {
              initialSchema =
                typeof existingSchema === "string"
                  ? existingSchema
                  : JSON.stringify(existingSchema, null, 2);
            } catch (_) {}
          }
          this.schemaEditor = CodeMirror(sw, {
            value: initialSchema,
            mode: "javascript",
            theme: "material-darker",
            lineNumbers: true,
            lineWrapping: false,
            indentUnit: 2,
            tabSize: 2,
            indentWithTabs: false,
            extraKeys: {
              "Ctrl-S": () => this.save(),
              "Cmd-S": () => this.save(),
            },
          });
          this.schemaEditor.setSize("100%", "100%");
          this.schemaEditor.on("change", () => {
            this.isDirty = true;
            this.schemaError = "";
          });
        });
      },

      async loadFileContent({ fileId, filename }) {
        this.activeFileId = fileId;
        this.activeFilename = filename;
        this.isDirty = false;
        if (!fileId) {
          if (this.editor) this.editor.setValue("");
          return;
        }
        const resp = await fetch(
          `/admin/modules/${this.moduleId}/files/${fileId}`,
          { headers: { "X-CSRF-Token": this.csrf } }
        );
        if (!resp.ok) return;
        const data = await resp.json();
        this.editor.setValue(data.content || "");
        this.editor.setOption("mode", modeForFilename(filename));
        this.editor.clearHistory();
        this.isDirty = false;
        this.editor.refresh();
        this.editor.focus();
      },

      async save() {
        this.saving = true;
        try {
          if (this.editorTab === "schema") {
            await this._saveSchema();
          } else {
            await this._saveFile();
          }
        } finally {
          this.saving = false;
        }
      },

      async _saveFile() {
        if (!this.activeFileId || !this.editor) return;
        const resp = await fetch(
          `/admin/modules/${this.moduleId}/files/${this.activeFileId}`,
          {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": this.csrf,
            },
            body: JSON.stringify({ content: this.editor.getValue() }),
          }
        );
        if (resp.ok) {
          this.isDirty = false;
          this._setFlash("Saved.");
        } else {
          this._setFlash("Save failed.");
        }
      },

      async _saveSchema() {
        const raw = (this.schemaEditor && this.schemaEditor.getValue()) || "";
        try {
          const parsed = JSON.parse(raw);
          if (!Array.isArray(parsed))
            throw new Error("Schema must be a JSON array");
          this.schemaError = "";
        } catch (e) {
          this.schemaError = e.message;
          return;
        }
        const resp = await fetch(
          `/admin/modules/${this.moduleId}/options-schema`,
          {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": this.csrf,
            },
            body: JSON.stringify({ schema: raw }),
          }
        );
        if (resp.ok) {
          this.isDirty = false;
          this._setFlash("Parameters saved.");
        } else {
          const d = await resp.json().catch(() => ({}));
          this._setFlash(d.error || "Save failed.");
        }
      },

      async toggleEnabled() {
        const resp = await fetch(
          `/admin/modules/${this.moduleId}/toggle`,
          { method: "POST", headers: { "X-CSRF-Token": this.csrf } }
        ).catch(() => null);
        if (resp && resp.ok) {
          window.location.reload();
        } else {
          this._setFlash("Toggle failed.");
        }
      },

      async runTest() {
        this.testing = true;
        try {
          const resp = await fetch(
            `/admin/modules/${this.moduleId}/test`,
            { method: "POST", headers: { "X-CSRF-Token": this.csrf } }
          ).catch(() => null);
          if (!resp) { this._setFlash("Test request failed."); return; }
          const data = await resp.json().catch(() => ({}));
          this._setFlash(data.message || (resp.ok ? "Test queued." : "Test failed."));
        } finally {
          this.testing = false;
        }
      },

      _setFlash(msg) {
        clearTimeout(this._flashTimer);
        this.flash = msg;
        this._flashTimer = setTimeout(() => { this.flash = ""; }, 3000);
      },
    };
  });

  // ── createModuleDialog ────────────────────────────────────────────────────
  // Dialog for creating a new custom module from the list page.
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
      runtime_image: "python:3.11-slim",
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
        runtime_image: "python:3.11-slim",
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
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": this.csrf,
          },
          body: JSON.stringify({ ...this.form, id }),
        });
        const data = await resp.json();
        if (!resp.ok) {
          this.error = data.error || "Create failed.";
          return;
        }
        window.location.href = `/admin/modules/${data.id}/ide`;
      } finally {
        this.saving = false;
      }
    },
  }));
});
