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

  const MODULE_CATEGORY_LABELS = {
    generic: "Generic / Any File",
    binary: "Binary / Executable Forensics",
    pcap: "PCAP / Network Forensics",
    email: "EML / Email Forensics",
    image: "Image Forensics",
    audio: "Audio Forensics",
    video: "Video Forensics",
    memory: "Memory Forensics",
    disk: "Disk Image Forensics",
    document: "Document Forensics",
    archive: "Archive Forensics",
    mobile: "Mobile / APK Forensics",
    logs: "Logs / EVTX / System Log Forensics",
  };
  const MODULE_CATEGORY_ORDER = Object.keys(MODULE_CATEGORY_LABELS);

  // Small factories so the ~100 module defs below don't repeat the same
  // field shape by hand every time - one place to fix a field's shape.
  function outputFormatField(options, def) {
    const opts = options || ["Text", "JSON"];
    return [
      {
        key: "outputFormat",
        label: "Output Format",
        type: "select",
        options: opts,
        default: def || opts[0],
      },
    ];
  }
  function hashFields() {
    return [
      {
        key: "hashTypes",
        label: "Hash Types",
        type: "checklist",
        options: ["MD5", "SHA1", "SHA256", "SHA512"],
        default: ["MD5", "SHA1", "SHA256"],
      },
      {
        key: "output",
        label: "Output",
        type: "select",
        options: ["Summary", "JSON", "Summary + JSON"],
        default: "Summary + JSON",
      },
    ];
  }
  function iocFields() {
    return [
      {
        key: "extractIps",
        label: "Extract IPs",
        type: "checkbox",
        default: true,
      },
      {
        key: "extractDomains",
        label: "Extract Domains",
        type: "checkbox",
        default: true,
      },
      {
        key: "extractUrls",
        label: "Extract URLs",
        type: "checkbox",
        default: true,
      },
      {
        key: "extractEmails",
        label: "Extract Emails",
        type: "checkbox",
        default: true,
      },
      {
        key: "extractHashes",
        label: "Extract Hashes",
        type: "checkbox",
        default: true,
      },
    ];
  }
  function sensitivityField() {
    return [
      {
        key: "sensitivity",
        label: "Sensitivity",
        type: "select",
        options: ["Low", "Medium", "High"],
        default: "Medium",
      },
    ];
  }
  const VOLATILITY_FIELDS = [
    {
      key: "osType",
      label: "OS Type",
      type: "select",
      options: ["Auto-detect", "Windows", "Linux", "macOS"],
      default: "Auto-detect",
    },
    {
      key: "symbolMode",
      label: "Symbol Mode",
      type: "select",
      options: ["Online symbol server", "Local symbol cache", "Offline / none"],
      default: "Online symbol server",
    },
    {
      key: "outputFormat",
      label: "Plugin Output Format",
      type: "select",
      options: ["Text", "JSON"],
      default: "JSON",
    },
  ];

  const GENERIC_MODULES = [
    {
      id: "file_identification",
      name: "File Identification",
      category: "generic",
      tool: "file / libmagic",
      description:
        "Detects the real file type from magic bytes, independent of the extension.",
      outputType: "Detected type, MIME, magic bytes",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "JSON"),
    },
    {
      id: "hash_calculation",
      name: "Hash Calculation",
      category: "generic",
      tool: "hashdeep / sha256sum",
      description:
        "Computes cryptographic hashes for integrity verification and hash-set lookups.",
      outputType: "MD5, SHA1, SHA256, SHA512",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: hashFields(),
    },
    {
      id: "metadata_extraction",
      name: "Metadata Extraction",
      category: "generic",
      tool: "exiftool",
      description: "Extracts whatever embedded metadata the file carries.",
      outputType: "Metadata table + JSON",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Table", "JSON"], "JSON"),
    },
    {
      id: "entropy_analysis",
      name: "Entropy Analysis",
      category: "generic",
      tool: "binwalk / custom entropy analyzer",
      description:
        "Scores byte-level randomness across the file to flag packed or encrypted regions.",
      outputType: "Entropy score, suspicious packed regions",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "chunkSize",
          label: "Chunk Size",
          type: "select",
          options: ["Auto", "4 KB", "64 KB"],
          default: "Auto",
        },
        {
          key: "highlightThreshold",
          label: "Highlight Threshold",
          type: "number",
          default: 7,
        },
      ],
    },
    {
      id: "strings_extraction",
      name: "Strings Extraction",
      category: "generic",
      tool: "strings / FLOSS",
      description:
        "Pulls printable strings and flags embedded indicators among them.",
      outputType: "Strings table, URLs, IPs, emails",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "minLength",
          label: "Minimum Length",
          type: "number",
          default: 6,
        },
        {
          key: "encoding",
          label: "Encoding",
          type: "select",
          options: ["ASCII", "Unicode", "Both"],
          default: "Both",
        },
        {
          key: "extractUrls",
          label: "Extract URLs",
          type: "checkbox",
          default: true,
        },
        {
          key: "extractIps",
          label: "Extract IPs",
          type: "checkbox",
          default: true,
        },
        {
          key: "extractEmails",
          label: "Extract Emails",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "ioc_extraction",
      name: "IOC Extraction",
      category: "generic",
      tool: "custom parser",
      description:
        "Parses recognizable indicators of compromise out of the file.",
      outputType: "IPs, domains, URLs, emails, hashes",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: iocFields(),
    },
    {
      id: "yara_scan",
      name: "YARA Scan",
      category: "generic",
      tool: "yara",
      description: "Matches the file against curated and custom YARA rulesets.",
      outputType: "Matched rules, matched strings, severity",
      estimatedRuntime: "~20s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: [
        {
          key: "ruleset",
          label: "Ruleset",
          type: "select",
          options: ["Malware", "Generic IOC", "Custom"],
          default: "Malware",
        },
        {
          key: "mode",
          label: "Scan Mode",
          type: "select",
          options: ["Quick", "Full"],
          default: "Full",
        },
        {
          key: "showMatchedStrings",
          label: "Show Matched Strings",
          type: "checkbox",
          default: true,
        },
        {
          key: "extractIocs",
          label: "Extract IOCs",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "recursive_artifact_extraction",
      name: "Recursive Artifact Extraction",
      category: "generic",
      tool: "binwalk / 7z / custom extractor",
      description: "Recursively unpacks embedded files and containers.",
      outputType: "Extracted embedded files",
      estimatedRuntime: "~30s",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        { key: "maxDepth", label: "Max Depth", type: "number", default: 3 },
        {
          key: "knownTypesOnly",
          label: "Known Types Only",
          type: "checkbox",
          default: true,
        },
      ],
    },
  ];

  const BINARY_MODULES = [
    {
      id: "pe_header_analysis",
      name: "PE Header Analysis",
      category: "binary",
      tool: "pefile",
      supportedTypes: ["binary"],
      description:
        "Parses Windows PE headers, sections, and import/export tables.",
      outputType: "Sections, imports, exports, timestamps",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(
        ["Summary", "Full headers + sections"],
        "Full headers + sections",
      ),
    },
    {
      id: "elf_header_analysis",
      name: "ELF Header Analysis",
      category: "binary",
      tool: "readelf / objdump",
      supportedTypes: ["binary"],
      description:
        "Parses ELF headers, sections, and symbol/library information.",
      outputType: "Sections, symbols, linked libraries",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(
        ["Summary", "Full sections + symbols"],
        "Full sections + symbols",
      ),
    },
    {
      id: "import_export_analysis",
      name: "Import / Export Analysis",
      category: "binary",
      tool: "pefile / rabin2",
      supportedTypes: ["binary"],
      description: "Lists imported APIs and exported functions.",
      outputType: "Imported APIs, exported functions",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON"),
    },
    {
      id: "packer_detection",
      name: "Packer Detection",
      category: "binary",
      tool: "Detect It Easy / custom entropy",
      supportedTypes: ["binary"],
      description:
        "Flags likely packers or compilers from signatures and entropy.",
      outputType: "Possible packer/compiler",
      estimatedRuntime: "~20s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: sensitivityField(),
    },
    {
      id: "capa_capability_detection",
      name: "Capa Capability Detection",
      category: "binary",
      tool: "capa",
      supportedTypes: ["binary"],
      description: "Maps binary behavior to recognizable malware capabilities.",
      outputType: "Malware capabilities",
      estimatedRuntime: "~1-2 minutes",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        {
          key: "outputFormat",
          label: "Output Format",
          type: "select",
          options: ["Summary", "Full ATT&CK mapping"],
          default: "Full ATT&CK mapping",
        },
      ],
    },
    {
      id: "floss_string_recovery",
      name: "FLOSS String Recovery",
      category: "binary",
      tool: "floss",
      supportedTypes: ["binary"],
      description:
        "Recovers obfuscated/decoded strings beyond a plain strings dump.",
      outputType: "Decoded strings",
      estimatedRuntime: "~1 minute",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "minLength",
          label: "Minimum Length",
          type: "number",
          default: 6,
        },
        {
          key: "decodeObfuscated",
          label: "Decode Obfuscated Strings",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "disassembly_summary",
      name: "Disassembly Summary",
      category: "binary",
      tool: "objdump / radare2",
      supportedTypes: ["binary"],
      description: "Produces a function list and high-level assembly summary.",
      outputType: "Function list, assembly summary",
      estimatedRuntime: "~1-2 minutes",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "architecture",
          label: "Architecture",
          type: "select",
          options: ["Auto-detect", "x86", "x64", "ARM"],
          default: "Auto-detect",
        },
      ],
    },
    {
      id: "ghidra_decompile",
      name: "Ghidra Decompile",
      category: "binary",
      tool: "ghidra headless",
      supportedTypes: ["binary"],
      description: "Decompiles functions and recovers symbol information.",
      outputType: "Decompiled functions, symbols",
      estimatedRuntime: "~5-10 minutes",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        {
          key: "architecture",
          label: "Architecture",
          type: "select",
          options: ["Auto-detect", "x86", "x64", "ARM"],
          default: "Auto-detect",
        },
        {
          key: "output",
          label: "Output",
          type: "select",
          options: ["Decompiled C", "Disassembly + C"],
          default: "Decompiled C",
        },
      ],
    },
    {
      id: "signature_certificate_check",
      name: "Signature / Certificate Check",
      category: "binary",
      tool: "osslsigncode / sigcheck equivalent",
      supportedTypes: ["binary"],
      description: "Verifies code-signing certificates and chain validity.",
      outputType: "Signing info, certificate status",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "verifyChain",
          label: "Verify Certificate Chain",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "suspicious_api_detection",
      name: "Suspicious API Detection",
      category: "binary",
      tool: "custom rules",
      supportedTypes: ["binary"],
      description:
        "Flags imported APIs associated with injection, networking, or persistence.",
      outputType: "Process injection, networking, persistence APIs",
      estimatedRuntime: "~20s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: sensitivityField(),
    },
  ];

  const PCAP_MODULES = [
    {
      id: "pcap_summary",
      name: "Pcap Summary",
      category: "pcap",
      tool: "capinfos / tshark",
      supportedTypes: ["pcap"],
      description:
        "Top-level capture stats: packet count, duration, protocols seen.",
      outputType: "Packet count, duration, protocols",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "timeRange",
          label: "Time Range",
          type: "select",
          options: ["Full capture", "First 10 minutes", "Custom range"],
          default: "Full capture",
        },
      ],
    },
    {
      id: "protocol_statistics",
      name: "Protocol Statistics",
      category: "pcap",
      tool: "tshark",
      supportedTypes: ["pcap"],
      description: "Breaks down traffic by protocol.",
      outputType: "Protocol distribution",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        { key: "topN", label: "Top N Protocols", type: "number", default: 10 },
      ],
    },
    {
      id: "dns_extraction",
      name: "DNS Extraction",
      category: "pcap",
      tool: "tshark / zeek",
      supportedTypes: ["pcap"],
      description:
        "Extracts queried domains and resolved IPs from DNS traffic.",
      outputType: "Queried domains, resolved IPs",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "timeRange",
          label: "Time Range",
          type: "select",
          options: ["Full capture", "Custom range"],
          default: "Full capture",
        },
        {
          key: "includeInternalDomains",
          label: "Include Internal Domains",
          type: "checkbox",
          default: false,
        },
        {
          key: "extractSuspiciousDomains",
          label: "Extract Suspicious Domains",
          type: "checkbox",
          default: true,
        },
        {
          key: "outputFormat",
          label: "Output Format",
          type: "select",
          options: ["Text", "JSON", "CSV"],
          default: "JSON",
        },
      ],
    },
    {
      id: "http_extraction",
      name: "HTTP Extraction",
      category: "pcap",
      tool: "tshark / zeek",
      supportedTypes: ["pcap"],
      description: "Extracts HTTP hosts, URLs, methods, and status codes.",
      outputType: "Hosts, URLs, methods, status codes",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "extract",
          label: "Extract",
          type: "select",
          options: ["Requests + responses", "Requests only"],
          default: "Requests + responses",
        },
        {
          key: "extractHeaders",
          label: "Extract Headers",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "tls_ssl_analysis",
      name: "TLS / SSL Analysis",
      category: "pcap",
      tool: "tshark / ja3",
      supportedTypes: ["pcap"],
      description: "Extracts SNI, JA3/JA3S fingerprints, and certificate info.",
      outputType: "SNI, JA3/JA3S, certificates",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "extractCertificates",
          label: "Extract Certificates",
          type: "checkbox",
          default: true,
        },
        {
          key: "computeJa3",
          label: "Compute JA3 / JA3S",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "tcp_conversations",
      name: "TCP Conversations",
      category: "pcap",
      tool: "tshark",
      supportedTypes: ["pcap"],
      description:
        "Lists source/destination pairs with byte and packet counts.",
      outputType: "Source/destination pairs, bytes, packets",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        { key: "minBytes", label: "Minimum Bytes", type: "number", default: 0 },
      ],
    },
    {
      id: "suspicious_connections",
      name: "Suspicious Connections",
      category: "pcap",
      tool: "custom rules",
      supportedTypes: ["pcap"],
      description:
        "Flags unusual ports, external IPs, and long-lived sessions.",
      outputType: "Unusual ports, external IPs, long sessions",
      estimatedRuntime: "~20s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: [
        {
          key: "flagExternalOnly",
          label: "Flag External IPs Only",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "pcap_file_extraction",
      name: "File Extraction",
      category: "pcap",
      tool: "zeek / tshark",
      supportedTypes: ["pcap"],
      description: "Carves out files transferred over the captured traffic.",
      outputType: "Extracted transferred files",
      estimatedRuntime: "~30s",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        {
          key: "maxFileSize",
          label: "Max File Size",
          type: "select",
          options: ["No limit", "10 MB", "50 MB"],
          default: "No limit",
        },
      ],
    },
    {
      id: "suricata_alert_scan",
      name: "Suricata Alert Scan",
      category: "pcap",
      tool: "suricata",
      supportedTypes: ["pcap"],
      description: "Replays the capture through Suricata IDS rules.",
      outputType: "IDS alerts",
      estimatedRuntime: "~1 minute",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: [
        {
          key: "rulesetVersion",
          label: "Ruleset",
          type: "select",
          options: ["Emerging Threats", "Custom"],
          default: "Emerging Threats",
        },
      ],
    },
    {
      id: "zeek_log_generation",
      name: "Zeek Log Generation",
      category: "pcap",
      tool: "zeek",
      supportedTypes: ["pcap"],
      description: "Generates Zeek's standard log set for the capture.",
      outputType: "conn.log, dns.log, http.log, ssl.log, files.log",
      estimatedRuntime: "~1 minute",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "logs",
          label: "Logs",
          type: "checklist",
          options: ["conn", "dns", "http", "ssl", "files"],
          default: ["conn", "dns", "http", "ssl", "files"],
        },
      ],
    },
    {
      id: "network_ioc_extraction",
      name: "Network IOC Extraction",
      category: "pcap",
      tool: "custom parser",
      supportedTypes: ["pcap"],
      description: "Parses recognizable network indicators out of the capture.",
      outputType: "IPs, domains, URLs, hashes",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: iocFields(),
    },
  ];

  const EMAIL_MODULES = [
    {
      id: "email_header_analysis",
      name: "Email Header Analysis",
      category: "email",
      tool: "mailparser",
      supportedTypes: ["email"],
      description:
        "Parses sender, receiver, subject, message-id, and routing headers.",
      outputType: "Sender, receiver, subject, message-id, routing",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "parseReceivedChain",
          label: "Parse Received Chain",
          type: "checkbox",
          default: true,
        },
        {
          key: "extractSenderIps",
          label: "Extract Sender IPs",
          type: "checkbox",
          default: true,
        },
        {
          key: "validateAuthResults",
          label: "Validate Authentication Results",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "received_path_analysis",
      name: "Received Path Analysis",
      category: "email",
      tool: "custom parser",
      supportedTypes: ["email"],
      description: "Reconstructs the mail relay chain and per-hop timestamps.",
      outputType: "Mail relay chain and timestamps",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "parseReceivedChain",
          label: "Parse Received Chain",
          type: "checkbox",
          default: true,
        },
        {
          key: "extractSenderIps",
          label: "Extract Sender IPs",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "spf_dkim_dmarc_check",
      name: "SPF / DKIM / DMARC Check",
      category: "email",
      tool: "auth parser / DNS resolver if allowed",
      supportedTypes: ["email"],
      description: "Evaluates the message's sender-authentication results.",
      outputType: "Authentication result",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "Network-Restricted",
      fields: [
        {
          key: "resolveDns",
          label: "Resolve DNS Live (if allowed)",
          type: "checkbox",
          default: false,
        },
      ],
    },
    {
      id: "email_url_extraction",
      name: "URL Extraction",
      category: "email",
      tool: "custom parser",
      supportedTypes: ["email"],
      description:
        "Extracts URLs and domains, optionally following redirect chains.",
      outputType: "URLs, domains, redirect chains if enabled",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "Network-Restricted",
      fields: [
        {
          key: "followRedirects",
          label: "Follow Redirects (if allowed)",
          type: "checkbox",
          default: false,
        },
      ],
    },
    {
      id: "attachment_extraction",
      name: "Attachment Extraction",
      category: "email",
      tool: "ripmime / munpack",
      supportedTypes: ["email"],
      description:
        "Pulls attachments out of the message for separate analysis.",
      outputType: "Extracted attachments",
      estimatedRuntime: "~10s",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        {
          key: "maxAttachments",
          label: "Max Attachments",
          type: "number",
          default: 10,
        },
      ],
    },
    {
      id: "attachment_hashing",
      name: "Attachment Hashing",
      category: "email",
      tool: "hashdeep",
      supportedTypes: ["email"],
      description: "Hashes every extracted attachment for lookups.",
      outputType: "Hashes of attachments",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: hashFields(),
    },
    {
      id: "phishing_indicator_scan",
      name: "Phishing Indicator Scan",
      category: "email",
      tool: "custom rules",
      supportedTypes: ["email"],
      description: "Flags suspicious senders, links, and domain mismatches.",
      outputType: "Suspicious sender, links, mismatched domains",
      estimatedRuntime: "~10s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: sensitivityField(),
    },
    {
      id: "email_ioc_extraction",
      name: "Email IOC Extraction",
      category: "email",
      tool: "custom parser",
      supportedTypes: ["email"],
      description:
        "Parses recognizable indicators out of the message and attachments.",
      outputType: "Sender IPs, domains, URLs, attachments",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: iocFields(),
    },
  ];

  const IMAGE_MODULES = [
    {
      id: "image_metadata",
      name: "Image Metadata",
      category: "image",
      tool: "exiftool",
      supportedTypes: ["image"],
      description: "Reads camera, GPS, timestamp, and software metadata.",
      outputType: "Camera, GPS, timestamps, software",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "includeGps",
          label: "Include GPS",
          type: "checkbox",
          default: true,
        },
        {
          key: "extractThumbnail",
          label: "Extract Thumbnail",
          type: "checkbox",
          default: true,
        },
        {
          key: "outputFormat",
          label: "Output Format",
          type: "select",
          options: ["Summary", "JSON"],
          default: "JSON",
        },
      ],
    },
    {
      id: "image_integrity_check",
      name: "Image Integrity Check",
      category: "image",
      tool: "jpeginfo / pngcheck",
      supportedTypes: ["image"],
      description: "Checks for corrupted or modified file structure.",
      outputType: "Corrupted or modified structure",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "strictMode",
          label: "Strict Mode",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "thumbnail_extraction",
      name: "Thumbnail Extraction",
      category: "image",
      tool: "exiftool",
      supportedTypes: ["image"],
      description: "Pulls any embedded thumbnail image out of the file.",
      outputType: "Embedded thumbnails",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["JPEG", "PNG"], "JPEG"),
    },
    {
      id: "hidden_data_check",
      name: "Hidden Data Check",
      category: "image",
      tool: "binwalk / zsteg / steghide check",
      supportedTypes: ["image"],
      description:
        "Looks for data appended or embedded beyond the visible image.",
      outputType: "Possible embedded data",
      estimatedRuntime: "~15s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: sensitivityField(),
    },
    {
      id: "image_hashing",
      name: "Image Hashing",
      category: "image",
      tool: "hashdeep",
      supportedTypes: ["image"],
      description: "Computes file hashes for integrity and lookups.",
      outputType: "File hashes",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: hashFields(),
    },
    {
      id: "pixel_dimension_analysis",
      name: "Pixel / Dimension Analysis",
      category: "image",
      tool: "imagemagick identify",
      supportedTypes: ["image"],
      description: "Reads dimensions, color space, and compression details.",
      outputType: "Dimensions, color space, compression",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "Summary"),
    },
    {
      id: "ocr_text_extraction",
      name: "OCR Text Extraction",
      category: "image",
      tool: "tesseract if available",
      supportedTypes: ["image"],
      description: "Runs OCR to recover any text rendered in the image.",
      outputType: "Detected text",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "language",
          label: "Language",
          type: "select",
          options: ["English", "Auto-detect"],
          default: "English",
        },
      ],
    },
    {
      id: "steganography_triage",
      name: "Steganography Triage",
      category: "image",
      tool: "zsteg / stegdetect-style checks",
      supportedTypes: ["image"],
      description: "Runs quick checks for common steganographic channels.",
      outputType: "Possible hidden channels",
      estimatedRuntime: "~20s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: sensitivityField(),
    },
  ];

  const AUDIO_MODULES = [
    {
      id: "audio_metadata",
      name: "Audio Metadata",
      category: "audio",
      tool: "exiftool / mediainfo",
      supportedTypes: ["audio"],
      description: "Reads codec, bitrate, timestamp, and tag metadata.",
      outputType: "Codec, bitrate, timestamps, tags",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON"),
    },
    {
      id: "waveform_summary",
      name: "Waveform Summary",
      category: "audio",
      tool: "ffmpeg / sox",
      supportedTypes: ["audio"],
      description: "Summarizes duration, channels, and sample rate.",
      outputType: "Duration, channels, sample rate",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "Summary"),
    },
    {
      id: "spectrogram_generation",
      name: "Spectrogram Generation",
      category: "audio",
      tool: "sox / ffmpeg",
      supportedTypes: ["audio"],
      description: "Renders a spectrogram image artifact for visual review.",
      outputType: "Spectrogram image artifact",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "frequencyRange",
          label: "Frequency Range",
          type: "select",
          options: ["0-8 kHz", "0-16 kHz", "Full spectrum"],
          default: "Full spectrum",
        },
        {
          key: "generatePng",
          label: "Generate PNG Artifact",
          type: "checkbox",
          default: true,
        },
        {
          key: "outputFormat",
          label: "Output Format",
          type: "select",
          options: ["PNG", "JSON"],
          default: "PNG",
        },
      ],
    },
    {
      id: "hidden_tone_dtmf_detection",
      name: "Hidden Tone / DTMF Detection",
      category: "audio",
      tool: "multimon-ng / custom analyzer",
      supportedTypes: ["audio"],
      description: "Detects DTMF tones or other encoded tone sequences.",
      outputType: "Detected tones or sequences",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: sensitivityField(),
    },
    {
      id: "audio_hashing",
      name: "Audio Hashing",
      category: "audio",
      tool: "hashdeep",
      supportedTypes: ["audio"],
      description: "Computes file hashes for integrity and lookups.",
      outputType: "Hashes",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: hashFields(),
    },
    {
      id: "silence_spike_detection",
      name: "Silence / Spike Detection",
      category: "audio",
      tool: "custom analyzer",
      supportedTypes: ["audio"],
      description: "Flags abnormal silence gaps or volume spikes.",
      outputType: "Suspicious silence, spikes, anomalies",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "thresholdDb",
          label: "Threshold (dB)",
          type: "number",
          default: -40,
        },
      ],
    },
  ];

  const VIDEO_MODULES = [
    {
      id: "video_metadata",
      name: "Video Metadata",
      category: "video",
      tool: "mediainfo / exiftool",
      supportedTypes: ["video"],
      description: "Reads codec, duration, resolution, and timestamp metadata.",
      outputType: "Codec, duration, resolution, timestamps",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON"),
    },
    {
      id: "frame_extraction",
      name: "Frame Extraction",
      category: "video",
      tool: "ffmpeg",
      supportedTypes: ["video"],
      description: "Extracts frames at a fixed interval for review.",
      outputType: "Selected frames",
      estimatedRuntime: "~30s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "interval",
          label: "Interval",
          type: "select",
          options: ["Every 1s", "Every 5s", "Every 10s"],
          default: "Every 5s",
        },
      ],
    },
    {
      id: "keyframe_extraction",
      name: "Keyframe Extraction",
      category: "video",
      tool: "ffmpeg",
      supportedTypes: ["video"],
      description: "Extracts only the encoded keyframes.",
      outputType: "Keyframes",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        { key: "maxFrames", label: "Max Frames", type: "number", default: 20 },
      ],
    },
    {
      id: "audio_track_extraction",
      name: "Audio Track Extraction",
      category: "video",
      tool: "ffmpeg",
      supportedTypes: ["video"],
      description: "Pulls the audio track out as a standalone artifact.",
      outputType: "Audio artifact",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["WAV", "MP3"], "WAV"),
    },
    {
      id: "video_hashing",
      name: "Video Hashing",
      category: "video",
      tool: "hashdeep",
      supportedTypes: ["video"],
      description: "Computes file hashes for integrity and lookups.",
      outputType: "Hashes",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: hashFields(),
    },
  ];

  const MEMORY_MODULES = [
    [
      "memory_image_info",
      "Memory Image Info",
      "volatility3",
      "OS info, symbols, architecture",
      "Low",
    ],
    [
      "process_list",
      "Process List",
      "volatility3 pslist",
      "Process table",
      "Low",
    ],
    [
      "process_tree",
      "Process Tree",
      "volatility3 pstree",
      "Parent-child process tree",
      "Low",
    ],
    [
      "process_scan",
      "Process Scan",
      "volatility3 psscan",
      "Hidden/terminated process scan",
      "Medium",
    ],
    [
      "network_connections",
      "Network Connections",
      "volatility3 netscan",
      "Sockets, connections, listening ports",
      "Medium",
    ],
    [
      "command_line",
      "Command Line",
      "volatility3 cmdline",
      "Process command lines",
      "Low",
    ],
    [
      "dll_list",
      "DLL List",
      "volatility3 dlllist",
      "Loaded DLLs/modules",
      "Low",
    ],
    [
      "malfind",
      "Malfind",
      "volatility3 malfind",
      "Injected/suspicious memory regions",
      "High",
    ],
    ["handles", "Handles", "volatility3 handles", "Process handles", "Low"],
    ["services", "Services", "volatility3 svcscan", "Windows services", "Low"],
    [
      "registry_hive_list",
      "Registry Hive List",
      "volatility3 hivelist",
      "Registry hives",
      "Low",
    ],
    [
      "execution_artifacts",
      "UserAssist / Shimcache / Amcache",
      "volatility3 plugins",
      "Execution artifacts",
      "Medium",
    ],
  ].map(([id, name, tool, output, risk]) => ({
    id,
    name,
    category: "memory",
    tool,
    supportedTypes: ["memory"],
    description: name + " via " + tool + ".",
    outputType: output,
    estimatedRuntime: "1-6 minutes",
    riskLevel: risk,
    isolationLevel: "None",
    fields: VOLATILITY_FIELDS,
  }));

  const DISK_MODULES = [
    {
      id: "partition_table",
      name: "Partition Table",
      category: "disk",
      tool: "mmls",
      supportedTypes: ["disk"],
      description: "Lists partitions and their offsets within the image.",
      outputType: "Partitions and offsets",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text"),
    },
    {
      id: "filesystem_info",
      name: "File System Info",
      category: "disk",
      tool: "fsstat",
      supportedTypes: ["disk"],
      description: "Reads filesystem-level metadata for a partition.",
      outputType: "Filesystem metadata",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text"),
    },
    {
      id: "file_listing",
      name: "File Listing",
      category: "disk",
      tool: "fls",
      supportedTypes: ["disk"],
      description: "Walks the filesystem tree and lists every file.",
      outputType: "File tree",
      estimatedRuntime: "~1-3 minutes",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "includeDeleted",
          label: "Include Deleted Entries",
          type: "checkbox",
          default: false,
        },
      ],
    },
    {
      id: "deleted_file_listing",
      name: "Deleted File Listing",
      category: "disk",
      tool: "fls with deleted entries",
      supportedTypes: ["disk"],
      description: "Lists filesystem entries marked deleted.",
      outputType: "Deleted files",
      estimatedRuntime: "~1-3 minutes",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "recoverableOnly",
          label: "Recoverable Only",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "disk_file_extraction",
      name: "File Extraction",
      category: "disk",
      tool: "icat / tsk_recover",
      supportedTypes: ["disk"],
      description: "Carves out specific files by inode/offset.",
      outputType: "Extracted selected files",
      estimatedRuntime: "~30s-2 minutes",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        {
          key: "maxFileSize",
          label: "Max File Size",
          type: "select",
          options: ["No limit", "10 MB", "50 MB"],
          default: "No limit",
        },
      ],
    },
    {
      id: "timeline_generation",
      name: "Timeline Generation",
      category: "disk",
      tool: "log2timeline / fls bodyfile",
      supportedTypes: ["disk"],
      description: "Builds a filesystem-wide MAC-time timeline.",
      outputType: "Filesystem timeline",
      estimatedRuntime: "3-10 minutes",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "timezone",
          label: "Timezone",
          type: "select",
          options: ["UTC", "System default", "Custom"],
          default: "UTC",
        },
        {
          key: "includeDeletedFiles",
          label: "Include Deleted Files",
          type: "checkbox",
          default: true,
        },
        {
          key: "outputFormat",
          label: "Output Format",
          type: "select",
          options: ["CSV", "JSON"],
          default: "CSV",
        },
      ],
    },
    {
      id: "browser_artifact_scan",
      name: "Browser Artifact Scan",
      category: "disk",
      tool: "custom parser / sqlite parsers",
      supportedTypes: ["disk"],
      description:
        "Recovers browser history, downloads, and cookies if present.",
      outputType: "History, downloads, cookies if present",
      estimatedRuntime: "~1 minute",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "includeCookies",
          label: "Include Cookies",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "windows_registry_extraction",
      name: "Windows Registry Extraction",
      category: "disk",
      tool: "regripper / hivex",
      supportedTypes: ["disk"],
      description: "Extracts artifacts from the Windows registry hives.",
      outputType: "Registry artifacts",
      estimatedRuntime: "~1 minute",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "hives",
          label: "Hives",
          type: "checklist",
          options: ["SYSTEM", "SOFTWARE", "SAM", "NTUSER.DAT"],
          default: ["SYSTEM", "SOFTWARE"],
        },
      ],
    },
    {
      id: "event_log_extraction",
      name: "Event Log Extraction",
      category: "disk",
      tool: "evtx_dump / chainsaw / hayabusa",
      supportedTypes: ["disk"],
      description: "Extracts and runs detections over Windows event logs.",
      outputType: "Windows event logs and detections",
      estimatedRuntime: "1-3 minutes",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: [
        {
          key: "sigmaRules",
          label: "Run Sigma Rules",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "prefetch_analysis",
      name: "Prefetch Analysis",
      category: "disk",
      tool: "prefetch parser",
      supportedTypes: ["disk"],
      description: "Lists programs executed according to Prefetch records.",
      outputType: "Executed programs",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text"),
    },
    {
      id: "lnk_jumplist_analysis",
      name: "LNK / JumpList Analysis",
      category: "disk",
      tool: "lnk parser",
      supportedTypes: ["disk"],
      description:
        "Parses shortcut and jump-list artifacts for accessed paths.",
      outputType: "Shortcut artifacts",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text"),
    },
  ];

  const DOCUMENT_MODULES = [
    {
      id: "document_metadata",
      name: "Document Metadata",
      category: "document",
      tool: "exiftool",
      supportedTypes: ["document"],
      description: "Reads author, timestamp, and producer-software metadata.",
      outputType: "Author, timestamps, producer software",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON"),
    },
    {
      id: "pdf_structure_analysis",
      name: "PDF Structure Analysis",
      category: "document",
      tool: "pdfid / pdf-parser",
      supportedTypes: ["document"],
      description: "Inspects PDF objects for embedded JavaScript and files.",
      outputType: "Objects, JavaScript, embedded files",
      estimatedRuntime: "~15s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: [
        {
          key: "extractJavascript",
          label: "Extract JavaScript",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "office_macro_analysis",
      name: "Office Macro Analysis",
      category: "document",
      tool: "olevba",
      supportedTypes: ["document"],
      description: "Extracts and flags suspicious VBA macro content.",
      outputType: "Macros, suspicious keywords",
      estimatedRuntime: "~15s",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        {
          key: "deobfuscate",
          label: "Deobfuscate",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "embedded_object_extraction",
      name: "Embedded Object Extraction",
      category: "document",
      tool: "oletools / binwalk",
      supportedTypes: ["document"],
      description: "Pulls embedded OLE objects and files out of the document.",
      outputType: "Embedded files",
      estimatedRuntime: "~20s",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        {
          key: "maxObjects",
          label: "Max Objects",
          type: "number",
          default: 50,
        },
      ],
    },
    {
      id: "document_link_extraction",
      name: "Link Extraction",
      category: "document",
      tool: "custom parser",
      supportedTypes: ["document"],
      description: "Extracts URLs and domains referenced in the document.",
      outputType: "URLs/domains",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "Network-Restricted",
      fields: [
        {
          key: "followRedirects",
          label: "Follow Redirects (if allowed)",
          type: "checkbox",
          default: false,
        },
      ],
    },
    {
      id: "suspicious_document_indicators",
      name: "Suspicious Document Indicators",
      category: "document",
      tool: "custom rules",
      supportedTypes: ["document"],
      description:
        "Flags auto-open macros, obfuscation, and external template injection.",
      outputType: "Auto-open macros, obfuscation, external templates",
      estimatedRuntime: "~15s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: sensitivityField(),
    },
  ];

  const ARCHIVE_MODULES = [
    {
      id: "archive_listing",
      name: "Archive Listing",
      category: "archive",
      tool: "7z / unzip / unrar",
      supportedTypes: ["archive"],
      description: "Lists the archive's contents without extracting.",
      outputType: "File list",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text"),
    },
    {
      id: "archive_metadata",
      name: "Archive Metadata",
      category: "archive",
      tool: "7z / exiftool",
      supportedTypes: ["archive"],
      description: "Reads compression method and per-entry timestamps.",
      outputType: "Compression info, timestamps",
      estimatedRuntime: "~10s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "JSON"),
    },
    {
      id: "archive_recursive_extraction",
      name: "Recursive Extraction",
      category: "archive",
      tool: "7z / custom extractor",
      supportedTypes: ["archive"],
      description: "Recursively extracts nested archives.",
      outputType: "Extracted files",
      estimatedRuntime: "~30s-2 minutes",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        { key: "maxDepth", label: "Max Depth", type: "number", default: 5 },
      ],
    },
    {
      id: "password_protection_check",
      name: "Password Protection Check",
      category: "archive",
      tool: "7z",
      supportedTypes: ["archive"],
      description: "Checks whether the archive is password-protected.",
      outputType: "Protected/not protected",
      estimatedRuntime: "~5s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "bruteForceCommon",
          label: "Try Common Passwords",
          type: "checkbox",
          default: false,
        },
      ],
    },
    {
      id: "nested_file_type_detection",
      name: "Nested File Type Detection",
      category: "archive",
      tool: "file / libmagic",
      supportedTypes: ["archive"],
      description: "Detects the real type of every extracted file.",
      outputType: "Detected types of extracted files",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "JSON"),
    },
  ];

  const MOBILE_MODULES = [
    {
      id: "apk_manifest_analysis",
      name: "APK Manifest Analysis",
      category: "mobile",
      tool: "apktool / androguard",
      supportedTypes: ["mobile"],
      description:
        "Parses the manifest for package info, activities, and services.",
      outputType: "Package info, activities, services",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON"),
    },
    {
      id: "apk_permission_analysis",
      name: "APK Permission Analysis",
      category: "mobile",
      tool: "androguard",
      supportedTypes: ["mobile"],
      description: "Lists requested permissions and flags dangerous ones.",
      outputType: "Requested permissions",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "flagDangerousOnly",
          label: "Flag Dangerous Permissions Only",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "jadx_decompile",
      name: "JADX Decompile",
      category: "mobile",
      tool: "jadx",
      supportedTypes: ["mobile"],
      description: "Decompiles the APK back to a Java source tree.",
      outputType: "Java source tree",
      estimatedRuntime: "1-3 minutes",
      riskLevel: "Medium",
      isolationLevel: "Sandboxed",
      fields: [
        {
          key: "outputFormat",
          label: "Output Format",
          type: "select",
          options: ["Java source", "Smali"],
          default: "Java source",
        },
      ],
    },
    {
      id: "mobile_resource_extraction",
      name: "Resource Extraction",
      category: "mobile",
      tool: "apktool",
      supportedTypes: ["mobile"],
      description: "Extracts resources and assets bundled in the package.",
      outputType: "Resources, assets",
      estimatedRuntime: "~30s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        { key: "maxFiles", label: "Max Files", type: "number", default: 200 },
      ],
    },
    {
      id: "mobile_ioc_extraction",
      name: "Mobile IOC Extraction",
      category: "mobile",
      tool: "custom parser",
      supportedTypes: ["mobile"],
      description:
        "Parses recognizable indicators out of strings and resources.",
      outputType: "URLs, IPs, domains, keys",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: iocFields(),
    },
    {
      id: "tracker_sdk_detection",
      name: "Tracker / SDK Detection",
      category: "mobile",
      tool: "custom signatures",
      supportedTypes: ["mobile"],
      description: "Flags known third-party tracker and ad-SDK libraries.",
      outputType: "Detected libraries/SDKs",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: sensitivityField(),
    },
    {
      id: "ios_ipa_metadata",
      name: "iOS IPA Metadata",
      category: "mobile",
      tool: "unzip / plist parser",
      supportedTypes: ["mobile"],
      description: "Reads Info.plist and entitlements from an iOS package.",
      outputType: "Info.plist, entitlements",
      estimatedRuntime: "~15s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON"),
    },
  ];

  const LOGS_MODULES = [
    {
      id: "evtx_parse",
      name: "EVTX Parse",
      category: "logs",
      tool: "evtx_dump",
      supportedTypes: ["logs"],
      description: "Parses Windows EVTX records into a structured form.",
      outputType: "Parsed events",
      estimatedRuntime: "~30s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "eventIdFilter",
          label: "Event ID Filter",
          type: "select",
          options: ["All", "Security only", "System only"],
          default: "All",
        },
      ],
    },
    {
      id: "sigma_rule_scan",
      name: "Sigma Rule Scan",
      category: "logs",
      tool: "chainsaw / hayabusa",
      supportedTypes: ["logs"],
      description: "Runs Sigma detection rules over the parsed log records.",
      outputType: "Detections",
      estimatedRuntime: "~1 minute",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: [
        {
          key: "rulesetVersion",
          label: "Ruleset",
          type: "select",
          options: ["Default", "Custom"],
          default: "Default",
        },
      ],
    },
    {
      id: "windows_logon_events",
      name: "Windows Logon Events",
      category: "logs",
      tool: "custom EVTX parser",
      supportedTypes: ["logs"],
      description: "Summarizes logon/logoff activity from Security events.",
      outputType: "Logon/logoff activity",
      estimatedRuntime: "~30s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text"),
    },
    {
      id: "powershell_event_analysis",
      name: "PowerShell Event Analysis",
      category: "logs",
      tool: "chainsaw / custom rules",
      supportedTypes: ["logs"],
      description: "Flags script-block logging events and decodes obfuscation.",
      outputType: "Script block indicators",
      estimatedRuntime: "~30s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: [
        {
          key: "decodeBase64",
          label: "Decode Base64 Payloads",
          type: "checkbox",
          default: true,
        },
      ],
    },
    {
      id: "web_access_log_analysis",
      name: "Web Access Log Analysis",
      category: "logs",
      tool: "custom parser",
      supportedTypes: ["logs"],
      description:
        "Summarizes requests by IP, path, status code, and user agent.",
      outputType: "IPs, paths, status codes, user agents",
      estimatedRuntime: "~20s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "JSON"),
    },
    {
      id: "auth_log_analysis",
      name: "Auth Log Analysis",
      category: "logs",
      tool: "custom parser",
      supportedTypes: ["logs"],
      description: "Flags failed logins, SSH activity, and sudo usage.",
      outputType: "Failed logins, SSH activity, sudo usage",
      estimatedRuntime: "~20s",
      riskLevel: "Medium",
      isolationLevel: "None",
      fields: [
        {
          key: "flagFailedOnly",
          label: "Flag Failed Attempts Only",
          type: "checkbox",
          default: false,
        },
      ],
    },
    {
      id: "log_timeline_builder",
      name: "Timeline Builder",
      category: "logs",
      tool: "custom timeline normalizer",
      supportedTypes: ["logs"],
      description: "Normalizes parsed log events into a single timeline.",
      outputType: "Timeline events",
      estimatedRuntime: "~30s",
      riskLevel: "Low",
      isolationLevel: "None",
      fields: [
        {
          key: "timezone",
          label: "Timezone",
          type: "select",
          options: ["UTC", "System default"],
          default: "UTC",
        },
      ],
    },
  ];

  const MODULE_REGISTRY = [
    ...GENERIC_MODULES,
    ...BINARY_MODULES,
    ...PCAP_MODULES,
    ...EMAIL_MODULES,
    ...IMAGE_MODULES,
    ...AUDIO_MODULES,
    ...VIDEO_MODULES,
    ...MEMORY_MODULES,
    ...DISK_MODULES,
    ...DOCUMENT_MODULES,
    ...ARCHIVE_MODULES,
    ...MOBILE_MODULES,
    ...LOGS_MODULES,
  ];
  const MODULE_MAP = {};
  MODULE_REGISTRY.forEach((m) => {
    MODULE_MAP[m.id] = m;
  });

  function isModuleCompatible(module, evidenceType) {
    // "generic" category modules (hashing, strings, YARA, etc.) apply to
    // every evidence type, including files we couldn't classify at all.
    return (
      module.category === "generic" ||
      (module.supportedTypes || []).includes(evidenceType)
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
    if (module.category === "pcap") return "network";
    if (module.category === "email") return "email";
    if (module.category === "memory") return "memory";
    if (module.category === "generic") return "basic_triage";
    if (
      module.riskLevel === "High" ||
      (module.isolationLevel && module.isolationLevel !== "None")
    )
      return "advanced";
    return "standard";
  }

  // Mock subscription gating: which plan a module requires is derived the
  // same way - advanced-tier modules need the top plan, basic triage is
  // free for everyone, everything else needs at least Analyst unless it's
  // explicitly low-risk. No per-module "requiredPlan" field to maintain.
  const PLAN_ORDER = ["Free", "Analyst", "Advanced"];
  function requiredPlanOf(module) {
    const tier = moduleTierOf(module);
    if (tier === "advanced") return "Advanced";
    if (tier === "basic_triage") return "Free";
    return module.riskLevel === "Low" ? "Free" : "Analyst";
  }
  function isModuleLocked(module, userPlan) {
    return (
      PLAN_ORDER.indexOf(requiredPlanOf(module)) > PLAN_ORDER.indexOf(userPlan)
    );
  }

  function mockOutputFor(module, evidenceName) {
    return (
      "Mock " +
      module.outputType.toLowerCase() +
      " generated for " +
      evidenceName +
      " via " +
      module.tool +
      "."
    );
  }

  // Result Canvas deep output - findings/IOCs/artifacts/raw stdout+stderr,
  // derived from the module's existing category/tool/outputType fields
  // (same "derive, don't hand-tag" approach as moduleTierOf/requiredPlanOf)
  // rather than authoring per-module mock content for ~104 modules.
  const ARTIFACT_CATEGORIES = [
    "pcap",
    "memory",
    "disk",
    "image",
    "archive",
    "binary",
  ];
  function mockDeepOutputFor(module, evidenceName) {
    const findings = [
      module.name + " completed against " + evidenceName + " with no errors.",
      "Output classified as " + module.outputType + " via " + module.tool + ".",
    ];
    let iocs;
    if (module.category === "pcap") {
      iocs = [
        { type: "ip", value: "203.0.113.45" },
        { type: "domain", value: "malicious-update.net" },
      ];
    } else if (module.category === "email") {
      iocs = [
        { type: "domain", value: "phish-relay.example" },
        { type: "url", value: "http://phish-relay.example/login" },
      ];
    } else {
      iocs = [
        {
          type: "hash",
          value:
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        },
      ];
    }
    const artifacts = ARTIFACT_CATEGORIES.includes(module.category)
      ? [
          {
            name:
              evidenceName + "_extracted." + module.outputType.toLowerCase(),
            type: module.outputType,
          },
        ]
      : [];
    const rawOutput = {
      stdout: [
        "[" + module.tool + "] starting analysis of " + evidenceName,
        "[" + module.tool + "] module: " + module.name,
        "[" + module.tool + "] output type: " + module.outputType,
        "[" + module.tool + "] completed successfully.",
      ],
      stderr: [],
    };
    return { findings, iocs, artifacts, rawOutput };
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

  /* this component manages the Analyze tab's planner and job queue */
  Alpine.data(
    "analyzeWorkspace",
    (evidenceItems, userPlan, caseId, caseTitle, currentUserName) => ({
      /*
    this analyze page needs to remember some things while the user is using it
    and those things are called "state" variables
    */
      moduleMap: MODULE_MAP,
      evidenceTypeLabels: EVIDENCE_TYPE_LABELS,
      moduleTierLabels: MODULE_TIER_LABELS,
      userPlan: userPlan || "Free", // mock subscription tier gating which modules are locked
      evidence: evidenceItems || [], // for remembering the evidence items (files) inside Alpine (state)
      caseId: caseId || null,
      currentUserName: currentUserName || "Analyst",

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

      init() {
        // Single shared ticker advancing every queued/running task across
        // every job - cheap no-op when nothing's queued, see _tickProgress.
        setInterval(() => this._tickProgress(), 500);
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
        const dialog = document.getElementById("analyze-evidence-dialog");
        if (dialog) {
          dialog.dataset.state = "open";
          if (!dialog.open) dialog.showModal();
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
        const type = this.evidenceTypeOf(this.analyzingEvidence);
        return MODULE_REGISTRY.filter((m) => isModuleCompatible(m, type));
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
        const tiers = new Set(mods.map((m) => moduleTierOf(m)));
        return {
          moduleCount: mods.length,
          taskCount: mods.length,
          containerRuns: tiers.size,
          estimatedMinutes:
            mods.length === 0 ? 0 : Math.max(2, mods.length * 2),
        };
      },

      // "Next": groups the checked modules into one job per tier (every Basic
      // Triage Bundle module shares one container/job; everything else gets
      // its own job) and queues them, then switches straight to the Analysis
      // Progress dialog - there's no separate "review plan" step once modules
      // are checked here.
      startAnalysis() {
        if (!this.checkedModuleIds.length || !this.analyzingEvidence) return;
        const evidence = this.analyzingEvidence;
        const mods = this.checkedModuleIds
          .map((id) => this.moduleMap[id])
          .filter(Boolean);
        const byTier = {};
        mods.forEach((m) => {
          const tier = moduleTierOf(m);
          (byTier[tier] = byTier[tier] || []).push(m);
        });

        const newJobIds = [];
        MODULE_TIER_ORDER.forEach((tier) => {
          if (!byTier[tier]) return;
          const jobId = evidence.id + ":" + tier + ":" + Date.now();
          newJobIds.push(jobId);
          this.queue.push({
            id: jobId,
            tier,
            tierLabel: MODULE_TIER_LABELS[tier],
            evidenceId: evidence.id,
            evidenceName: evidence.filename,
            tasks: byTier[tier].map((m) => ({
              id: jobId + ":" + m.id,
              moduleId: m.id,
              moduleName: m.name,
              tool: m.tool,
              outputType: m.outputType,
              risk: m.riskLevel,
              isolation: m.isolationLevel,
              summary: this.optionsSummaryFor(m.id),
              status: "Queued",
              progress: 0,
            })),
          });
        });

        this.activeProgressJobIds = newJobIds;
        this.closeAnalyzeDialog();
        const queueDialog = document.getElementById("current-job-queue");
        if (queueDialog) {
          queueDialog.dataset.state = "open";
          if (!queueDialog.open) queueDialog.showModal();
        }
      },

      // Jobs the Analysis Progress dialog currently displays - the most
      // recently started run, matching the wireframe's single "Evidence: …"
      // header rather than every run ever queued.
      progressJobs() {
        return this.queue.filter((j) =>
          this.activeProgressJobIds.includes(j.id),
        );
      },

      // Drives every queued/running task across every job: each job runs its
      // tasks sequentially (it's "one container"), advancing whichever task
      // is active by a fixed chunk each tick until it completes and drops a
      // mock result into Results - this is what makes Queued/Running/
      // Completed coexist instead of every job mock-finishing instantly.
      _tickProgress() {
        let changed = false;
        this.queue.forEach((job) => {
          const task =
            job.tasks.find((t) => t.status === "Running") ||
            job.tasks.find((t) => t.status === "Queued");
          if (!task) return;
          if (task.status === "Queued") task.status = "Running";
          task.progress = Math.min(100, task.progress + 20);
          changed = true;
          if (task.progress >= 100) {
            task.status = "Completed";
            const mod = this.moduleMap[task.moduleId];
            const deep = mockDeepOutputFor(mod, job.evidenceName);
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
              output: mockOutputFor(mod, job.evidenceName),
              findings: deep.findings,
              iocs: deep.iocs,
              artifacts: deep.artifacts,
              rawOutput: deep.rawOutput,
            });
          }
        });
        if (changed) this.queue = [...this.queue];
      },

      // Cancelling a queued/running task marks it Failed instead of deleting
      // it outright - a cancelled job should leave a visible trace (the
      // Results tab's Failed count, the Result Canvas's ⚠ status) rather than
      // silently vanishing. Re-Analyze from the canvas is how you retry it.
      cancelTask(jobId, taskId) {
        const job = this.queue.find((j) => j.id === jobId);
        if (!job) return;
        const task = job.tasks.find((t) => t.id === taskId);
        if (!task) return;
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
        this.queue = [...this.queue];
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

      openResultCanvasFor(evidenceId) {
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
        const compatible = type
          ? MODULE_REGISTRY.filter((m) => isModuleCompatible(m, type))
          : [];

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

      saveCanvasNote() {
        if (!this.canvasSelectedModuleId) return;
        this.notesByKey[this.canvasNoteKeyFor(this.canvasSelectedModuleId)] =
          this.canvasNoteDraft;
        this.flashCanvas("Note saved.");
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
          summary: result ? result.output : null,
          findings: result ? result.findings : [],
          iocs: result ? result.iocs : [],
          artifacts: result ? result.artifacts : [],
          rawOutput: result ? result.rawOutput : { stdout: [], stderr: [] },
        };
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
        this.caseFindings.push({
          id: this.canvasEvidenceId + ":" + output.moduleId + ":" + Date.now(),
          caseId: this.caseId,
          title,
          severity: severityOfModule(mod),
          confidence: confidenceOfModule(mod),
          sourceEvidence: this.canvasEvidenceName,
          sourceModule: output.moduleName,
          description,
          includedInReport: false,
        });
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
        this.timelineEvents.push({
          id: this.canvasEvidenceId + ":" + output.moduleId + ":" + Date.now(),
          caseId: this.caseId,
          eventTime: formatTimelineTimestamp(Date.now()),
          title: output.moduleName + " completed on " + this.canvasEvidenceName,
          eventType,
          source: this.canvasEvidenceName + " → " + output.moduleName,
          confidence: confidenceOfModule(mod),
          includedInReport: false,
        });
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

      saveDraft() {
        this.report.updatedBy = this.currentUserName;
        this.flashReport("Draft saved.");
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
