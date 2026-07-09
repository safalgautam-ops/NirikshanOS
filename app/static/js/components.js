/* this file defines Alpine components */

// this waits until Alpine is ready, then registers your custom components
document.addEventListener("alpine:init", () => {
  // Drives tabs.html's sliding active-tab indicator (next-app's TabsList).
  // Measures the active trigger's box and writes it as inline style on the
  // indicator element so it can be a plain absolutely-positioned div.
  Alpine.data("tabsIndicator", (initialTab) => ({
    tab: initialTab,
    indicatorStyle: "",

    init() {
      this.moveIndicator();
      window.addEventListener("resize", () => this.moveIndicator());
    },

    selectTab(value) {
      this.tab = value;
      this.$nextTick(() => this.moveIndicator());
    },

    moveIndicator() {
      const active = this.$refs.list.querySelector('[data-active="true"]');
      if (!active) {
        this.indicatorStyle = "";
        return;
      }
      this.indicatorStyle =
        "width:" +
        active.offsetWidth +
        "px;" +
        "height:" +
        active.offsetHeight +
        "px;" +
        "transform:translateX(" +
        active.offsetLeft +
        "px)";
    },
  }));

  // Drives the 3-step organization-registration wizard (onboarding/index.html).
  // Steps are plain sibling <div data-wizard-step="N"> blocks inside one big
  // <form> - this only toggles which one is visible and gates "Next" on the
  // current step's [data-required] fields actually having a value. The real
  // validation authority is server-side (app/features/onboarding/service.py);
  // this is just UX so a half-filled step can't silently advance.
  Alpine.data("orgWizard", () => ({
    step: 1,
    totalSteps: 3,
    error: "",

    next() {
      if (this.validateStep(this.step)) {
        this.error = "";
        this.step = Math.min(this.step + 1, this.totalSteps);
      }
    },

    back() {
      this.error = "";
      this.step = Math.max(this.step - 1, 1);
    },

    validateStep(n) {
      const container = this.$root.querySelector(
        '[data-wizard-step="' + n + '"]',
      );
      if (!container) return true;
      const fields = container.querySelectorAll("[data-required]");
      for (const field of fields) {
        if (!field.value || !field.value.trim()) {
          this.error = "Fill in every required field before continuing.";
          field.focus();
          return false;
        }
      }
      return true;
    },
  }));

  // Drives the "Add members" picker in the create-case dialog
  // (cases/list.html). orgMembers is this organization's full member list,
  // passed from the server once at render time - filtering/picking happens
  // entirely client-side since the list is small and the case doesn't exist
  // yet to scope a server-side search against (see cases/repository.py's
  // search_org_members_not_in_case, which only works once a case id exists).
  // ───────────────────────────────────────────────────────────────────────
  // Evidence type catalog + module registry for the case Analyze tab
  // (cases/detail.html). Everything below is mock data describing what a
  // real forensic module catalog would look like - there's no analysis job
  // backend yet (see analyzeWorkspace below), so "running" a module never
  // does real work. The point is the data model and UI flow: evidence type
  // detection -> compatible modules -> per-module config -> a staged plan
  // -> a mock "queue" -> mock "results" you can save/export.
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

  // Extension -> evidence type. A few extensions are inherently ambiguous in
  // real forensics (.raw/.dmp could be memory or disk) - picked one bucket
  // for each rather than guessing from content, which this mock has no way
  // to inspect anyway.
  const EVIDENCE_TYPE_EXTENSIONS = {
    binary: ["exe", "dll", "elf", "bin", "so", "sys", "macho", "o"],
    pcap: ["pcap", "pcapng", "cap"],
    email: ["eml", "msg", "mbox"],
    image: ["jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"],
    audio: ["wav", "mp3", "flac", "m4a", "ogg", "aac"],
    video: ["mp4", "mov", "avi", "mkv", "webm"],
    memory: ["mem", "vmem", "dmp", "lime", "raw"],
    disk: ["img", "dd", "e01", "aff", "vmdk", "qcow2", "iso"],
    document: [
      "pdf",
      "doc",
      "docx",
      "xls",
      "xlsx",
      "ppt",
      "pptx",
      "rtf",
      "odt",
    ],
    archive: ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"],
    mobile: ["apk", "aab", "dex", "jar", "ipa"],
    logs: ["evtx", "log", "jsonl", "syslog"],
    generic: [
      "txt",
      "csv",
      "json",
      "xml",
      "ini",
      "cfg",
      "dat",
      "plist",
      "db",
      "sqlite",
      "html",
      "htm",
      "md",
      "yaml",
      "yml",
    ],
  };

  const EXT_TO_EVIDENCE_TYPE = {};
  Object.entries(EVIDENCE_TYPE_EXTENSIONS).forEach(([type, exts]) => {
    exts.forEach((ext) => {
      EXT_TO_EVIDENCE_TYPE[ext] = type;
    });
  });

  // Populated lazily from the /modules API as the user opens Analyze dialogs.
  // Keys are module IDs; values are the serialized module dicts from the backend.
  const MODULE_MAP = {};

  function isModuleCompatible(module, evidenceType) {
    // The backend already filters by evidence type before returning the module
    // list, so client-side filtering is only needed for canvasModuleOutputs()
    // which uses the full cached list. "generic" category modules run against
    // everything; everything else must list the evidence type explicitly.
    return (
      module.category === "generic" ||
      (module.supported_types || []).includes(evidenceType)
    );
  }

  // The Analyze dialog groups compatible modules by execution "tier" rather
  // than by evidence-type category - pcap/email/memory categories map 1:1
  // onto their own tier (the wireframe's Network/Email/Memory Modules
  // groups), while every other category gets split by risk/isolation into
  // Basic Triage Bundle (fast, no-isolation, batchable into one container),
  // Standard Modules, or Advanced Modules. Derived from fields every module
  // already has rather than hand-tagging ~100 module objects with a new key.
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
    // API response carries `tier` directly from module_registry; fall back
    // to category-based derivation for any legacy mock data still in the file.
    if (module.tier) return module.tier;
    if (module.category === "pcap") return "network";
    if (module.category === "email") return "email";
    if (module.category === "memory") return "memory";
    if (module.category === "generic") return "basic_triage";
    return "standard";
  }

  // Plan values are lowercase (free/analyst/advanced) to match the backend.
  const PLAN_ORDER = ["free", "analyst", "advanced"];
  function requiredPlanOf(module) {
    // API response carries `required_plan` directly; fall back to tier-based
    // derivation for any legacy mock data still in the file.
    if (module.required_plan) return module.required_plan;
    const tier = moduleTierOf(module);
    if (tier === "advanced") return "advanced";
    if (tier === "basic_triage") return "free";
    return "free";
  }
  function isModuleLocked(module, userPlan) {
    const plan = (userPlan || "free").toLowerCase();
    return (
      PLAN_ORDER.indexOf(requiredPlanOf(module)) > PLAN_ORDER.indexOf(plan)
    );
  }


  // Severity/confidence for findings, IOCs, and timeline events are derived
  // from the module that produced them (riskLevel / isolationLevel already
  // exist on every module) rather than asked for by hand each time - same
  // "derive, don't hand-tag" approach as moduleTierOf/requiredPlanOf above.
  function severityOfModule(module) {
    return (module && module.riskLevel) || "Medium";
  }
  function confidenceOfModule(module) {
    return module && module.isolationLevel && module.isolationLevel !== "None"
      ? "High"
      : "Medium";
  }

  function formatTimelineTimestamp(ms) {
    const d = new Date(ms);
    const pad = (n) => String(n).padStart(2, "0");
    return (
      d.getFullYear() +
      "-" +
      pad(d.getMonth() + 1) +
      "-" +
      pad(d.getDate()) +
      " " +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes()) +
      ":" +
      pad(d.getSeconds())
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

  // Minimal Markdown -> HTML renderer for the Report Preview dialog - only
  // covers what the report editor actually produces (headings, bold,
  // links/images, tables, paragraphs with hard line breaks).
  // # Heading
  // ## Heading
  // ### Heading
  // **bold text**
  // [link](https://example.com)
  // ![image](image.png)
  // | tables |
  // paragraphs
  // line breaks

  // helps prevent XSS attacks by escaping special characters in HTML like: <script>alert('Hello World')</script>
  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function inlineMd(s) {
    let out = escapeHtml(s);
    out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>"); // converts **bold text** into <strong>bold text</strong>
    out = out.replace(/!\[([^\]]*)\]\((\S+?)\)/g, '<img src="$2" alt="$1">'); // converts ![image](image.png) into <img src="image.png" alt="image">
    out = out.replace(
      /\[([^\]]*)\]\((\S+?)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>', // converts [link](https://example.com) into <a href="https://example.com" target="_blank" rel="noopener">link</a>
    );
    return out;
  }
  // a main function that converts a markdown string into an HTML string
  function renderMarkdownToHtml(md) {
    const lines = (md || "").split("\n"); // split the markdown string into an array of lines: # Report Hello world ["# Report", "Hello world"]
    let html = ""; // final generated HTML
    let paragraph = []; // temporary stores normal text lines until the code knows the paragraph is finished
    // function that takes the current paragraphed line and adds it to the final HTML output
    // takes the current paragraph and adds it to the final HTML output
    // converts ["This is line one.", "This is line two."] into <p>This is line one. This is line two.</p>
    const flushParagraph = () => {
      if (!paragraph.length) return;
      html +=
        "<p>" +
        /* for each line of the paragraph,
         * replace any trailing spaces with a single space (to avoid double spaces)
         * and add a <br> if the line ends with two spaces (to preserve line breaks)
         * then join all the lines together with spaces in between
         */
        paragraph
          .map(
            (l, idx) =>
              inlineMd(l.replace(/ {2}$/, "")) +
              (idx < paragraph.length - 1
                ? l.endsWith("  ")
                  ? "<br>"
                  : " "
                : ""),
          )
          .join("") +
        "</p>";
      paragraph = [];
    };
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (/^###\s+/.test(line)) {
        flushParagraph();
        html += "<h3>" + inlineMd(line.replace(/^###\s+/, "")) + "</h3>";
        i++;
        continue;
      }
      if (/^##\s+/.test(line)) {
        flushParagraph();
        html += "<h2>" + inlineMd(line.replace(/^##\s+/, "")) + "</h2>";
        i++;
        continue;
      }
      if (/^#\s+/.test(line)) {
        flushParagraph();
        html += "<h1>" + inlineMd(line.replace(/^#\s+/, "")) + "</h1>";
        i++;
        continue;
      }
      if (line.trim().startsWith("|")) {
        flushParagraph();
        const tableLines = [];
        while (i < lines.length && lines[i].trim().startsWith("|")) {
          tableLines.push(lines[i]);
          i++;
        }
        const rows = tableLines.map((l) =>
          l
            .trim()
            .replace(/^\|/, "")
            .replace(/\|$/, "")
            .split("|")
            .map((c) => c.trim()),
        );
        const isSeparatorRow = (cells) => cells.every((c) => /^-+$/.test(c));
        let bodyRows = rows;
        let headRow = null;
        if (rows.length > 1 && isSeparatorRow(rows[1])) {
          headRow = rows[0];
          bodyRows = rows.slice(2);
        }
        html += "<table>";
        if (headRow)
          html +=
            "<thead><tr>" +
            headRow.map((c) => "<th>" + inlineMd(c) + "</th>").join("") +
            "</tr></thead>";
        html +=
          "<tbody>" +
          bodyRows
            .map(
              (r) =>
                "<tr>" +
                r.map((c) => "<td>" + inlineMd(c) + "</td>").join("") +
                "</tr>",
            )
            .join("") +
          "</tbody>";
        html += "</table>";
        continue;
      }
      if (line.trim() === "") {
        flushParagraph();
        i++;
        continue;
      }
      paragraph.push(line);
      i++;
    }
    flushParagraph();
    return html;
  }

  // Map backend status strings (lowercase) to the Title-case strings the
  // progress dialog template checks (e.g. task.status === 'Running').
  function _toFrontendStatus(backendStatus) {
    return (
      { queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Failed" }[backendStatus] || "Queued"
    );
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
    } catch {
      return { stdout: [], stderr: [] };
    }
  }

  function _formatSummary(summary) {
    if (!summary || typeof summary !== "object") return summary || "";
    return Object.entries(summary)
      .filter(([, v]) => v !== null && v !== undefined && v !== "")
      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
      .join("\n");
  }

  /* this component manages the Analyze tab's planner and job queue */
  Alpine.data(
    "analyzeWorkspace",
    (evidenceItems, userPlan, caseId, caseTitle, currentUserName, csrfToken) => ({
      /*
    this analyze page needs to remember some things while the user is using it
    and those things are called "state" variables
    */
      moduleMap: MODULE_MAP,
      evidenceTypeLabels: EVIDENCE_TYPE_LABELS,
      moduleTierLabels: MODULE_TIER_LABELS,
      userPlan: (userPlan || "free").toLowerCase(),
      // Per-evidence module cache: evidenceId → array of module objects from API.
      _modulesByEvidence: {},
      modulesLoading: false,
      evidence: evidenceItems || [], // for remembering the evidence items (files) inside Alpine (state)
      caseId: caseId || null,
      currentUserName: currentUserName || "Analyst",
      csrfToken: csrfToken || "",

      // Analyze dialog state - scoped to exactly one evidence file at a time,
      // opened via openAnalyzeDialog() from that file's card (see
      // evidence-upload.js's per-card Analyze button).
      analyzingEvidence: null,
      moduleQuery: "",
      tierFilter: "all",
      checkedModuleIds: [], // modules checked for this run
      selectedModule: null, // which checked module's config the right panel shows
      moduleOptionsByModule: {}, // { [moduleId]: { [fieldKey]: value } } - one config per module, not shared
      lockedModule: null, // module clicked while above the user's plan, for the upgrade dialog

      queue: [], // job groups across every analyze run: { id, tier, tierLabel, evidenceId, evidenceName, tasks }
      activeProgressJobIds: [], // which queue job ids the Analysis Progress dialog is currently showing
      results: [], // completed (and failed) module outputs: { id, evidenceId, moduleId, ..., failed?, findings, iocs, artifacts, rawOutput }

      // Results tab (case-wide index) filters.
      resultSearch: "",
      resultsFilterStatus: "all",
      resultsFilterType: "all",
      resultsFilterModule: "all",

      // Result Canvas - the per-evidence deep-dive dialog opened from a
      // Results tab row's "Open Canvas"/"View Jobs" action.
      canvasEvidenceId: null,
      canvasEvidenceName: "",
      canvasSelectedModuleId: null,
      canvasTab: "overview", // "overview" | "raw" - Raw Output never renders until chosen
      canvasNoteDraft: "",
      notesByKey: {}, // { "<evidenceId>:<moduleId>": noteText }
      savedIndicatorKeys: [], // dedup "type:value" already added via Add Indicator
      // Saved-but-not-yet-inserted items for the Report tab's Insert dialog -
      // shapes match the Report Tab spec's mock data structures exactly.
      indicators: [], // [{ id, caseId, type, value, severity, confidence, sourceEvidence, sourceModule, includedInReport }]
      caseFindings: [], // [{ id, caseId, title, severity, confidence, sourceEvidence, sourceModule, description, includedInReport }]
      timelineEvents: [], // [{ id, caseId, eventTime, title, eventType, source, confidence, includedInReport }]
      canvasFlash: "", // brief confirmation text under the Actions panel

      // ── Notes tab: shared case scratchpad ───────────────────────────────
      noteContent: "",
      noteFlash: "",
      _noteFlashTimer: null,

      // ── Report tab: the markdown report itself ───────────────────────────
      report: {
        id: "report_001",
        caseId: caseId || null,
        title: (caseTitle ? caseTitle + " " : "") + "Investigation Report",
        visibility: "personal_draft", // "personal_draft" | "case_shared"
        status: "draft", // draft | in_review | changes_requested | approved | final | exported
        version: "0.1",
        createdBy: currentUserName || "Analyst",
        updatedBy: currentUserName || "Analyst",
        markdownContent: DEFAULT_REPORT_MARKDOWN,
        includedFindingIds: [],
        includedIocIds: [],
        includedTimelineEventIds: [],
      },
      reportFlash: "", // brief confirmation text near the report action row

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

      // Delegates to evidence-upload.js's global formatter - exposed as a
      // component method (not called directly from the template) because
      // Alpine's expression evaluator runs expressions through a `with()`
      // block over its reactive proxy, which doesn't reliably fall through
      // to plain global functions.
      formatBytes(bytes) {
        return evidenceFormatBytes(bytes);
      },

      // Opens the per-file Analyze dialog for one evidence item. Called from
      // a plain DOM event dispatched by the vanilla-JS evidence card (those
      // cards aren't Alpine-rendered), so it upserts the item into `evidence`
      // first in case it wasn't in the page's initial server-rendered list
      // (e.g. it finished uploading after page load).
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
        if (dialog) {
          dialog.dataset.state = "open";
          if (!dialog.open) dialog.showModal();
        }
      },

      async _fetchModulesForEvidence(evidenceId) {
        if (this._modulesByEvidence[evidenceId]) return;
        this.modulesLoading = true;
        try {
          const resp = await fetch(
            `/cases/${this.caseId}/evidence/${evidenceId}/modules`,
            { headers: { "X-CSRF-Token": this.csrfToken } },
          );
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          const modules = data.modules || [];
          // Populate the shared module map so isModuleLocked / requiredPlanOf work.
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
        if (dialog) {
          dialog.dataset.state = "closed";
          if (dialog.open) dialog.close();
        }
      },

      compatibleModules() {
        if (!this.analyzingEvidence) return [];
        // Backend already filters by evidence type; return the cached result directly.
        return this._modulesByEvidence[this.analyzingEvidence.id] || [];
      },

      // Only tiers that actually contain a compatible module are shown, per
      // spec - a memory dump never shows an empty "Email Modules" group.
      compatibleModuleGroups() {
        const q = this.moduleQuery.trim().toLowerCase();
        const filtered = this.compatibleModules().filter((m) => {
          if (this.tierFilter !== "all" && moduleTierOf(m) !== this.tierFilter)
            return false;
          if (q && !m.name.toLowerCase().includes(q)) return false;
          return true;
        });
        const groups = [];
        MODULE_TIER_ORDER.forEach((tier) => {
          const mods = filtered.filter((m) => moduleTierOf(m) === tier);
          if (mods.length)
            groups.push({
              tier,
              label: MODULE_TIER_LABELS[tier],
              modules: mods,
            });
        });
        return groups;
      },

      availableTiers() {
        const tiers = new Set(
          this.compatibleModules().map((m) => moduleTierOf(m)),
        );
        return MODULE_TIER_ORDER.filter((t) => tiers.has(t));
      },

      isModuleLocked(moduleId) {
        return isModuleLocked(this.moduleMap[moduleId], this.userPlan);
      },

      requiredPlanOf(moduleId) {
        return requiredPlanOf(this.moduleMap[moduleId]);
      },

      // Basic Triage Bundle modules are batched into one shared container job
      // (see startAnalysis) - everything else runs as its own job.
      isBatchable(moduleId) {
        return moduleTierOf(this.moduleMap[moduleId]) === "basic_triage";
      },

      openUpgradeDialog(moduleId) {
        this.lockedModule = this.moduleMap[moduleId];
        const dialog = document.getElementById("upgrade-plan-dialog");
        if (dialog) {
          dialog.dataset.state = "open";
          if (!dialog.open) dialog.showModal();
        }
      },

      ensureOptions(moduleId) {
        if (this.moduleOptionsByModule[moduleId]) return;
        const mod = this.moduleMap[moduleId];
        const opts = {};
        mod.fields.forEach((f) => {
          opts[f.key] = Array.isArray(f.default) ? [...f.default] : f.default;
        });
        this.moduleOptionsByModule[moduleId] = opts;
      },

      // Checking a module both stages it for this run and shows its config on
      // the right - unchecking it falls back to whatever else is still
      // checked (or clears the config panel if nothing is).
      toggleModuleChecked(moduleId) {
        if (this.isModuleLocked(moduleId)) {
          this.openUpgradeDialog(moduleId);
          return;
        }
        const idx = this.checkedModuleIds.indexOf(moduleId);
        if (idx === -1) {
          this.checkedModuleIds.push(moduleId);
          this.selectModuleForConfig(moduleId);
        } else {
          this.checkedModuleIds.splice(idx, 1);
          if (this.selectedModule === moduleId)
            this.selectedModule = this.checkedModuleIds[0] || null;
        }
      },

      isModuleChecked(moduleId) {
        return this.checkedModuleIds.includes(moduleId);
      },

      selectModuleForConfig(moduleId) {
        if (this.isModuleLocked(moduleId)) {
          this.openUpgradeDialog(moduleId);
          return;
        }
        this.selectedModule = moduleId;
        this.ensureOptions(moduleId);
      },

      toggleChecklistValue(moduleId, fieldKey, value) {
        const list = this.moduleOptionsByModule[moduleId][fieldKey] || [];
        const idx = list.indexOf(value);
        if (idx === -1) list.push(value);
        else list.splice(idx, 1);
        this.moduleOptionsByModule[moduleId][fieldKey] = list;
      },

      optionsSummaryFor(moduleId) {
        const mod = this.moduleMap[moduleId];
        const opts = this.moduleOptionsByModule[moduleId] || {};
        return mod.fields
          .map((f) => {
            const v = opts[f.key];
            const val = Array.isArray(v)
              ? v.join("/")
              : typeof v === "boolean"
                ? v
                  ? "Yes"
                  : "No"
                : v;
            return f.label + ": " + val;
          })
          .join(", ");
      },

      // Bottom-of-dialog plan summary, computed live from whatever's checked -
      // no separate "Add to Plan" step before this.
      planSummary() {
        const mods = this.checkedModuleIds
          .map((id) => this.moduleMap[id])
          .filter(Boolean);
        const batchGroups = new Set();
        let containers = 0;
        mods.forEach((m) => {
          if (m.batchable && m.batch_group) {
            batchGroups.add(m.batch_group);
          } else {
            containers++;
          }
        });
        return {
          moduleCount: mods.length,
          taskCount: mods.length,
          containerRuns: containers + batchGroups.size,
          estimatedMinutes:
            mods.length === 0 ? 0 : Math.max(2, mods.length * 2),
        };
      },

      // Submits checked modules to the backend, builds queue from real job/task
      // IDs, opens the Analysis Progress dialog, and starts polling for status.
      async startAnalysis() {
        if (!this.checkedModuleIds.length || !this.analyzingEvidence) return;
        const evidence = this.analyzingEvidence;

        const moduleOptions = {};
        this.checkedModuleIds.forEach((id) => {
          if (this.moduleOptionsByModule[id])
            moduleOptions[id] = this.moduleOptionsByModule[id];
        });

        let data;
        try {
          const resp = await fetch(
            `/cases/${this.caseId}/evidence/${evidence.id}/analyze`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": this.csrfToken,
              },
              body: JSON.stringify({
                module_ids: this.checkedModuleIds,
                module_options: moduleOptions,
              }),
            },
          );
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            const msg = err.error || `Analysis request failed (${resp.status})`;
            alert(msg);
            return;
          }
          data = await resp.json();
        } catch (e) {
          console.error("[analyze] network error", e);
          return;
        }

        // Build queue entries from the real server-assigned job and task IDs.
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
                id: t.task_id,
                moduleId: t.module_id,
                moduleName: t.module_name,
                tool: mod.tool || "",
                outputType: mod.outputType || "",
                risk: mod.riskLevel || "",
                isolation: mod.isolationLevel || "",
                summary: this.moduleOptionsByModule[t.module_id]
                  ? this.optionsSummaryFor(t.module_id)
                  : "",
                status: "Queued",
                progress: 0,
              };
            }),
          });
        });

        this.activeProgressJobIds = newJobIds;
        this.closeAnalyzeDialog();
        const queueDialog = document.getElementById("current-job-queue");
        if (queueDialog) {
          queueDialog.dataset.state = "open";
          if (!queueDialog.open) queueDialog.showModal();
        }
        this._startPolling();
      },

      // Jobs the Analysis Progress dialog currently displays - the most
      // recently started run, matching the wireframe's single "Evidence: …"
      // header rather than every run ever queued.
      progressJobs() {
        return this.queue.filter((j) =>
          this.activeProgressJobIds.includes(j.id),
        );
      },

      _startPolling() {
        if (this._pollKey !== null) return;
        this._pollKey = setInterval(() => this._doPoll(), 2000);
      },

      _stopPolling() {
        if (this._pollKey !== null) {
          clearInterval(this._pollKey);
          this._pollKey = null;
        }
      },

      async _doPoll() {
        const activeJobs = this.queue.filter((j) =>
          j.tasks.some(
            (t) => t.status === "Queued" || t.status === "Running",
          ),
        );
        if (!activeJobs.length) {
          this._stopPolling();
          return;
        }
        const evidenceIds = [...new Set(activeJobs.map((j) => j.evidenceId))];
        for (const evidenceId of evidenceIds) {
          try {
            const resp = await fetch(
              `/cases/${this.caseId}/evidence/${evidenceId}/jobs`,
            );
            if (!resp.ok) continue;
            const data = await resp.json();
            await this._applyPollData(data.jobs || []);
          } catch (e) {
            console.error("[poll] error fetching job status", e);
          }
        }
      },

      async _applyPollData(serverJobs) {
        let changed = false;
        for (const serverJob of serverJobs) {
          const queueJob = this.queue.find((j) => j.id === serverJob.id);
          if (!queueJob) continue;
          for (const serverTask of serverJob.tasks) {
            const queueTask = queueJob.tasks.find(
              (t) => t.id === serverTask.id,
            );
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
                id: serverTask.id,
                evidenceId: queueJob.evidenceId,
                evidenceName: queueJob.evidenceName,
                moduleId: queueTask.moduleId,
                moduleName: queueTask.moduleName,
                tool: queueTask.tool,
                outputType: queueTask.outputType,
                risk: queueTask.risk,
                isolation: queueTask.isolation,
                summary: queueTask.summary,
                completedAt: Date.now(),
                findings: [],
                iocs: [],
                artifacts: [],
                rawOutput: output,
              });
            } else if (next === "Failed" && prev !== "Failed") {
              this.results = this.results.filter((r) => r.id !== serverTask.id);
              this.results.push({
                id: serverTask.id,
                evidenceId: queueJob.evidenceId,
                evidenceName: queueJob.evidenceName,
                moduleId: queueTask.moduleId,
                moduleName: queueTask.moduleName,
                tool: queueTask.tool,
                outputType: queueTask.outputType,
                risk: queueTask.risk,
                isolation: queueTask.isolation,
                summary: queueTask.summary,
                completedAt: Date.now(),
                failed: true,
                findings: [],
                iocs: [],
                artifacts: [],
                rawOutput: {
                  stdout: [],
                  stderr: [
                    serverTask.error_message ||
                      "Analysis failed — check worker logs.",
                  ],
                },
              });
            }
          }
        }
        if (changed) this.queue = [...this.queue];
      },

      // Cancelling a queued/running task marks it Failed instead of deleting
      // it outright - a cancelled job should leave a visible trace (the
      // Results tab's Failed count, the Result Canvas's ⚠ status) rather than
      // silently vanishing. Re-Analyze from the canvas is how you retry it.
      cancelTask(jobId, taskId) {
        const job = this.queue.find((j) => j.id === jobId);
        if (!job) return;
        // Backend cancels at job level — mark every task in the job Failed,
        // not just the clicked one.
        job.tasks.forEach((task) => {
          if (task.status === "Failed" || task.status === "Completed") return;
          task.status = "Failed";
          this.results = this.results.filter((r) => r.id !== task.id);
          this.results.push({
            id: task.id,
            evidenceId: job.evidenceId,
            evidenceName: job.evidenceName,
            moduleId: task.moduleId,
            moduleName: task.moduleName,
            tool: task.tool,
            outputType: task.outputType,
            risk: task.risk,
            isolation: task.isolation,
            summary: task.summary,
            completedAt: Date.now(),
            failed: true,
            output: "Analysis cancelled before completion.",
            findings: [],
            iocs: [],
            artifacts: [],
            rawOutput: {
              stdout: [],
              stderr: ["[" + task.tool + "] analysis cancelled by analyst."],
            },
          });
        });
        this.queue = [...this.queue];
        fetch(`/analysis/jobs/${jobId}/cancel`, {
          method: "POST",
          headers: { "X-CSRF-Token": this.csrfToken },
        }).catch(() => {});
      },

      // True removal, regardless of status - the only way a task/result
      // disappears from the queue and Results entirely.
      deleteTaskRow(jobId, taskId) {
        const job = this.queue.find((j) => j.id === jobId);
        if (job) {
          job.tasks = job.tasks.filter((t) => t.id !== taskId);
          if (!job.tasks.length)
            this.queue = this.queue.filter((j) => j.id !== jobId);
        }
        this.results = this.results.filter((r) => r.id !== taskId);
      },

      // Opens the Result Canvas for whichever evidence the Analysis Progress
      // dialog is currently showing.
      openResultCanvas() {
        const jobs = this.progressJobs();
        if (!jobs.length) return;
        const queueDialog = document.getElementById("current-job-queue");
        if (queueDialog) {
          queueDialog.dataset.state = "closed";
          if (queueDialog.open) queueDialog.close();
        }
        this.openResultCanvasFor(jobs[0].evidenceId);
      },

      // ── Results tab: case-wide index, one row per evidence file ─────────

      // One summary row per evidence id that has any analysis activity at
      // all (never run = not listed - there's nothing to index yet).
      resultRowsRaw() {
        const byEvidence = {};
        const ensure = (id, name) =>
          byEvidence[id] ||
          (byEvidence[id] = {
            evidenceId: id,
            evidenceName: name,
            completed: 0,
            running: 0,
            failed: 0,
            moduleIds: new Set(),
          });
        this.results.forEach((r) => {
          const g = ensure(r.evidenceId, r.evidenceName);
          g.moduleIds.add(r.moduleId);
          if (r.failed) g.failed += 1;
          else g.completed += 1;
        });
        this.queue.forEach((job) => {
          job.tasks.forEach((t) => {
            if (t.status === "Failed") return; // already counted via results above
            const g = ensure(job.evidenceId, job.evidenceName);
            g.moduleIds.add(t.moduleId);
            if (t.status === "Running" || t.status === "Queued") g.running += 1;
          });
        });
        return Object.values(byEvidence);
      },

      resultRows() {
        const q = this.resultSearch.trim().toLowerCase();
        return this.resultRowsRaw()
          .filter((row) => {
            if (q && !row.evidenceName.toLowerCase().includes(q)) return false;
            const item = this.evidence.find((e) => e.id === row.evidenceId);
            const type = item ? this.evidenceTypeOf(item) : null;
            if (
              this.resultsFilterType !== "all" &&
              type !== this.resultsFilterType
            )
              return false;
            if (
              this.resultsFilterModule !== "all" &&
              !row.moduleIds.has(this.resultsFilterModule)
            )
              return false;
            if (this.resultsFilterStatus === "completed" && !row.completed)
              return false;
            if (this.resultsFilterStatus === "running" && !row.running)
              return false;
            if (this.resultsFilterStatus === "failed" && !row.failed)
              return false;
            return true;
          })
          .map((row) => {
            const item = this.evidence.find((e) => e.id === row.evidenceId);
            return {
              ...row,
              evidenceTypeLabel: item ? this.evidenceTypeLabelOf(item) : "—",
              actionLabel:
                row.completed > 0 || row.failed > 0
                  ? "Open Canvas"
                  : "View Jobs",
            };
          });
      },

      availableResultTypes() {
        const types = new Set();
        this.resultRowsRaw().forEach((row) => {
          const item = this.evidence.find((e) => e.id === row.evidenceId);
          if (item) types.add(this.evidenceTypeOf(item));
        });
        return Array.from(types).map((t) => ({
          value: t,
          label: this.evidenceTypeLabels[t] || t,
        }));
      },

      availableResultModules() {
        const ids = new Set();
        this.resultRowsRaw().forEach((row) =>
          row.moduleIds.forEach((id) => ids.add(id)),
        );
        return Array.from(ids)
          .map((id) => this.moduleMap[id])
          .filter(Boolean)
          .sort((a, b) => a.name.localeCompare(b.name));
      },

      openJobsForEvidence(evidenceId) {
        this.activeProgressJobIds = this.queue
          .filter((j) => j.evidenceId === evidenceId)
          .map((j) => j.id);
        const dialog = document.getElementById("current-job-queue");
        if (dialog) {
          dialog.dataset.state = "open";
          if (!dialog.open) dialog.showModal();
        }
      },

      // ── Result Canvas: deep-dive into one evidence file ──────────────────

      async openResultCanvasFor(evidenceId) {
        const item = this.evidence.find((e) => e.id === evidenceId);
        const row = this.resultRowsRaw().find(
          (r) => r.evidenceId === evidenceId,
        );
        this.canvasEvidenceId = evidenceId;
        this.canvasEvidenceName = item
          ? item.filename
          : row
            ? row.evidenceName
            : "";

        // Ensure modules are loaded for this evidence (needed by canvasModuleOutputs).
        await this._fetchModulesForEvidence(evidenceId);
        // Load persisted notes for this evidence so the Notes panel is pre-filled.
        await this._fetchNotesForEvidence(evidenceId);
        // Load real parsed results from DB before opening so the viewer
        // shows data even when the canvas is opened after a previous session's analysis.
        await this._loadResultsFromBackend(evidenceId);

        const outputs = this.canvasModuleOutputs();
        const preferred =
          outputs.find(
            (o) => o.status === "completed" || o.status === "failed",
          ) ||
          outputs[0] ||
          null;
        this.selectCanvasModule(preferred ? preferred.moduleId : null);
        const dialog = document.getElementById("result-canvas-dialog");
        if (dialog) {
          dialog.dataset.state = "open";
          if (!dialog.open) dialog.showModal();
        }
      },

      closeResultCanvas() {
        const dialog = document.getElementById("result-canvas-dialog");
        if (dialog) {
          dialog.dataset.state = "closed";
          if (dialog.open) dialog.close();
        }
      },

      // Every module compatible with this evidence's type, including ones
      // never run (status "not_run") - the left "Module Outputs" column shows
      // the full picture, not just modules that happened to execute.
      canvasModuleOutputs() {
        if (!this.canvasEvidenceId) return [];
        const item = this.evidence.find((e) => e.id === this.canvasEvidenceId);
        const type = item ? this.evidenceTypeOf(item) : null;
        const compatible = this._modulesByEvidence[this.canvasEvidenceId] || [];

        const taskByModule = {};
        this.queue.forEach((job) => {
          if (job.evidenceId !== this.canvasEvidenceId) return;
          job.tasks.forEach((t) => {
            taskByModule[t.moduleId] = t;
          });
        });
        const resultByModule = {};
        this.results.forEach((r) => {
          if (r.evidenceId === this.canvasEvidenceId)
            resultByModule[r.moduleId] = r;
        });

        const statusOrder = {
          running: 0,
          queued: 1,
          failed: 2,
          completed: 3,
          not_run: 4,
        };
        return compatible
          .map((m) => {
            const result = resultByModule[m.id];
            const task = taskByModule[m.id];
            let status = "not_run";
            let progress = 0;
            if (result) {
              status = result.failed ? "failed" : "completed";
              progress = 100;
            } else if (task) {
              status = task.status === "Running" ? "running" : "queued";
              progress = task.progress;
            }
            return {
              moduleId: m.id,
              moduleName: m.name,
              tool: m.tool,
              tier: moduleTierOf(m),
              status,
              progress,
            };
          })
          .sort(
            (a, b) =>
              statusOrder[a.status] - statusOrder[b.status] ||
              a.moduleName.localeCompare(b.moduleName),
          );
      },

      canvasModuleGroups() {
        const outputs = this.canvasModuleOutputs();
        const groups = [];
        MODULE_TIER_ORDER.forEach((tier) => {
          const mods = outputs.filter((o) => o.tier === tier);
          if (mods.length)
            groups.push({
              tier,
              label: MODULE_TIER_LABELS[tier],
              modules: mods,
            });
        });
        return groups;
      },

      // Switching modules always resets the viewer to Overview - Raw Output
      // is per-module and shouldn't carry over to whatever's selected next.
      selectCanvasModule(moduleId) {
        this.canvasSelectedModuleId = moduleId;
        this.canvasTab = "overview";
        this.canvasNoteDraft = moduleId
          ? this.notesByKey[this.canvasNoteKeyFor(moduleId)] || ""
          : "";
      },

      canvasNoteKeyFor(moduleId) {
        return this.canvasEvidenceId + ":" + moduleId;
      },

      async saveCanvasNote() {
        if (!this.canvasSelectedModuleId) return;
        const moduleId = this.canvasSelectedModuleId;
        const body = this.canvasNoteDraft;
        // Validate client-side before flashing success — the server rejects
        // empty/whitespace bodies with 400, so don't optimistically claim success.
        if (!body.trim()) {
          this.flashCanvas("Note is empty.");
          return;
        }
        this.notesByKey[this.canvasNoteKeyFor(moduleId)] = body;
        this.flashCanvas("Note saved.");
        fetch(
          `/cases/${this.caseId}/evidence/${this.canvasEvidenceId}/notes/${encodeURIComponent(moduleId)}`,
          {
            method: "PUT",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": this.csrfToken,
            },
            body: JSON.stringify({ body }),
          },
        ).catch(() => {});
      },

      async _fetchNotesForEvidence(evidenceId) {
        try {
          const resp = await fetch(
            `/cases/${this.caseId}/evidence/${evidenceId}/notes`,
            { headers: { "X-CSRF-Token": this.csrfToken } },
          );
          if (!resp.ok) return;
          const data = await resp.json();
          const notes = data.notes || {};
          Object.entries(notes).forEach(([moduleId, noteBody]) => {
            this.notesByKey[evidenceId + ":" + moduleId] = noteBody;
          });
        } catch (_) {}
      },

      // The Output Viewer's single source of truth - Overview, Raw Output,
      // and every Actions-panel button all read from this.
      canvasSelectedOutput() {
        if (!this.canvasSelectedModuleId) return null;
        const meta = this.canvasModuleOutputs().find(
          (o) => o.moduleId === this.canvasSelectedModuleId,
        );
        if (!meta) return null;
        const result = this.results.find(
          (r) =>
            r.evidenceId === this.canvasEvidenceId &&
            r.moduleId === this.canvasSelectedModuleId,
        );
        return {
          moduleId: meta.moduleId,
          moduleName: meta.moduleName,
          tool: meta.tool,
          status: meta.status,
          progress: meta.progress,
          summary: result ? (result.parsedOutput || result.output || "") : "",
          findings: result ? result.findings : [],
          iocs: result ? result.iocs : [],
          artifacts: result ? result.artifacts : [],
          rawOutput: result ? result.rawOutput : { stdout: [], stderr: [] },
        };
      },

      async _loadResultsFromBackend(evidenceId) {
        try {
          const resp = await fetch(
            `/cases/${this.caseId}/evidence/${evidenceId}/results`,
          );
          if (!resp.ok) return;
          const data = await resp.json();
          // Jobs arrive newest-first. First time we see a moduleId wins —
          // that's the result from the most recent analysis run for that module.
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

              // Remove any stale entry for this evidence+module before inserting
              // the canonical one (avoids moduleId-collision duplicates).
              this.results = this.results.filter(
                (r) =>
                  !(
                    r.evidenceId === evidenceId &&
                    r.moduleId === task.module_id
                  ),
              );

              const raw = rawOutput.stdout_path
                ? await _fetchTaskOutput(task.task_id)
                : { stdout: [], stderr: [] };

              this.results.push({
                id: task.task_id,
                evidenceId,
                evidenceName: data.evidence ? data.evidence.filename : "",
                moduleId: task.module_id,
                moduleName: task.module_name,
                tool: "",
                outputType: "",
                risk: "",
                isolation: "",
                summary: "",
                parsedOutput,
                completedAt: Date.now(),
                failed: task.status === "failed",
                findings,
                iocs,
                artifacts,
                rawOutput: raw,
              });
            }
          }
        } catch (e) {
          console.error("[canvas] failed to load results from backend", e);
        }
      },

      copyRawOutput() {
        const output = this.canvasSelectedOutput();
        if (!output) return;
        const text = [
          "STDOUT",
          ...output.rawOutput.stdout,
          "",
          "STDERR",
          ...output.rawOutput.stderr,
        ].join("\n");
        navigator.clipboard?.writeText(text);
        this.flashCanvas("Copied to clipboard.");
      },

      downloadRawOutput() {
        const output = this.canvasSelectedOutput();
        if (!output) return;
        const text = [
          "STDOUT",
          ...output.rawOutput.stdout,
          "",
          "STDERR",
          ...output.rawOutput.stderr,
        ].join("\n");
        const blob = new Blob([text], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download =
          this.canvasEvidenceName + "-" + output.moduleId + "-raw.txt";
        a.click();
        URL.revokeObjectURL(url);
      },

      // Re-queues the currently selected module for this evidence as a fresh
      // job - drops any prior task/result for that exact module first so it
      // shows as freshly Queued rather than coexisting with the old one.
      reAnalyzeCurrentModule() {
        if (!this.canvasSelectedModuleId || !this.canvasEvidenceId) return;
        const mod = this.moduleMap[this.canvasSelectedModuleId];
        if (!mod) return;
        const item = this.evidence.find((e) => e.id === this.canvasEvidenceId);
        const evidenceName =
          this.canvasEvidenceName || (item && item.filename) || "";

        this.queue.forEach((job) => {
          if (job.evidenceId === this.canvasEvidenceId)
            job.tasks = job.tasks.filter((t) => t.moduleId !== mod.id);
        });
        this.queue = this.queue.filter((j) => j.tasks.length);
        this.results = this.results.filter(
          (r) =>
            !(r.evidenceId === this.canvasEvidenceId && r.moduleId === mod.id),
        );

        this.ensureOptions(mod.id);
        const tier = moduleTierOf(mod);
        const jobId = this.canvasEvidenceId + ":" + tier + ":" + Date.now();
        this.queue.push({
          id: jobId,
          tier,
          tierLabel: MODULE_TIER_LABELS[tier],
          evidenceId: this.canvasEvidenceId,
          evidenceName,
          tasks: [
            {
              id: jobId + ":" + mod.id,
              moduleId: mod.id,
              moduleName: mod.name,
              tool: mod.tool,
              outputType: mod.outputType,
              risk: mod.riskLevel,
              isolation: mod.isolationLevel,
              summary: this.optionsSummaryFor(mod.id),
              status: "Queued",
              progress: 0,
            },
          ],
        });
        this.flashCanvas("Re-Analyze queued.");
      },

      exportCanvasEvidence() {
        const data = this.results.filter(
          (r) => r.evidenceId === this.canvasEvidenceId,
        );
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
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
        this._canvasFlashTimer = setTimeout(() => {
          this.canvasFlash = "";
        }, 2000);
      },

      // ── Analyst Notes / Actions panel ────────────────────────────────────

      indicatorsAddedForCurrent() {
        const output = this.canvasSelectedOutput();
        if (!output || !output.iocs.length) return false;
        return output.iocs.every((ioc) =>
          this.savedIndicatorKeys.includes(ioc.type + ":" + ioc.value),
        );
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
            id:
              this.canvasEvidenceId +
              ":" +
              output.moduleId +
              ":" +
              ioc.type +
              ":" +
              Date.now(),
            caseId: this.caseId,
            type: ioc.type,
            value: ioc.value,
            severity: severityOfModule(mod),
            confidence: confidenceOfModule(mod),
            sourceEvidence: this.canvasEvidenceName,
            sourceModule: output.moduleName,
            includedInReport: false,
          });
          // Persist to backend (fire-and-forget; dedup handled server-side).
          fetch(`/cases/${this.caseId}/indicators`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": this.csrfToken,
            },
            body: JSON.stringify({
              evidence_id: this.canvasEvidenceId,
              module_id: output.moduleId,
              type: ioc.type,
              value: ioc.value,
              severity: severityOfModule(mod),
              confidence: confidenceOfModule(mod),
              source_evidence: this.canvasEvidenceName,
              source_module: output.moduleName,
            }),
          }).catch(() => {});
        });
        this.flashCanvas("Indicator added.");
      },

      createFinding() {
        const output = this.canvasSelectedOutput();
        if (!output) return;
        const mod = this.moduleMap[output.moduleId];
        const note = this.canvasNoteDraft.trim();
        const description =
          note || output.findings.join(" ") || output.summary || "";
        if (!description) return;
        const title = note
          ? note.split("\n")[0].slice(0, 80)
          : output.findings[0] || output.moduleName + " finding";
        const finding = {
          id: this.canvasEvidenceId + ":" + output.moduleId + ":" + Date.now(),
          caseId: this.caseId,
          title,
          severity: severityOfModule(mod),
          confidence: confidenceOfModule(mod),
          sourceEvidence: this.canvasEvidenceName,
          sourceModule: output.moduleName,
          description,
          includedInReport: false,
        };
        this.caseFindings.push(finding);
        // Persist to backend.
        fetch(`/cases/${this.caseId}/findings`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": this.csrfToken,
          },
          body: JSON.stringify({
            evidence_id: this.canvasEvidenceId,
            module_id: output.moduleId,
            title: finding.title,
            description: finding.description,
            severity: finding.severity,
            confidence: finding.confidence,
            source_evidence: finding.sourceEvidence,
            source_module: finding.sourceModule,
          }),
        }).catch(() => {});
        this.flashCanvas("Finding created.");
      },

      addToTimeline() {
        const output = this.canvasSelectedOutput();
        if (!output) return;
        const mod = this.moduleMap[output.moduleId];
        const eventType =
          {
            network: "Network Event",
            email: "Email Event",
            memory: "Memory Event",
          }[mod ? moduleTierOf(mod) : ""] || "Analysis Event";
        const nowStr = new Date().toISOString().slice(0, 16); // "YYYY-MM-DDTHH:MM"
        const tlTitle = output.moduleName + " completed on " + this.canvasEvidenceName;
        this.timelineEvents.push({
          id: this.canvasEvidenceId + ":" + output.moduleId + ":" + Date.now(),
          caseId: this.caseId,
          eventTime: formatTimelineTimestamp(Date.now()),
          title: tlTitle,
          eventType,
          source: this.canvasEvidenceName + " → " + output.moduleName,
          confidence: confidenceOfModule(mod),
          includedInReport: false,
        });
        // Persist to the timeline as a milestone so it appears on /cases/<id>/timeline.
        fetch(`/cases/${this.caseId}/timeline/items/json`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": this.csrfToken,
          },
          body: JSON.stringify({
            type: "milestone",
            title: tlTitle,
            description: eventType + " detected via " + output.moduleName,
            timeline_time: nowStr,
            linked_evidence_id: this.canvasEvidenceId,
            linked_result_label: output.moduleName,
          }),
        }).catch(() => {});
        this.flashCanvas("Added to timeline.");
      },

      // The Result Canvas's "Add to Report" fast path: builds a finding from
      // the current completed result's own summary and inserts it straight
      // into the report draft, skipping the Insert dialog entirely. This is
      // distinct from Create Finding, which lets the analyst write their own
      // title/description first and queues it for a deliberate Insert later.
      addCurrentToReport() {
        const output = this.canvasSelectedOutput();
        if (!output || output.status !== "completed") return;
        const mod = this.moduleMap[output.moduleId];
        const finding = {
          id: this.canvasEvidenceId + ":" + output.moduleId + ":" + Date.now(),
          caseId: this.caseId,
          title: output.moduleName + " result",
          severity: severityOfModule(mod),
          confidence: confidenceOfModule(mod),
          sourceEvidence: this.canvasEvidenceName,
          sourceModule: output.moduleName,
          description: output.summary,
          includedInReport: true,
        };
        this.caseFindings.push(finding);
        this.insertFindingMarkdown(finding);
        this.report.includedFindingIds.push(finding.id);
        this.flashCanvas("Added to report.");
      },

      // ── Report tab: the markdown report itself ───────────────────────────

      flashReport(message) {
        this.reportFlash = message;
        clearTimeout(this._reportFlashTimer);
        this._reportFlashTimer = setTimeout(() => {
          this.reportFlash = "";
        }, 2000);
      },

      async saveDraft() {
        this.report.updatedBy = this.currentUserName;
        const resp = await fetch(`/cases/${this.caseId}/report`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": this.csrfToken,
          },
          body: JSON.stringify({
            content: this.report.markdownContent,
            title: this.report.title,
          }),
        }).catch(() => null);
        this.flashReport(resp && resp.ok ? "Draft saved." : "Save failed.");
      },

      async _loadReportFromBackend() {
        try {
          const resp = await fetch(`/cases/${this.caseId}/report`);
          if (!resp.ok) return;
          const data = await resp.json();
          if (data.content) {
            this.report.markdownContent = data.content;
            if (data.title) this.report.title = data.title;
          }
        } catch (_) {}
      },

      async _loadFindingsFromBackend() {
        try {
          const resp = await fetch(`/cases/${this.caseId}/findings`);
          if (!resp.ok) return;
          const data = await resp.json();
          this.caseFindings = (data.findings || []).map((f) => ({
            id: f.id,
            caseId: this.caseId,
            title: f.title,
            description: f.description,
            severity: f.severity,
            confidence: f.confidence,
            sourceEvidence: f.source_evidence || "",
            sourceModule: f.source_module || "",
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
            id: i.id,
            caseId: this.caseId,
            type: i.type,
            value: i.value,
            severity: i.severity,
            confidence: i.confidence,
            sourceEvidence: i.source_evidence || "",
            sourceModule: i.source_module || "",
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
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": this.csrfToken,
          },
          body: JSON.stringify({ content: this.noteContent }),
        }).catch(() => null);
        clearTimeout(this._noteFlashTimer);
        this.noteFlash = resp && resp.ok ? "Saved." : "Save failed.";
        this._noteFlashTimer = setTimeout(() => { this.noteFlash = ""; }, 2000);
      },

      pendingFindings() {
        return this.caseFindings.filter((f) => !f.includedInReport);
      },
      pendingIocs() {
        return this.indicators.filter((i) => !i.includedInReport);
      },
      pendingTimelineEvents() {
        return this.timelineEvents.filter((e) => !e.includedInReport);
      },
      pendingInsertCount() {
        return (
          this.pendingFindings().length +
          this.pendingIocs().length +
          this.pendingTimelineEvents().length
        );
      },

      // Inserts `block` at the bottom of the section under `headerText` (just
      // above whatever "## " heading comes next, or at the document's end if
      // this is the last section) - so repeated inserts stack in order rather
      // than piling up right under the heading every time.
      appendToSection(headerText, block) {
        const lines = this.report.markdownContent.split("\n");
        const headerIdx = lines.findIndex((l) => l.trim() === headerText);
        if (headerIdx === -1) {
          this.report.markdownContent += "\n" + block + "\n";
          return;
        }
        let insertAt = lines.length;
        for (let i = headerIdx + 1; i < lines.length; i++) {
          if (lines[i].startsWith("## ")) {
            insertAt = i;
            break;
          }
        }
        const before = lines.slice(0, insertAt);
        while (before.length && before[before.length - 1].trim() === "")
          before.pop();
        this.report.markdownContent = [
          ...before,
          "",
          ...block.split("\n"),
          "",
          ...lines.slice(insertAt),
        ].join("\n");
      },

      // Same section-scoped insertion as appendToSection, but for a Markdown
      // table row: creates the header+separator+row the first time something
      // is inserted into that section, and just appends a row after that.
      insertTableRow(headerText, columns, row) {
        const lines = this.report.markdownContent.split("\n");
        const headerIdx = lines.findIndex((l) => l.trim() === headerText);
        if (headerIdx === -1) {
          this.report.markdownContent += "\n" + row + "\n";
          return;
        }
        let sectionEnd = lines.length;
        for (let i = headerIdx + 1; i < lines.length; i++) {
          if (lines[i].startsWith("## ")) {
            sectionEnd = i;
            break;
          }
        }
        const isSeparatorRow = (line) =>
          line
            .trim()
            .replace(/^\||\|$/g, "")
            .split("|")
            .every((c) => /^-+$/.test(c.trim()));
        let tableHeaderIdx = -1;
        for (let i = headerIdx + 1; i < sectionEnd - 1; i++) {
          if (lines[i].trim().startsWith("|") && isSeparatorRow(lines[i + 1])) {
            tableHeaderIdx = i;
            break;
          }
        }
        if (tableHeaderIdx === -1) {
          const before = lines.slice(0, sectionEnd);
          while (before.length && before[before.length - 1].trim() === "")
            before.pop();
          const tableHeader = "| " + columns.join(" | ") + " |";
          const separator = "|" + columns.map(() => "---").join("|") + "|";
          this.report.markdownContent = [
            ...before,
            "",
            tableHeader,
            separator,
            row,
            "",
            ...lines.slice(sectionEnd),
          ].join("\n");
        } else {
          let tableEnd = tableHeaderIdx + 2;
          while (
            tableEnd < sectionEnd &&
            lines[tableEnd].trim().startsWith("|")
          )
            tableEnd++;
          this.report.markdownContent = [
            ...lines.slice(0, tableEnd),
            row,
            ...lines.slice(tableEnd),
          ].join("\n");
        }
      },

      insertFindingMarkdown(finding) {
        const block =
          "### " +
          finding.title +
          "\n\n" +
          "**Severity:** " +
          finding.severity +
          "  \n" +
          "**Confidence:** " +
          finding.confidence +
          "  \n" +
          "**Source Evidence:** " +
          finding.sourceEvidence +
          "  \n" +
          "**Source Module:** " +
          finding.sourceModule +
          "  \n\n" +
          finding.description;
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
        const row =
          "| " +
          ioc.type +
          " | " +
          ioc.value +
          " | " +
          ioc.severity +
          " | " +
          ioc.confidence +
          " | " +
          ioc.sourceEvidence +
          " → " +
          ioc.sourceModule +
          " |";
        this.insertTableRow(
          "## IOCs",
          ["Type", "Value", "Severity", "Confidence", "Source"],
          row,
        );
        ioc.includedInReport = true;
        this.report.includedIocIds.push(ioc.id);
        this.flashReport("IOC inserted into report.");
      },

      insertTimelineIntoReport(eventId) {
        const ev = this.timelineEvents.find((x) => x.id === eventId);
        if (!ev || ev.includedInReport) return;
        const row =
          "| " +
          ev.eventTime +
          " | " +
          ev.title +
          " | " +
          ev.eventType +
          " | " +
          ev.source +
          " |";
        this.insertTableRow(
          "## Incident Timeline",
          ["Time", "Event", "Type", "Source"],
          row,
        );
        ev.includedInReport = true;
        this.report.includedTimelineEventIds.push(ev.id);
        this.flashReport("Timeline event inserted into report.");
      },

      // The vendored Alpine build is the CSP-safe variant, which disables the
      // x-html directive entirely - so the preview is rendered by directly
      // setting innerHTML on a $ref from here instead of a template binding.
      openReportPreview() {
        if (this.$refs.reportPreviewBody) {
          this.$refs.reportPreviewBody.innerHTML = renderMarkdownToHtml(
            this.report.markdownContent,
          );
        }
        const dialog = document.getElementById("report-preview-dialog");
        if (dialog) {
          dialog.dataset.state = "open";
          if (!dialog.open) dialog.showModal();
        }
      },

      reportPrintDocument() {
        const body = renderMarkdownToHtml(this.report.markdownContent);
        return (
          '<!DOCTYPE html><html><head><meta charset="utf-8"><title>' +
          this.report.title +
          "</title>" +
          "<style>body{font-family:Calibri,Arial,sans-serif;color:#111;line-height:1.5;padding:2rem;max-width:800px;margin:0 auto;}" +
          "h1{font-size:1.6rem;margin-top:0;}h2{font-size:1.25rem;margin-top:1.5rem;border-bottom:1px solid #ddd;padding-bottom:.25rem;}h3{font-size:1.05rem;margin-top:1.25rem;}" +
          "table{border-collapse:collapse;width:100%;margin:.75rem 0;}td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:left;font-size:.9rem;}</style>" +
          "</head><body><h1>" +
          this.report.title +
          "</h1>" +
          body +
          "</body></html>"
        );
      },

      exportReportPdf() {
        const win = window.open("", "_blank"); // opens a blank window or tab
        if (!win) return; // if blank window/tab could not be opened, do nothing
        win.document.write(this.reportPrintDocument()); // writes the report HTML to the blank window/tab
        win.document.close(); // closes the document, ready for printing
        win.focus(); // focuses on the blank window/tab
        win.print(); // triggers the browser's print dialog
      },

      exportReportDocx() {
        /* creates a blob which is file-like object in the browser,
           containing the report HTML to be downloaded/treated as a DOCX file */
        const blob = new Blob(["﻿", this.reportPrintDocument()], {
          type: "application/msword",
        });
        const url = URL.createObjectURL(blob); // creates a URL for the blob, so it can be downloaded as a file
        const a = document.createElement("a"); // creates an anchor element to trigger the download
        a.href = url;
        a.download =
          (this.report.title || "report").replace(/[^a-z0-9-_]+/gi, "_") + // sets the filename
          ".doc";
        a.click();
        URL.revokeObjectURL(url); // releases the temporary URL from browser's memory
      },
    }),
  );

  Alpine.data("caseCreateForm", (orgMembers) => ({
    query: "",
    open: false,
    members: [],
    allMembers: orgMembers || [],

    filtered() {
      const q = this.query.trim().toLowerCase();
      const chosenIds = new Set(this.members.map((m) => m.id));
      return this.allMembers
        .filter((m) => !chosenIds.has(m.id))
        .filter(
          (m) =>
            !q ||
            m.name.toLowerCase().includes(q) ||
            m.email.toLowerCase().includes(q),
        )
        .slice(0, 8);
    },

    addMember(member) {
      if (this.members.some((existing) => existing.id === member.id)) return;
      this.members.push(member);
      this.query = "";
      this.open = false;
    },

    removeMember(id) {
      this.members = this.members.filter((m) => m.id !== id);
    },
  }));

  /* the individual case timeline page's one job: drive the single shared
     Edit dialog, since one item's fields differ from another's (task vs
     note vs milestone) - everything else on that page is plain server-
     rendered HTML/forms with no client state of its own. */
  Alpine.data("timelinePage", (itemsById, caseId) => ({
    itemsById: itemsById || {},
    caseId,
    editingItem: null,

    openEditDialog(itemId) {
      const item = this.itemsById[itemId];
      if (!item) return;
      this.editingItem = { ...item };
      const dialog = document.getElementById("edit-timeline-item-dialog");
      if (dialog) {
        dialog.dataset.state = "open";
        if (!dialog.open) dialog.showModal();
      }
    },

    editFormAction() {
      if (!this.editingItem) return "#";
      return (
        "/cases/" +
        this.caseId +
        "/timeline/items/" +
        this.editingItem.id +
        "/edit"
      );
    },
  }));

  /* Topbar "find on page" search - a real in-page text search (like
     browser Ctrl+F), not a server query. Walks every visible text node in
     <body>, wraps matches in <mark>, and lets the user step through them.
     One instance per page load since topbar() is only rendered once. */
  Alpine.data("pageSearch", () => ({
    query: "",
    matches: [],
    currentIndex: -1,

    search() {
      this.clearHighlights();
      const term = this.query.trim();
      if (!term) {
        this.currentIndex = -1;
        return;
      }
      this._highlight(term); // highlight the search term in the page
      this.currentIndex = this.matches.length ? 0 : -1;
      this._focusCurrent();
    },

    _highlight(term) {
      const lowerTerm = term.toLowerCase();
      const skipTags = new Set([
        "SCRIPT",
        "STYLE",
        "NOSCRIPT",
        "TEMPLATE",
        "TEXTAREA",
        "INPUT",
        "SELECT",
        "MARK",
      ]);
      const walker = document.createTreeWalker(
        // create a tree walker to traverse the DOM and find text nodes to highlight
        document.body,
        NodeFilter.SHOW_TEXT, // only look at text nodes
        {
          acceptNode(node) {
            const parent = node.parentElement;
            if (!parent || skipTags.has(parent.tagName))
              return NodeFilter.FILTER_REJECT;
            if (parent.closest("[data-page-search-ignore]"))
              return NodeFilter.FILTER_REJECT;
            // Elements with no client rects are either display:none
            // themselves or inside a closed <dialog>/x-show-hidden
            // ancestor - same "not actually on the page" rule a real
            // Ctrl+F respects.
            if (parent.getClientRects().length === 0)
              return NodeFilter.FILTER_REJECT;
            if (!node.nodeValue.toLowerCase().includes(lowerTerm))
              return NodeFilter.FILTER_SKIP;
            return NodeFilter.FILTER_ACCEPT;
          },
        },
      );
      const textNodes = [];
      let node;
      while ((node = walker.nextNode())) textNodes.push(node);
      for (const textNode of textNodes)
        this._wrapMatches(textNode, term, lowerTerm);
    },

    _wrapMatches(textNode, term, lowerTerm) {
      const text = textNode.nodeValue;
      const lowerText = text.toLowerCase();
      const frag = document.createDocumentFragment();
      let cursor = 0;
      let idx = lowerText.indexOf(lowerTerm, cursor);
      while (idx !== -1) {
        if (idx > cursor)
          frag.appendChild(document.createTextNode(text.slice(cursor, idx)));
        const mark = document.createElement("mark");
        mark.className = "page-search-highlight";
        mark.textContent = text.slice(idx, idx + term.length);
        frag.appendChild(mark);
        this.matches.push(mark);
        cursor = idx + term.length;
        idx = lowerText.indexOf(lowerTerm, cursor);
      }
      if (cursor < text.length)
        frag.appendChild(document.createTextNode(text.slice(cursor)));
      textNode.parentNode.replaceChild(frag, textNode);
    },

    clearHighlights() {
      document
        .querySelectorAll("mark.page-search-highlight")
        .forEach((mark) => {
          const parent = mark.parentNode;
          if (!parent) return;
          parent.replaceChild(document.createTextNode(mark.textContent), mark);
          parent.normalize();
        });
      this.matches = [];
    },

    _focusCurrent() {
      this.matches.forEach((mark, i) =>
        mark.classList.toggle("page-search-current", i === this.currentIndex),
      );
      const current = this.matches[this.currentIndex];
      if (current)
        current.scrollIntoView({ behavior: "smooth", block: "center" });
    },

    next() {
      if (!this.matches.length) return;
      this.currentIndex = (this.currentIndex + 1) % this.matches.length;
      this._focusCurrent();
    },

    prev() {
      if (!this.matches.length) return;
      this.currentIndex =
        (this.currentIndex - 1 + this.matches.length) % this.matches.length;
      this._focusCurrent();
    },

    clear() {
      this.query = "";
      this.clearHighlights();
      this.currentIndex = -1;
    },
  }));
});
