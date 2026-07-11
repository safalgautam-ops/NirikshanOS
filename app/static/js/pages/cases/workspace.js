// Page-specific JS for cases/detail.html — the Analyze workspace.
// Registers the analyzeWorkspace Alpine component and all its helpers.
// Must be loaded BEFORE alpine.min.js in the HTML (via {% block scripts %}).

document.addEventListener("alpine:init", () => {
  const EVIDENCE_TYPE_LABELS = {
    generic: "Generic / Any File",
    binary: "Binary / Executable",
    pcap: "PCAP / Network Capture",
    email: "EML / Email File",
    image: "Image Forensics",
    audio: "Audio Forensics",
    video: "Video Forensics",
    memory: "Memory Dump",
    disk: "Disk Image",
    document: "Document / PDF / Office",
    archive: "Archive File",
    mobile: "Mobile / APK",
    logs: "Logs / EVTX / System Logs",
    unknown: "Unknown File",
  };

  const EVIDENCE_TYPE_EXTENSIONS = {
    binary: ["exe", "dll", "elf", "bin", "so", "sys", "macho", "o"],
    pcap: ["pcap", "pcapng", "cap"],
    email: ["eml", "msg", "mbox"],
    image: ["jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"],
    audio: ["wav", "mp3", "flac", "m4a", "ogg", "aac"],
    video: ["mp4", "mov", "avi", "mkv", "webm"],
    memory: ["mem", "vmem", "dmp", "lime", "raw"],
    disk: ["img", "dd", "e01", "aff", "vmdk", "qcow2", "iso"],
    document: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "rtf", "odt"],
    archive: ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"],
    mobile: ["apk", "aab", "dex", "jar", "ipa"],
    logs: ["evtx", "log", "jsonl", "syslog"],
    generic: ["txt", "csv", "json", "xml", "ini", "cfg", "dat", "plist", "db", "sqlite", "html", "htm", "md", "yaml", "yml"],
  };

  const EXT_TO_EVIDENCE_TYPE = {};
  Object.entries(EVIDENCE_TYPE_EXTENSIONS).forEach(([type, exts]) => {
    exts.forEach((ext) => { EXT_TO_EVIDENCE_TYPE[ext] = type; });
  });

  const MODULE_MAP = {};

  const MODULE_TIER_LABELS = {
    basic_triage: "Basic Triage Bundle",
    standard: "Standard Modules",
    advanced: "Advanced Modules",
    network: "Network Modules",
    email: "Email Modules",
    memory: "Memory Modules",
  };
  const MODULE_TIER_ORDER = Object.keys(MODULE_TIER_LABELS);

  function moduleTierOf(module) {
    if (module.tier) return module.tier;
    if (module.category === "pcap") return "network";
    if (module.category === "email") return "email";
    if (module.category === "memory") return "memory";
    if (module.category === "generic") return "basic_triage";
    return "standard";
  }

  const PLAN_ORDER = ["free", "analyst", "advanced"];
  function requiredPlanOf(module) {
    if (module.required_plan) return module.required_plan;
    const tier = moduleTierOf(module);
    if (tier === "advanced") return "advanced";
    return "free";
  }
  function isModuleLocked(module, userPlan) {
    const plan = (userPlan || "free").toLowerCase();
    return PLAN_ORDER.indexOf(requiredPlanOf(module)) > PLAN_ORDER.indexOf(plan);
  }

  function severityOfModule(module) {
    return (module && module.riskLevel) || "Medium";
  }
  function confidenceOfModule(module) {
    return module && module.isolationLevel && module.isolationLevel !== "None" ? "High" : "Medium";
  }

  function formatTimelineTimestamp(ms) {
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    return (
      d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
      " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds())
    );
  }

  const DEFAULT_REPORT_MARKDOWN = `# Executive Summary

Write the investigation summary here.

## Key Findings

Saved findings will appear here after the analyst inserts or creates findings from analysis results.

## IOCs

Saved indicators of compromise will appear here after the analyst inserts saved IOCs.

## Incident Timeline

Selected timeline events will appear here.

## Recommendations

Write recommended actions here.

## Appendix

Add supporting evidence references, screenshots, artifacts, and raw output references here.`;

  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function inlineMd(s) {
    let out = escapeHtml(s);
    out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/!\[([^\]]*)\]\((\S+?)\)/g, '<img src="$2" alt="$1">');
    out = out.replace(/\[([^\]]*)\]\((\S+?)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    return out;
  }
  function renderMarkdownToHtml(md) {
    const lines = (md || "").split("\n");
    let html = "";
    let paragraph = [];
    const flushParagraph = () => {
      if (!paragraph.length) return;
      html += "<p>" + paragraph.map((l, idx) =>
        inlineMd(l.replace(/ {2}$/, "")) + (idx < paragraph.length - 1 ? (l.endsWith("  ") ? "<br>" : " ") : "")
      ).join("") + "</p>";
      paragraph = [];
    };
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (/^###\s+/.test(line)) { flushParagraph(); html += "<h3>" + inlineMd(line.replace(/^###\s+/, "")) + "</h3>"; i++; continue; }
      if (/^##\s+/.test(line))  { flushParagraph(); html += "<h2>" + inlineMd(line.replace(/^##\s+/, "")) + "</h2>";  i++; continue; }
      if (/^#\s+/.test(line))   { flushParagraph(); html += "<h1>" + inlineMd(line.replace(/^#\s+/, "")) + "</h1>";   i++; continue; }
      if (line.trim().startsWith("|")) {
        flushParagraph();
        const tableLines = [];
        while (i < lines.length && lines[i].trim().startsWith("|")) { tableLines.push(lines[i]); i++; }
        const rows = tableLines.map((l) =>
          l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim())
        );
        const isSep = (cells) => cells.every((c) => /^-+$/.test(c));
        let bodyRows = rows, headRow = null;
        if (rows.length > 1 && isSep(rows[1])) { headRow = rows[0]; bodyRows = rows.slice(2); }
        html += "<table>";
        if (headRow) html += "<thead><tr>" + headRow.map((c) => "<th>" + inlineMd(c) + "</th>").join("") + "</tr></thead>";
        html += "<tbody>" + bodyRows.map((r) => "<tr>" + r.map((c) => "<td>" + inlineMd(c) + "</td>").join("") + "</tr>").join("") + "</tbody>";
        html += "</table>";
        continue;
      }
      if (line.trim() === "") { flushParagraph(); i++; continue; }
      paragraph.push(line);
      i++;
    }
    flushParagraph();
    return html;
  }

  function _toFrontendStatus(backendStatus) {
    return ({ queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Failed" }[backendStatus] || "Queued");
  }
  function _statusToProgress(frontendStatus) {
    if (frontendStatus === "Completed" || frontendStatus === "Failed") return 100;
    if (frontendStatus === "Running") return 50;
    return 0;
  }
  async function _fetchTaskOutput(taskId) {
    try {
      const resp = await fetch(`/analysis/tasks/${taskId}/output`);
      if (!resp.ok) return { stdout: [], stderr: [] };
      const data = await resp.json();
      return {
        stdout: (data.stdout || "").split("\n").filter(Boolean),
        stderr: (data.stderr || "").split("\n").filter(Boolean),
      };
    } catch { return { stdout: [], stderr: [] }; }
  }
  function _formatSummary(summary) {
    if (!summary || typeof summary !== "object") return summary || "";
    return Object.entries(summary)
      .filter(([, v]) => v !== null && v !== undefined && v !== "")
      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
      .join("\n");
  }

  Alpine.data(
    "analyzeWorkspace",
    (evidenceItems, userPlan, caseId, caseTitle, currentUserName, csrfToken) => ({
      moduleMap: MODULE_MAP,
      evidenceTypeLabels: EVIDENCE_TYPE_LABELS,
      moduleTierLabels: MODULE_TIER_LABELS,
      userPlan: (userPlan || "free").toLowerCase(),
      _modulesByEvidence: {},
      modulesLoading: false,
      evidence: evidenceItems || [],
      caseId: caseId || null,
      currentUserName: currentUserName || "Analyst",
      csrfToken: csrfToken || "",
      analyzingEvidence: null,
      moduleQuery: "",
      tierFilter: "all",
      checkedModuleIds: [],
      selectedModule: null,
      moduleOptionsByModule: {},
      lockedModule: null,
      queue: [],
      activeProgressJobIds: [],
      results: [],
      resultSearch: "",
      resultsFilterStatus: "all",
      resultsFilterType: "all",
      resultsFilterModule: "all",
      canvasEvidenceId: null,
      canvasEvidenceName: "",
      canvasSelectedModuleId: null,
      canvasTab: "overview",
      canvasNoteDraft: "",
      notesByKey: {},
      savedIndicatorKeys: [],
      indicators: [],
      caseFindings: [],
      timelineEvents: [],
      canvasFlash: "",
      noteContent: "",
      noteFlash: "",
      _noteFlashTimer: null,
      report: {
        id: "report_001",
        caseId: caseId || null,
        title: (caseTitle ? caseTitle + " " : "") + "Investigation Report",
        visibility: "personal_draft",
        status: "draft",
        version: "0.1",
        createdBy: currentUserName || "Analyst",
        updatedBy: currentUserName || "Analyst",
        markdownContent: DEFAULT_REPORT_MARKDOWN,
        includedFindingIds: [],
        includedIocIds: [],
        includedTimelineEventIds: [],
      },
      reportFlash: "",
      _pollKey: null,

      init() {
        this._analyzeHandler = (e) => this.openAnalyzeDialog(e.detail);
        window.addEventListener("analyze-evidence", this._analyzeHandler);
        if (this.caseId) {
          this.evidence.forEach((ev) => this._loadResultsFromBackend(ev.id));
          this._loadFindingsFromBackend();
          this._loadIndicatorsFromBackend();
          this._loadReportFromBackend();
          this._loadNoteFromBackend();
        }
      },

      destroy() {
        window.removeEventListener("analyze-evidence", this._analyzeHandler);
      },

      evidenceTypeOf(item) {
        const ext = (item.filename || "").toLowerCase().split(".").pop();
        return EXT_TO_EVIDENCE_TYPE[ext] || "unknown";
      },

      evidenceTypeLabelOf(item) {
        return this.evidenceTypeLabels[this.evidenceTypeOf(item)];
      },

      formatBytes(bytes) {
        return evidenceFormatBytes(bytes);
      },

      openAnalyzeDialog(item) {
        const idx = this.evidence.findIndex((e) => e.id === item.id);
        if (idx === -1) this.evidence.push(item);
        else this.evidence[idx] = item;
        this.analyzingEvidence = item;
        this.moduleQuery = "";
        this.tierFilter = "all";
        this.checkedModuleIds = [];
        this.selectedModule = null;
        this._fetchModulesForEvidence(item.id);
        const dialog = document.getElementById("analyze-evidence-dialog");
        if (dialog) { dialog.dataset.state = "open"; if (!dialog.open) dialog.showModal(); }
      },

      async _fetchModulesForEvidence(evidenceId) {
        if (this._modulesByEvidence[evidenceId]) return;
        this.modulesLoading = true;
        try {
          const resp = await fetch(`/cases/${this.caseId}/evidence/${evidenceId}/modules`, {
            headers: { "X-CSRF-Token": this.csrfToken },
          });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          const modules = data.modules || [];
          modules.forEach((m) => { MODULE_MAP[m.id] = m; });
          this._modulesByEvidence[evidenceId] = modules;
        } catch (_) {
          this._modulesByEvidence[evidenceId] = [];
        } finally {
          this.modulesLoading = false;
        }
      },

      closeAnalyzeDialog() {
        const dialog = document.getElementById("analyze-evidence-dialog");
        if (dialog) { dialog.dataset.state = "closed"; if (dialog.open) dialog.close(); }
      },

      compatibleModules() {
        if (!this.analyzingEvidence) return [];
        return this._modulesByEvidence[this.analyzingEvidence.id] || [];
      },

      compatibleModuleGroups() {
        const q = this.moduleQuery.trim().toLowerCase();
        const filtered = this.compatibleModules().filter((m) => {
          if (this.tierFilter !== "all" && moduleTierOf(m) !== this.tierFilter) return false;
          if (q && !m.name.toLowerCase().includes(q)) return false;
          return true;
        });
        const groups = [];
        MODULE_TIER_ORDER.forEach((tier) => {
          const mods = filtered.filter((m) => moduleTierOf(m) === tier);
          if (mods.length) groups.push({ tier, label: MODULE_TIER_LABELS[tier], modules: mods });
        });
        return groups;
      },

      availableTiers() {
        const tiers = new Set(this.compatibleModules().map((m) => moduleTierOf(m)));
        return MODULE_TIER_ORDER.filter((t) => tiers.has(t));
      },

      isModuleLocked(moduleId) { return isModuleLocked(this.moduleMap[moduleId], this.userPlan); },
      requiredPlanOf(moduleId) { return requiredPlanOf(this.moduleMap[moduleId]); },
      isBatchable(moduleId) { return moduleTierOf(this.moduleMap[moduleId]) === "basic_triage"; },

      openUpgradeDialog(moduleId) {
        this.lockedModule = this.moduleMap[moduleId];
        const dialog = document.getElementById("upgrade-plan-dialog");
        if (dialog) { dialog.dataset.state = "open"; if (!dialog.open) dialog.showModal(); }
      },

      ensureOptions(moduleId) {
        if (this.moduleOptionsByModule[moduleId]) return;
        const mod = this.moduleMap[moduleId];
        const opts = {};
        mod.fields.forEach((f) => { opts[f.key] = Array.isArray(f.default) ? [...f.default] : f.default; });
        this.moduleOptionsByModule[moduleId] = opts;
      },

      toggleModuleChecked(moduleId) {
        if (this.isModuleLocked(moduleId)) { this.openUpgradeDialog(moduleId); return; }
        const idx = this.checkedModuleIds.indexOf(moduleId);
        if (idx === -1) { this.checkedModuleIds.push(moduleId); this.selectModuleForConfig(moduleId); }
        else { this.checkedModuleIds.splice(idx, 1); if (this.selectedModule === moduleId) this.selectedModule = this.checkedModuleIds[0] || null; }
      },

      isModuleChecked(moduleId) { return this.checkedModuleIds.includes(moduleId); },

      selectModuleForConfig(moduleId) {
        if (this.isModuleLocked(moduleId)) { this.openUpgradeDialog(moduleId); return; }
        this.selectedModule = moduleId;
        this.ensureOptions(moduleId);
      },

      toggleChecklistValue(moduleId, fieldKey, value) {
        const list = this.moduleOptionsByModule[moduleId][fieldKey] || [];
        const idx = list.indexOf(value);
        if (idx === -1) list.push(value); else list.splice(idx, 1);
        this.moduleOptionsByModule[moduleId][fieldKey] = list;
      },

      optionsSummaryFor(moduleId) {
        const mod = this.moduleMap[moduleId];
        const opts = this.moduleOptionsByModule[moduleId] || {};
        return mod.fields.map((f) => {
          const v = opts[f.key];
          const val = Array.isArray(v) ? v.join("/") : typeof v === "boolean" ? (v ? "Yes" : "No") : v;
          return f.label + ": " + val;
        }).join(", ");
      },

      planSummary() {
        const mods = this.checkedModuleIds.map((id) => this.moduleMap[id]).filter(Boolean);
        const batchGroups = new Set();
        let containers = 0;
        mods.forEach((m) => {
          if (m.batchable && m.batch_group) batchGroups.add(m.batch_group);
          else containers++;
        });
        return {
          moduleCount: mods.length,
          taskCount: mods.length,
          containerRuns: containers + batchGroups.size,
          estimatedMinutes: mods.length === 0 ? 0 : Math.max(2, mods.length * 2),
        };
      },

      async startAnalysis() {
        if (!this.checkedModuleIds.length || !this.analyzingEvidence) return;
        const evidence = this.analyzingEvidence;
        const moduleOptions = {};
        this.checkedModuleIds.forEach((id) => {
          if (this.moduleOptionsByModule[id]) moduleOptions[id] = this.moduleOptionsByModule[id];
        });
        let data;
        try {
          const resp = await fetch(`/cases/${this.caseId}/evidence/${evidence.id}/analyze`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrfToken },
            body: JSON.stringify({ module_ids: this.checkedModuleIds, module_options: moduleOptions }),
          });
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            alert(err.error || `Analysis request failed (${resp.status})`);
            return;
          }
          data = await resp.json();
        } catch (e) { console.error("[analyze] network error", e); return; }

        const newJobIds = [];
        (data.jobs || []).forEach((serverJob) => {
          newJobIds.push(serverJob.job_id);
          this.queue.push({
            id: serverJob.job_id,
            evidenceId: evidence.id,
            evidenceName: evidence.filename,
            tasks: (serverJob.tasks || []).map((t) => {
              const mod = this.moduleMap[t.module_id] || {};
              return {
                id: t.task_id, moduleId: t.module_id, moduleName: t.module_name,
                tool: mod.tool || "", outputType: mod.outputType || "",
                risk: mod.riskLevel || "", isolation: mod.isolationLevel || "",
                summary: this.moduleOptionsByModule[t.module_id] ? this.optionsSummaryFor(t.module_id) : "",
                status: "Queued", progress: 0,
              };
            }),
          });
        });
        this.activeProgressJobIds = newJobIds;
        this.closeAnalyzeDialog();
        const queueDialog = document.getElementById("current-job-queue");
        if (queueDialog) { queueDialog.dataset.state = "open"; if (!queueDialog.open) queueDialog.showModal(); }
        this._startPolling();
      },

      progressJobs() {
        return this.queue.filter((j) => this.activeProgressJobIds.includes(j.id));
      },

      _startPolling() {
        if (this._pollKey !== null) return;
        this._pollKey = setInterval(() => this._doPoll(), 2000);
      },

      _stopPolling() {
        if (this._pollKey !== null) { clearInterval(this._pollKey); this._pollKey = null; }
      },

      async _doPoll() {
        const activeJobs = this.queue.filter((j) => j.tasks.some((t) => t.status === "Queued" || t.status === "Running"));
        if (!activeJobs.length) { this._stopPolling(); return; }
        const evidenceIds = [...new Set(activeJobs.map((j) => j.evidenceId))];
        for (const evidenceId of evidenceIds) {
          try {
            const resp = await fetch(`/cases/${this.caseId}/evidence/${evidenceId}/jobs`);
            if (!resp.ok) continue;
            const data = await resp.json();
            await this._applyPollData(data.jobs || []);
          } catch (e) { console.error("[poll] error fetching job status", e); }
        }
      },

      async _applyPollData(serverJobs) {
        let changed = false;
        for (const serverJob of serverJobs) {
          const queueJob = this.queue.find((j) => j.id === serverJob.id);
          if (!queueJob) continue;
          for (const serverTask of serverJob.tasks) {
            const queueTask = queueJob.tasks.find((t) => t.id === serverTask.id);
            if (!queueTask) continue;
            const prev = queueTask.status;
            const next = _toFrontendStatus(serverTask.status);
            if (prev === next) continue;
            queueTask.status = next;
            queueTask.progress = _statusToProgress(next);
            changed = true;
            if (next === "Completed" && prev !== "Completed") {
              const output = await _fetchTaskOutput(serverTask.id);
              this.results = this.results.filter((r) => r.id !== serverTask.id);
              this.results.push({
                id: serverTask.id, evidenceId: queueJob.evidenceId, evidenceName: queueJob.evidenceName,
                moduleId: queueTask.moduleId, moduleName: queueTask.moduleName,
                tool: queueTask.tool, outputType: queueTask.outputType,
                risk: queueTask.risk, isolation: queueTask.isolation, summary: queueTask.summary,
                completedAt: Date.now(), findings: [], iocs: [], artifacts: [], rawOutput: output,
              });
            } else if (next === "Failed" && prev !== "Failed") {
              this.results = this.results.filter((r) => r.id !== serverTask.id);
              this.results.push({
                id: serverTask.id, evidenceId: queueJob.evidenceId, evidenceName: queueJob.evidenceName,
                moduleId: queueTask.moduleId, moduleName: queueTask.moduleName,
                tool: queueTask.tool, outputType: queueTask.outputType,
                risk: queueTask.risk, isolation: queueTask.isolation, summary: queueTask.summary,
                completedAt: Date.now(), failed: true,
                findings: [], iocs: [], artifacts: [],
                rawOutput: { stdout: [], stderr: [serverTask.error_message || "Analysis failed — check worker logs."] },
              });
            }
          }
        }
        if (changed) this.queue = [...this.queue];
      },

      cancelTask(jobId, taskId) {
        const job = this.queue.find((j) => j.id === jobId);
        if (!job) return;
        job.tasks.forEach((task) => {
          if (task.status === "Failed" || task.status === "Completed") return;
          task.status = "Failed";
          this.results = this.results.filter((r) => r.id !== task.id);
          this.results.push({
            id: task.id, evidenceId: job.evidenceId, evidenceName: job.evidenceName,
            moduleId: task.moduleId, moduleName: task.moduleName,
            tool: task.tool, outputType: task.outputType, risk: task.risk,
            isolation: task.isolation, summary: task.summary,
            completedAt: Date.now(), failed: true,
            output: "Analysis cancelled before completion.",
            findings: [], iocs: [], artifacts: [],
            rawOutput: { stdout: [], stderr: ["[" + task.tool + "] analysis cancelled by analyst."] },
          });
        });
        this.queue = [...this.queue];
        fetch(`/analysis/jobs/${jobId}/cancel`, { method: "POST", headers: { "X-CSRF-Token": this.csrfToken } }).catch(() => {});
      },

      deleteTaskRow(jobId, taskId) {
        const job = this.queue.find((j) => j.id === jobId);
        if (job) {
          job.tasks = job.tasks.filter((t) => t.id !== taskId);
          if (!job.tasks.length) this.queue = this.queue.filter((j) => j.id !== jobId);
        }
        this.results = this.results.filter((r) => r.id !== taskId);
      },

      openResultCanvas() {
        const jobs = this.progressJobs();
        if (!jobs.length) return;
        const queueDialog = document.getElementById("current-job-queue");
        if (queueDialog) { queueDialog.dataset.state = "closed"; if (queueDialog.open) queueDialog.close(); }
        this.openResultCanvasFor(jobs[0].evidenceId);
      },

      resultRowsRaw() {
        const byEvidence = {};
        const ensure = (id, name) =>
          byEvidence[id] || (byEvidence[id] = { evidenceId: id, evidenceName: name, completed: 0, running: 0, failed: 0, moduleIds: new Set() });
        this.results.forEach((r) => {
          const g = ensure(r.evidenceId, r.evidenceName);
          g.moduleIds.add(r.moduleId);
          if (r.failed) g.failed += 1; else g.completed += 1;
        });
        this.queue.forEach((job) => {
          job.tasks.forEach((t) => {
            if (t.status === "Failed") return;
            const g = ensure(job.evidenceId, job.evidenceName);
            g.moduleIds.add(t.moduleId);
            if (t.status === "Running" || t.status === "Queued") g.running += 1;
          });
        });
        return Object.values(byEvidence);
      },

      resultRows() {
        const q = this.resultSearch.trim().toLowerCase();
        return this.resultRowsRaw().filter((row) => {
          if (q && !row.evidenceName.toLowerCase().includes(q)) return false;
          const item = this.evidence.find((e) => e.id === row.evidenceId);
          const type = item ? this.evidenceTypeOf(item) : null;
          if (this.resultsFilterType !== "all" && type !== this.resultsFilterType) return false;
          if (this.resultsFilterModule !== "all" && !row.moduleIds.has(this.resultsFilterModule)) return false;
          if (this.resultsFilterStatus === "completed" && !row.completed) return false;
          if (this.resultsFilterStatus === "running" && !row.running) return false;
          if (this.resultsFilterStatus === "failed" && !row.failed) return false;
          return true;
        }).map((row) => {
          const item = this.evidence.find((e) => e.id === row.evidenceId);
          return { ...row, evidenceTypeLabel: item ? this.evidenceTypeLabelOf(item) : "—", actionLabel: row.completed > 0 || row.failed > 0 ? "Open Canvas" : "View Jobs" };
        });
      },

      availableResultTypes() {
        const types = new Set();
        this.resultRowsRaw().forEach((row) => {
          const item = this.evidence.find((e) => e.id === row.evidenceId);
          if (item) types.add(this.evidenceTypeOf(item));
        });
        return Array.from(types).map((t) => ({ value: t, label: this.evidenceTypeLabels[t] || t }));
      },

      availableResultModules() {
        const ids = new Set();
        this.resultRowsRaw().forEach((row) => row.moduleIds.forEach((id) => ids.add(id)));
        return Array.from(ids).map((id) => this.moduleMap[id]).filter(Boolean).sort((a, b) => a.name.localeCompare(b.name));
      },

      openJobsForEvidence(evidenceId) {
        this.activeProgressJobIds = this.queue.filter((j) => j.evidenceId === evidenceId).map((j) => j.id);
        const dialog = document.getElementById("current-job-queue");
        if (dialog) { dialog.dataset.state = "open"; if (!dialog.open) dialog.showModal(); }
      },

      async openResultCanvasFor(evidenceId) {
        const item = this.evidence.find((e) => e.id === evidenceId);
        const row = this.resultRowsRaw().find((r) => r.evidenceId === evidenceId);
        this.canvasEvidenceId = evidenceId;
        this.canvasEvidenceName = item ? item.filename : (row ? row.evidenceName : "");
        await this._fetchModulesForEvidence(evidenceId);
        await this._fetchNotesForEvidence(evidenceId);
        await this._loadResultsFromBackend(evidenceId);
        const outputs = this.canvasModuleOutputs();
        const preferred = outputs.find((o) => o.status === "completed" || o.status === "failed") || outputs[0] || null;
        this.selectCanvasModule(preferred ? preferred.moduleId : null);
        const dialog = document.getElementById("result-canvas-dialog");
        if (dialog) { dialog.dataset.state = "open"; if (!dialog.open) dialog.showModal(); }
      },

      closeResultCanvas() {
        const dialog = document.getElementById("result-canvas-dialog");
        if (dialog) { dialog.dataset.state = "closed"; if (dialog.open) dialog.close(); }
      },

      canvasModuleOutputs() {
        if (!this.canvasEvidenceId) return [];
        const item = this.evidence.find((e) => e.id === this.canvasEvidenceId);
        const compatible = this._modulesByEvidence[this.canvasEvidenceId] || [];
        const taskByModule = {};
        this.queue.forEach((job) => {
          if (job.evidenceId !== this.canvasEvidenceId) return;
          job.tasks.forEach((t) => { taskByModule[t.moduleId] = t; });
        });
        const resultByModule = {};
        this.results.forEach((r) => { if (r.evidenceId === this.canvasEvidenceId) resultByModule[r.moduleId] = r; });
        const statusOrder = { running: 0, queued: 1, failed: 2, completed: 3, not_run: 4 };
        return compatible.map((m) => {
          const result = resultByModule[m.id];
          const task = taskByModule[m.id];
          let status = "not_run", progress = 0;
          if (result) { status = result.failed ? "failed" : "completed"; progress = 100; }
          else if (task) { status = task.status === "Running" ? "running" : "queued"; progress = task.progress; }
          return { moduleId: m.id, moduleName: m.name, tool: m.tool, tier: moduleTierOf(m), status, progress };
        }).sort((a, b) => statusOrder[a.status] - statusOrder[b.status] || a.moduleName.localeCompare(b.moduleName));
      },

      canvasModuleGroups() {
        const outputs = this.canvasModuleOutputs();
        const groups = [];
        MODULE_TIER_ORDER.forEach((tier) => {
          const mods = outputs.filter((o) => o.tier === tier);
          if (mods.length) groups.push({ tier, label: MODULE_TIER_LABELS[tier], modules: mods });
        });
        return groups;
      },

      selectCanvasModule(moduleId) {
        this.canvasSelectedModuleId = moduleId;
        this.canvasTab = "overview";
        this.canvasNoteDraft = moduleId ? (this.notesByKey[this.canvasNoteKeyFor(moduleId)] || "") : "";
      },

      canvasNoteKeyFor(moduleId) { return this.canvasEvidenceId + ":" + moduleId; },

      async saveCanvasNote() {
        if (!this.canvasSelectedModuleId) return;
        const moduleId = this.canvasSelectedModuleId;
        const body = this.canvasNoteDraft;
        if (!body.trim()) { this.flashCanvas("Note is empty."); return; }
        this.notesByKey[this.canvasNoteKeyFor(moduleId)] = body;
        this.flashCanvas("Note saved.");
        fetch(`/cases/${this.caseId}/evidence/${this.canvasEvidenceId}/notes/${encodeURIComponent(moduleId)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrfToken },
          body: JSON.stringify({ body }),
        }).catch(() => {});
      },

      async _fetchNotesForEvidence(evidenceId) {
        try {
          const resp = await fetch(`/cases/${this.caseId}/evidence/${evidenceId}/notes`, { headers: { "X-CSRF-Token": this.csrfToken } });
          if (!resp.ok) return;
          const data = await resp.json();
          Object.entries(data.notes || {}).forEach(([moduleId, noteBody]) => {
            this.notesByKey[evidenceId + ":" + moduleId] = noteBody;
          });
        } catch (_) {}
      },

      canvasSelectedOutput() {
        if (!this.canvasSelectedModuleId) return null;
        const meta = this.canvasModuleOutputs().find((o) => o.moduleId === this.canvasSelectedModuleId);
        if (!meta) return null;
        const result = this.results.find((r) => r.evidenceId === this.canvasEvidenceId && r.moduleId === this.canvasSelectedModuleId);
        return {
          moduleId: meta.moduleId, moduleName: meta.moduleName, tool: meta.tool,
          status: meta.status, progress: meta.progress,
          summary: result ? (result.parsedOutput || result.output || "") : "",
          findings: result ? result.findings : [],
          iocs: result ? result.iocs : [],
          artifacts: result ? result.artifacts : [],
          rawOutput: result ? result.rawOutput : { stdout: [], stderr: [] },
        };
      },

      async _loadResultsFromBackend(evidenceId) {
        try {
          const resp = await fetch(`/cases/${this.caseId}/evidence/${evidenceId}/results`);
          if (!resp.ok) return;
          const data = await resp.json();
          const seenModules = new Set();
          for (const job of data.jobs || []) {
            for (const task of job.tasks || []) {
              if (!task.result) continue;
              if (seenModules.has(task.module_id)) continue;
              seenModules.add(task.module_id);
              const rawOutput = task.result.raw_output || {};
              const parsedOutput = _formatSummary(task.result.summary);
              const iocs = task.result.iocs || [];
              const findings = task.result.findings || [];
              const artifacts = task.result.artifacts || [];
              this.results = this.results.filter((r) => !(r.evidenceId === evidenceId && r.moduleId === task.module_id));
              const raw = rawOutput.stdout_path ? await _fetchTaskOutput(task.task_id) : { stdout: [], stderr: [] };
              this.results.push({
                id: task.task_id, evidenceId, evidenceName: data.evidence ? data.evidence.filename : "",
                moduleId: task.module_id, moduleName: task.module_name,
                tool: "", outputType: "", risk: "", isolation: "", summary: "", parsedOutput,
                completedAt: Date.now(), failed: task.status === "failed",
                findings, iocs, artifacts, rawOutput: raw,
              });
            }
          }
        } catch (e) { console.error("[canvas] failed to load results from backend", e); }
      },

      copyRawOutput() {
        const output = this.canvasSelectedOutput();
        if (!output) return;
        const text = ["STDOUT", ...output.rawOutput.stdout, "", "STDERR", ...output.rawOutput.stderr].join("\n");
        navigator.clipboard?.writeText(text);
        this.flashCanvas("Copied to clipboard.");
      },

      downloadRawOutput() {
        const output = this.canvasSelectedOutput();
        if (!output) return;
        const text = ["STDOUT", ...output.rawOutput.stdout, "", "STDERR", ...output.rawOutput.stderr].join("\n");
        const blob = new Blob([text], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = this.canvasEvidenceName + "-" + output.moduleId + "-raw.txt";
        a.click();
        URL.revokeObjectURL(url);
      },

      reAnalyzeCurrentModule() {
        if (!this.canvasSelectedModuleId || !this.canvasEvidenceId) return;
        const mod = this.moduleMap[this.canvasSelectedModuleId];
        if (!mod) return;
        const item = this.evidence.find((e) => e.id === this.canvasEvidenceId);
        const evidenceName = this.canvasEvidenceName || (item && item.filename) || "";
        this.queue.forEach((job) => {
          if (job.evidenceId === this.canvasEvidenceId) job.tasks = job.tasks.filter((t) => t.moduleId !== mod.id);
        });
        this.queue = this.queue.filter((j) => j.tasks.length);
        this.results = this.results.filter((r) => !(r.evidenceId === this.canvasEvidenceId && r.moduleId === mod.id));
        this.ensureOptions(mod.id);
        const tier = moduleTierOf(mod);
        const jobId = this.canvasEvidenceId + ":" + tier + ":" + Date.now();
        this.queue.push({
          id: jobId, tier, tierLabel: MODULE_TIER_LABELS[tier],
          evidenceId: this.canvasEvidenceId, evidenceName,
          tasks: [{ id: jobId + ":" + mod.id, moduleId: mod.id, moduleName: mod.name, tool: mod.tool, outputType: mod.outputType, risk: mod.riskLevel, isolation: mod.isolationLevel, summary: this.optionsSummaryFor(mod.id), status: "Queued", progress: 0 }],
        });
        this.flashCanvas("Re-Analyze queued.");
      },

      exportCanvasEvidence() {
        const data = this.results.filter((r) => r.evidenceId === this.canvasEvidenceId);
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = (this.canvasEvidenceName || "evidence") + "-results.json";
        a.click();
        URL.revokeObjectURL(url);
      },

      flashCanvas(message) {
        this.canvasFlash = message;
        clearTimeout(this._canvasFlashTimer);
        this._canvasFlashTimer = setTimeout(() => { this.canvasFlash = ""; }, 2000);
      },

      indicatorsAddedForCurrent() {
        const output = this.canvasSelectedOutput();
        if (!output || !output.iocs.length) return false;
        return output.iocs.every((ioc) => this.savedIndicatorKeys.includes(ioc.type + ":" + ioc.value));
      },

      addIndicator() {
        const output = this.canvasSelectedOutput();
        if (!output || !output.iocs.length) return;
        const mod = this.moduleMap[output.moduleId];
        output.iocs.forEach((ioc) => {
          const key = ioc.type + ":" + ioc.value;
          if (this.savedIndicatorKeys.includes(key)) return;
          this.savedIndicatorKeys.push(key);
          this.indicators.push({
            id: this.canvasEvidenceId + ":" + output.moduleId + ":" + ioc.type + ":" + Date.now(),
            caseId: this.caseId, type: ioc.type, value: ioc.value,
            severity: severityOfModule(mod), confidence: confidenceOfModule(mod),
            sourceEvidence: this.canvasEvidenceName, sourceModule: output.moduleName, includedInReport: false,
          });
          fetch(`/cases/${this.caseId}/indicators`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrfToken },
            body: JSON.stringify({ evidence_id: this.canvasEvidenceId, module_id: output.moduleId, type: ioc.type, value: ioc.value, severity: severityOfModule(mod), confidence: confidenceOfModule(mod), source_evidence: this.canvasEvidenceName, source_module: output.moduleName }),
          }).catch(() => {});
        });
        this.flashCanvas("Indicator added.");
      },

      createFinding() {
        const output = this.canvasSelectedOutput();
        if (!output) return;
        const mod = this.moduleMap[output.moduleId];
        const note = this.canvasNoteDraft.trim();
        const description = note || output.findings.join(" ") || output.summary || "";
        if (!description) return;
        const title = note ? note.split("\n")[0].slice(0, 80) : (output.findings[0] || output.moduleName + " finding");
        const finding = {
          id: this.canvasEvidenceId + ":" + output.moduleId + ":" + Date.now(),
          caseId: this.caseId, title,
          severity: severityOfModule(mod), confidence: confidenceOfModule(mod),
          sourceEvidence: this.canvasEvidenceName, sourceModule: output.moduleName,
          description, includedInReport: false,
        };
        this.caseFindings.push(finding);
        fetch(`/cases/${this.caseId}/findings`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrfToken },
          body: JSON.stringify({ evidence_id: this.canvasEvidenceId, module_id: output.moduleId, title: finding.title, description: finding.description, severity: finding.severity, confidence: finding.confidence, source_evidence: finding.sourceEvidence, source_module: finding.sourceModule }),
        }).catch(() => {});
        this.flashCanvas("Finding created.");
      },

      addToTimeline() {
        const output = this.canvasSelectedOutput();
        if (!output) return;
        const mod = this.moduleMap[output.moduleId];
        const eventType = ({ network: "Network Event", email: "Email Event", memory: "Memory Event" }[mod ? moduleTierOf(mod) : ""] || "Analysis Event");
        const nowStr = new Date().toISOString().slice(0, 16);
        const tlTitle = output.moduleName + " completed on " + this.canvasEvidenceName;
        this.timelineEvents.push({
          id: this.canvasEvidenceId + ":" + output.moduleId + ":" + Date.now(),
          caseId: this.caseId, eventTime: formatTimelineTimestamp(Date.now()),
          title: tlTitle, eventType, source: this.canvasEvidenceName + " → " + output.moduleName,
          confidence: confidenceOfModule(mod), includedInReport: false,
        });
        fetch(`/cases/${this.caseId}/timeline/items/json`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrfToken },
          body: JSON.stringify({ type: "milestone", title: tlTitle, description: eventType + " detected via " + output.moduleName, timeline_time: nowStr, linked_evidence_id: this.canvasEvidenceId, linked_result_label: output.moduleName }),
        }).catch(() => {});
        this.flashCanvas("Added to timeline.");
      },

      addCurrentToReport() {
        const output = this.canvasSelectedOutput();
        if (!output || output.status !== "completed") return;
        const mod = this.moduleMap[output.moduleId];
        const finding = {
          id: this.canvasEvidenceId + ":" + output.moduleId + ":" + Date.now(),
          caseId: this.caseId, title: output.moduleName + " result",
          severity: severityOfModule(mod), confidence: confidenceOfModule(mod),
          sourceEvidence: this.canvasEvidenceName, sourceModule: output.moduleName,
          description: output.summary, includedInReport: true,
        };
        this.caseFindings.push(finding);
        this.insertFindingMarkdown(finding);
        this.report.includedFindingIds.push(finding.id);
        this.flashCanvas("Added to report.");
      },

      flashReport(message) {
        this.reportFlash = message;
        clearTimeout(this._reportFlashTimer);
        this._reportFlashTimer = setTimeout(() => { this.reportFlash = ""; }, 2000);
      },

      async saveDraft() {
        this.report.updatedBy = this.currentUserName;
        const resp = await fetch(`/cases/${this.caseId}/report`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrfToken },
          body: JSON.stringify({ content: this.report.markdownContent, title: this.report.title }),
        }).catch(() => null);
        this.flashReport(resp && resp.ok ? "Draft saved." : "Save failed.");
      },

      async _loadReportFromBackend() {
        try {
          const resp = await fetch(`/cases/${this.caseId}/report`);
          if (!resp.ok) return;
          const data = await resp.json();
          if (data.content) { this.report.markdownContent = data.content; if (data.title) this.report.title = data.title; }
        } catch (_) {}
      },

      async _loadFindingsFromBackend() {
        try {
          const resp = await fetch(`/cases/${this.caseId}/findings`);
          if (!resp.ok) return;
          const data = await resp.json();
          this.caseFindings = (data.findings || []).map((f) => ({
            id: f.id, caseId: this.caseId, title: f.title, description: f.description,
            severity: f.severity, confidence: f.confidence,
            sourceEvidence: f.source_evidence || "", sourceModule: f.source_module || "",
            includedInReport: false,
          }));
        } catch (_) {}
      },

      async _loadIndicatorsFromBackend() {
        try {
          const resp = await fetch(`/cases/${this.caseId}/indicators`);
          if (!resp.ok) return;
          const data = await resp.json();
          this.indicators = (data.indicators || []).map((i) => ({
            id: i.id, caseId: this.caseId, type: i.type, value: i.value,
            severity: i.severity, confidence: i.confidence,
            sourceEvidence: i.source_evidence || "", sourceModule: i.source_module || "",
            includedInReport: false,
          }));
        } catch (_) {}
      },

      async _loadNoteFromBackend() {
        try {
          const resp = await fetch(`/cases/${this.caseId}/note`);
          if (!resp.ok) return;
          const data = await resp.json();
          if (data.content) this.noteContent = data.content;
        } catch (_) {}
      },

      async saveNote() {
        const resp = await fetch(`/cases/${this.caseId}/note`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": this.csrfToken },
          body: JSON.stringify({ content: this.noteContent }),
        }).catch(() => null);
        clearTimeout(this._noteFlashTimer);
        this.noteFlash = resp && resp.ok ? "Saved." : "Save failed.";
        this._noteFlashTimer = setTimeout(() => { this.noteFlash = ""; }, 2000);
      },

      pendingFindings() { return this.caseFindings.filter((f) => !f.includedInReport); },
      pendingIocs() { return this.indicators.filter((i) => !i.includedInReport); },
      pendingTimelineEvents() { return this.timelineEvents.filter((e) => !e.includedInReport); },
      pendingInsertCount() { return this.pendingFindings().length + this.pendingIocs().length + this.pendingTimelineEvents().length; },

      appendToSection(headerText, block) {
        const lines = this.report.markdownContent.split("\n");
        const headerIdx = lines.findIndex((l) => l.trim() === headerText);
        if (headerIdx === -1) { this.report.markdownContent += "\n" + block + "\n"; return; }
        let insertAt = lines.length;
        for (let i = headerIdx + 1; i < lines.length; i++) {
          if (lines[i].startsWith("## ")) { insertAt = i; break; }
        }
        const before = lines.slice(0, insertAt);
        while (before.length && before[before.length - 1].trim() === "") before.pop();
        this.report.markdownContent = [...before, "", ...block.split("\n"), "", ...lines.slice(insertAt)].join("\n");
      },

      insertTableRow(headerText, columns, row) {
        const lines = this.report.markdownContent.split("\n");
        const headerIdx = lines.findIndex((l) => l.trim() === headerText);
        if (headerIdx === -1) { this.report.markdownContent += "\n" + row + "\n"; return; }
        let sectionEnd = lines.length;
        for (let i = headerIdx + 1; i < lines.length; i++) {
          if (lines[i].startsWith("## ")) { sectionEnd = i; break; }
        }
        const isSeparatorRow = (line) => line.trim().replace(/^\||\|$/g, "").split("|").every((c) => /^-+$/.test(c.trim()));
        let tableHeaderIdx = -1;
        for (let i = headerIdx + 1; i < sectionEnd - 1; i++) {
          if (lines[i].trim().startsWith("|") && isSeparatorRow(lines[i + 1])) { tableHeaderIdx = i; break; }
        }
        if (tableHeaderIdx === -1) {
          const before = lines.slice(0, sectionEnd);
          while (before.length && before[before.length - 1].trim() === "") before.pop();
          const tableHeader = "| " + columns.join(" | ") + " |";
          const separator = "|" + columns.map(() => "---").join("|") + "|";
          this.report.markdownContent = [...before, "", tableHeader, separator, row, "", ...lines.slice(sectionEnd)].join("\n");
        } else {
          let tableEnd = tableHeaderIdx + 2;
          while (tableEnd < sectionEnd && lines[tableEnd].trim().startsWith("|")) tableEnd++;
          this.report.markdownContent = [...lines.slice(0, tableEnd), row, ...lines.slice(tableEnd)].join("\n");
        }
      },

      insertFindingMarkdown(finding) {
        const block = "### " + finding.title + "\n\n**Severity:** " + finding.severity + "  \n**Confidence:** " + finding.confidence + "  \n**Source Evidence:** " + finding.sourceEvidence + "  \n**Source Module:** " + finding.sourceModule + "  \n\n" + finding.description;
        this.appendToSection("## Key Findings", block);
      },

      insertFindingIntoReport(findingId) {
        const f = this.caseFindings.find((x) => x.id === findingId);
        if (!f || f.includedInReport) return;
        this.insertFindingMarkdown(f);
        f.includedInReport = true;
        this.report.includedFindingIds.push(f.id);
        this.flashReport("Finding inserted into report.");
      },

      insertIocIntoReport(iocId) {
        const ioc = this.indicators.find((x) => x.id === iocId);
        if (!ioc || ioc.includedInReport) return;
        const row = "| " + ioc.type + " | " + ioc.value + " | " + ioc.severity + " | " + ioc.confidence + " | " + ioc.sourceEvidence + " → " + ioc.sourceModule + " |";
        this.insertTableRow("## IOCs", ["Type", "Value", "Severity", "Confidence", "Source"], row);
        ioc.includedInReport = true;
        this.report.includedIocIds.push(ioc.id);
        this.flashReport("IOC inserted into report.");
      },

      insertTimelineIntoReport(eventId) {
        const ev = this.timelineEvents.find((x) => x.id === eventId);
        if (!ev || ev.includedInReport) return;
        const row = "| " + ev.eventTime + " | " + ev.title + " | " + ev.eventType + " | " + ev.source + " |";
        this.insertTableRow("## Incident Timeline", ["Time", "Event", "Type", "Source"], row);
        ev.includedInReport = true;
        this.report.includedTimelineEventIds.push(ev.id);
        this.flashReport("Timeline event inserted into report.");
      },

      openReportPreview() {
        if (this.$refs.reportPreviewBody) {
          this.$refs.reportPreviewBody.innerHTML = renderMarkdownToHtml(this.report.markdownContent);
        }
        const dialog = document.getElementById("report-preview-dialog");
        if (dialog) { dialog.dataset.state = "open"; if (!dialog.open) dialog.showModal(); }
      },

      reportPrintDocument() {
        const body = renderMarkdownToHtml(this.report.markdownContent);
        return '<!DOCTYPE html><html><head><meta charset="utf-8"><title>' + this.report.title + "</title><style>body{font-family:Calibri,Arial,sans-serif;color:#111;line-height:1.5;padding:2rem;max-width:800px;margin:0 auto;}h1{font-size:1.6rem;margin-top:0;}h2{font-size:1.25rem;margin-top:1.5rem;border-bottom:1px solid #ddd;padding-bottom:.25rem;}h3{font-size:1.05rem;margin-top:1.25rem;}table{border-collapse:collapse;width:100%;margin:.75rem 0;}td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.9rem;}</style></head><body><h1>" + this.report.title + "</h1>" + body + "</body></html>";
      },

      exportReportPdf() {
        const win = window.open("", "_blank");
        if (!win) return;
        win.document.write(this.reportPrintDocument());
        win.document.close();
        win.focus();
        win.print();
      },

      exportReportDocx() {
        const blob = new Blob(["﻿", this.reportPrintDocument()], { type: "application/msword" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = (this.report.title || "report").replace(/[^a-z0-9-_]+/gi, "_") + ".doc";
        a.click();
        URL.revokeObjectURL(url);
      },
    }),
  );
});
