// Page-specific JS for admin/modules/ide.html — fileTree + ideEditor Alpine components.
// Must load BEFORE alpine.min.js (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  Alpine.data("fileTree", (moduleId, initialFiles) => ({
    moduleId,
    fileList: (initialFiles || []).map((f) => ({ ...f, is_entry_point: !!f.is_entry_point })),
    activeFileId: null,
    showNewFile: false,
    newFilename: "",
    newFileError: "",
    csrf: "",

    init() {
      this.csrf = window.getCsrfToken ? window.getCsrfToken() : "";
      const entry = this.fileList.find((f) => f.is_entry_point) || this.fileList[0];
      if (entry) this.openFile(entry.id);
    },

    fileIcon(filename) {
      const ext = (filename || "").split(".").pop().toLowerCase();
      const icons = { py: "py", yaml: "≋", yml: "≋", sh: "$", json: "{}", md: "#", txt: "T", toml: "⊞", conf: "⚙", ini: "⚙" };
      return icons[ext] || "·";
    },

    openFile(fileId) {
      this.activeFileId = fileId;
      const f = this.fileList.find((f) => f.id === fileId);
      window.dispatchEvent(new CustomEvent("file-opened", { detail: { fileId, filename: f ? f.filename : "" } }));
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
        headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
        body: JSON.stringify({ filename: name }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) { this.newFileError = data.error || "Create failed."; return; }
      this.fileList.push({ id: data.id, filename: name, is_entry_point: !!data.is_entry_point });
      this.showNewFile = false;
      this.newFilename = "";
      this.openFile(data.id);
    },

    async deleteFile(fileId, filename) {
      if (!confirm(`Delete "${filename}"?`)) return;
      const resp = await fetch(`/admin/modules/${this.moduleId}/files/${fileId}`, {
        method: "DELETE",
        headers: { "X-CSRF-Token": this.csrf },
      });
      if (!resp.ok) return;
      this.fileList = this.fileList.filter((f) => f.id !== fileId);
      if (this.activeFileId === fileId) {
        this.activeFileId = null;
        window.dispatchEvent(new CustomEvent("file-opened", { detail: { fileId: null, filename: "" } }));
      }
    },

    async setEntryPoint(fileId) {
      const resp = await fetch(`/admin/modules/${this.moduleId}/files/${fileId}/set-entry`, {
        method: "POST",
        headers: { "X-CSRF-Token": this.csrf },
      });
      if (!resp.ok) return;
      this.fileList = this.fileList.map((f) => ({ ...f, is_entry_point: f.id === fileId }));
    },
  }));

  Alpine.data("ideEditor", (moduleId, existingSchema, moduleMeta, instances, existingPipeline) => {
    function modeForFilename(filename) {
      const ext = (filename || "").split(".").pop().toLowerCase();
      return ({ py: "python", yaml: "yaml", yml: "yaml", sh: "shell", json: "javascript", js: "javascript" }[ext] || null);
    }

    const SCHEMA_PLACEHOLDER = JSON.stringify([{
      key: "example_flag",
      label: "Example Flag",
      type: "checkbox",
      default: false,
      description: "A boolean option shown in the Analyze dialog",
    }], null, 2);

    const PIPELINE_PLACEHOLDER = JSON.stringify({
      steps: [
        { id: "step_one", run: { argv: ["python3", "step_one.py"] } },
        { id: "step_two", depends_on: ["step_one"], run: { script: "result = {\"status\": \"success\", \"exit_code\": 0, \"stdout_file\": None, \"stderr_file\": None, \"error\": None}" } },
      ],
    }, null, 2);

    return {
      moduleId,
      editor: null,
      schemaEditor: null,
      pipelineEditor: null,
      activeFileId: null,
      activeFilename: "",
      editorTab: "code",
      saving: false,
      testDialogOpen: false,
      deleteDialogOpen: false,
      deleting: false,
      deleteError: "",
      testFile: null,
      testRunning: false,
      testRunId: null,
      testStatus: "",
      testResult: null,
      testErrorMessage: "",
      testError: "",
      _testPollTimer: null,
      isDirty: false,
      flash: "",
      schemaError: "",
      pipelineError: "",
      settingsError: "",
      _flashTimer: null,
      csrf: "",

      // Editable module metadata (Settings tab)
      settings: {
        display_name: (moduleMeta && moduleMeta.display_name) || "",
        description:  (moduleMeta && moduleMeta.description)  || "",
        category_id:  (moduleMeta && moduleMeta.category_id)  || "",
        tier:         (moduleMeta && moduleMeta.tier)         || "basic",
        instance_id:  (moduleMeta && moduleMeta.instance_id)  || "",
      },
      instances: instances || [],

      get instanceLabel() {
        const inst = this.instances.find((i) => i.id === this.settings.instance_id);
        return inst ? `${inst.display_name} (${inst.image_tag})` : "No instance";
      },

      init() {
        this.csrf = window.getCsrfToken ? window.getCsrfToken() : "";
        const wrapper = document.getElementById("cm-wrapper");
        if (!wrapper) return;
        this.editor = CodeMirror(wrapper, {
          value: "", mode: null, theme: "material-darker",
          lineNumbers: true, lineWrapping: false, indentUnit: 2, tabSize: 2, indentWithTabs: false,
          extraKeys: { "Ctrl-S": () => this.save(), "Cmd-S": () => this.save() },
        });
        this.editor.setSize("100%", "100%");
        this.editor.on("change", () => { if (this.activeFileId) this.isDirty = true; });
        this.$nextTick(() => {
          if (this.editor) this.editor.refresh();
          const sw = document.getElementById("cm-schema-wrapper");
          if (!sw) return;
          let initialSchema = SCHEMA_PLACEHOLDER;
          if (existingSchema !== null && existingSchema !== undefined) {
            try {
              initialSchema = typeof existingSchema === "string"
                ? existingSchema
                : JSON.stringify(existingSchema, null, 2);
            } catch (_) {}
          }
          this.schemaEditor = CodeMirror(sw, {
            value: initialSchema, mode: "javascript", theme: "material-darker",
            lineNumbers: true, lineWrapping: false, indentUnit: 2, tabSize: 2, indentWithTabs: false,
            extraKeys: { "Ctrl-S": () => this.save(), "Cmd-S": () => this.save() },
          });
          this.schemaEditor.setSize("100%", "100%");
          this.schemaEditor.on("change", () => { this.isDirty = true; this.schemaError = ""; });

          const pw = document.getElementById("cm-pipeline-wrapper");
          if (!pw) return;
          let initialPipeline = PIPELINE_PLACEHOLDER;
          if (existingPipeline !== null && existingPipeline !== undefined) {
            try {
              initialPipeline = typeof existingPipeline === "string"
                ? existingPipeline
                : JSON.stringify(existingPipeline, null, 2);
            } catch (_) {}
          }
          this.pipelineEditor = CodeMirror(pw, {
            value: initialPipeline, mode: "javascript", theme: "material-darker",
            lineNumbers: true, lineWrapping: false, indentUnit: 2, tabSize: 2, indentWithTabs: false,
            extraKeys: { "Ctrl-S": () => this.save(), "Cmd-S": () => this.save() },
          });
          this.pipelineEditor.setSize("100%", "100%");
          this.pipelineEditor.on("change", () => { this.isDirty = true; this.pipelineError = ""; });
        });
      },

      // Switches tabs and refreshes CodeMirror when it becomes visible (fixes hidden-element sizing).
      switchTab(tab) {
        this.editorTab = tab;
        this.$nextTick(() => {
          if (tab === "code" && this.editor) this.editor.refresh();
          if (tab === "schema" && this.schemaEditor) this.schemaEditor.refresh();
          if (tab === "pipeline" && this.pipelineEditor) this.pipelineEditor.refresh();
        });
      },

      async loadFileContent({ fileId, filename }) {
        this.activeFileId = fileId;
        this.activeFilename = filename;
        this.isDirty = false;
        if (!fileId) { if (this.editor) this.editor.setValue(""); return; }
        const resp = await fetch(`/admin/modules/${this.moduleId}/files/${fileId}`, {
          headers: { "X-CSRF-Token": this.csrf },
        });
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
          if (this.editorTab === "schema")        await this._saveSchema();
          else if (this.editorTab === "pipeline") await this._savePipeline();
          else if (this.editorTab === "settings") await this._saveSettings();
          else await this._saveFile();
        } finally { this.saving = false; }
      },

      async _saveFile() {
        if (!this.activeFileId || !this.editor) return;
        const resp = await fetch(`/admin/modules/${this.moduleId}/files/${this.activeFileId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify({ content: this.editor.getValue() }),
        });
        this.isDirty = !resp.ok;
        this._setFlash(resp.ok ? "Saved." : "Save failed.");
      },

      async _saveSchema() {
        const raw = (this.schemaEditor && this.schemaEditor.getValue()) || "";
        try {
          const parsed = JSON.parse(raw);
          if (!Array.isArray(parsed)) throw new Error("Schema must be a JSON array");
          this.schemaError = "";
        } catch (e) { this.schemaError = e.message; return; }
        const resp = await fetch(`/admin/modules/${this.moduleId}/options-schema`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify({ schema: raw }),
        });
        if (resp.ok) { this.isDirty = false; this._setFlash("Parameters saved."); }
        else { const d = await resp.json().catch(() => ({})); this._setFlash(d.error || "Save failed."); }
      },

      async _savePipeline() {
        const raw = (this.pipelineEditor && this.pipelineEditor.getValue().trim()) || "";
        if (raw) {
          try {
            const parsed = JSON.parse(raw);
            if (!parsed.steps || !Array.isArray(parsed.steps)) throw new Error("Pipeline must have a 'steps' array");
            this.pipelineError = "";
          } catch (e) { this.pipelineError = e.message; return; }
        }
        const resp = await fetch(`/admin/modules/${this.moduleId}/pipeline`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify({ pipeline: raw }),
        });
        if (resp.ok) { this.isDirty = false; this._setFlash("Pipeline saved."); }
        else { const d = await resp.json().catch(() => ({})); this.pipelineError = d.error || ""; this._setFlash(d.error || "Save failed."); }
      },

      async _saveSettings() {
        this.settingsError = "";
        if (!this.settings.display_name.trim()) { this.settingsError = "Display name is required."; return; }
        const resp = await fetch(`/admin/modules/${this.moduleId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
          body: JSON.stringify(this.settings),
        });
        const d = await resp.json().catch(() => ({}));
        if (resp.ok) { this.isDirty = false; this._setFlash("Settings saved."); }
        else { this.settingsError = d.error || "Save failed."; this._setFlash("Save failed."); }
      },

      async toggleEnabled() {
        const resp = await fetch(`/admin/modules/${this.moduleId}/toggle`, {
          method: "POST",
          headers: { "X-CSRF-Token": this.csrf },
        }).catch(() => null);
        if (resp && resp.ok) window.location.reload();
        else this._setFlash("Toggle failed.");
      },

      async deleteModule() {
        this.deleting = true;
        this.deleteError = "";
        const resp = await fetch(`/admin/modules/${this.moduleId}`, {
          method: "DELETE",
          headers: { "X-CSRF-Token": this.csrf },
        }).catch(() => null);
        if (resp && resp.ok) {
          window.location.href = "/admin/modules/";
          return;
        }
        const d = resp ? await resp.json().catch(() => ({})) : {};
        this.deleteError = d.error || "Delete failed.";
        this.deleting = false;
      },

      openTestDialog() {
        this.resetTestDialog();
        this.testDialogOpen = true;
      },

      resetTestDialog() {
        clearTimeout(this._testPollTimer);
        this.testFile = null;
        this.testRunning = false;
        this.testRunId = null;
        this.testStatus = "";
        this.testResult = null;
        this.testErrorMessage = "";
        this.testError = "";
        if (this.$refs.testFileInput) this.$refs.testFileInput.value = "";
      },

      onTestFileChange(event) {
        this.testFile = event.target.files[0] || null;
      },

      async runTest() {
        if (!this.testFile || !this.settings.instance_id) return;
        this.testRunning = true;
        this.testError = "";
        try {
          const fd = new FormData();
          fd.append("file", this.testFile);
          const uploadResp = await fetch(`/admin/modules/${this.moduleId}/test/upload`, {
            method: "POST",
            headers: { "X-CSRF-Token": this.csrf },
            body: fd,
          });
          const uploadData = await uploadResp.json().catch(() => ({}));
          if (!uploadResp.ok) { this.testError = uploadData.error || "Upload failed."; return; }

          const runResp = await fetch(`/admin/modules/${this.moduleId}/test/run`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrf },
            body: JSON.stringify({ s3_key: uploadData.s3_key }),
          });
          const runData = await runResp.json().catch(() => ({}));
          if (!runResp.ok) { this.testError = runData.error || "Failed to start test."; return; }

          this.testRunId = runData.run_id;
          this.testStatus = "queued";
          this._pollTestStatus();
        } finally {
          this.testRunning = false;
        }
      },

      _pollTestStatus() {
        this._testPollTimer = setTimeout(async () => {
          if (!this.testRunId) return;
          const resp = await fetch(`/admin/modules/${this.moduleId}/test/${this.testRunId}`, {
            headers: { "X-CSRF-Token": this.csrf },
          }).catch(() => null);
          if (!resp || !resp.ok) { this._pollTestStatus(); return; }
          const data = await resp.json().catch(() => ({}));
          this.testStatus = data.status || "";
          if (data.status === "completed" || data.status === "failed") {
            this.testErrorMessage = data.error_message || "";
            this.testResult = data.result || null;
            return;
          }
          this._pollTestStatus();
        }, 2000);
      },

      _setFlash(msg) {
        clearTimeout(this._flashTimer);
        this.flash = msg;
        this._flashTimer = setTimeout(() => { this.flash = ""; }, 4000);
      },
    };
  });
});
