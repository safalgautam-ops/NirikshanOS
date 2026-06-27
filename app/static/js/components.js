// Small Alpine.data() components that need real JS (DOM measurement, multi-
// statement logic) the CSP build's inline-attribute parser can't run - see
// the comment in layouts/base.html on why that parser only handles simple
// expressions. Lives in a real same-origin file, so CSP (script-src 'self')
// allows it; this is the supported way to do anything non-trivial with the
// CSP build, not a workaround.
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
        "width:" + active.offsetWidth + "px;" +
        "height:" + active.offsetHeight + "px;" +
        "transform:translateX(" + active.offsetLeft + "px)";
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
      const container = this.$root.querySelector('[data-wizard-step="' + n + '"]');
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
    document: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "rtf", "odt"],
    archive: ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"],
    mobile: ["apk", "aab", "dex", "jar", "ipa"],
    logs: ["evtx", "log", "jsonl", "syslog"],
    generic: ["txt", "csv", "json", "xml", "ini", "cfg", "dat", "plist", "db", "sqlite", "html", "htm", "md", "yaml", "yml"],
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
    return [{ key: "outputFormat", label: "Output Format", type: "select", options: opts, default: def || opts[0] }];
  }
  function hashFields() {
    return [
      { key: "hashTypes", label: "Hash Types", type: "checklist", options: ["MD5", "SHA1", "SHA256", "SHA512"], default: ["MD5", "SHA1", "SHA256"] },
      { key: "output", label: "Output", type: "select", options: ["Summary", "JSON", "Summary + JSON"], default: "Summary + JSON" },
    ];
  }
  function iocFields() {
    return [
      { key: "extractIps", label: "Extract IPs", type: "checkbox", default: true },
      { key: "extractDomains", label: "Extract Domains", type: "checkbox", default: true },
      { key: "extractUrls", label: "Extract URLs", type: "checkbox", default: true },
      { key: "extractEmails", label: "Extract Emails", type: "checkbox", default: true },
      { key: "extractHashes", label: "Extract Hashes", type: "checkbox", default: true },
    ];
  }
  function sensitivityField() {
    return [{ key: "sensitivity", label: "Sensitivity", type: "select", options: ["Low", "Medium", "High"], default: "Medium" }];
  }
  const VOLATILITY_FIELDS = [
    { key: "osType", label: "OS Type", type: "select", options: ["Auto-detect", "Windows", "Linux", "macOS"], default: "Auto-detect" },
    { key: "symbolMode", label: "Symbol Mode", type: "select", options: ["Online symbol server", "Local symbol cache", "Offline / none"], default: "Online symbol server" },
    { key: "outputFormat", label: "Plugin Output Format", type: "select", options: ["Text", "JSON"], default: "JSON" },
  ];

  const GENERIC_MODULES = [
    { id: "file_identification", name: "File Identification", category: "generic", tool: "file / libmagic",
      description: "Detects the real file type from magic bytes, independent of the extension.",
      outputType: "Detected type, MIME, magic bytes", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "JSON") },
    { id: "hash_calculation", name: "Hash Calculation", category: "generic", tool: "hashdeep / sha256sum",
      description: "Computes cryptographic hashes for integrity verification and hash-set lookups.",
      outputType: "MD5, SHA1, SHA256, SHA512", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: hashFields() },
    { id: "metadata_extraction", name: "Metadata Extraction", category: "generic", tool: "exiftool",
      description: "Extracts whatever embedded metadata the file carries.",
      outputType: "Metadata table + JSON", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Table", "JSON"], "JSON") },
    { id: "entropy_analysis", name: "Entropy Analysis", category: "generic", tool: "binwalk / custom entropy analyzer",
      description: "Scores byte-level randomness across the file to flag packed or encrypted regions.",
      outputType: "Entropy score, suspicious packed regions", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "chunkSize", label: "Chunk Size", type: "select", options: ["Auto", "4 KB", "64 KB"], default: "Auto" },
        { key: "highlightThreshold", label: "Highlight Threshold", type: "number", default: 7 },
      ] },
    { id: "strings_extraction", name: "Strings Extraction", category: "generic", tool: "strings / FLOSS",
      description: "Pulls printable strings and flags embedded indicators among them.",
      outputType: "Strings table, URLs, IPs, emails", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "minLength", label: "Minimum Length", type: "number", default: 6 },
        { key: "encoding", label: "Encoding", type: "select", options: ["ASCII", "Unicode", "Both"], default: "Both" },
        { key: "extractUrls", label: "Extract URLs", type: "checkbox", default: true },
        { key: "extractIps", label: "Extract IPs", type: "checkbox", default: true },
        { key: "extractEmails", label: "Extract Emails", type: "checkbox", default: true },
      ] },
    { id: "ioc_extraction", name: "IOC Extraction", category: "generic", tool: "custom parser",
      description: "Parses recognizable indicators of compromise out of the file.",
      outputType: "IPs, domains, URLs, emails, hashes", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: iocFields() },
    { id: "yara_scan", name: "YARA Scan", category: "generic", tool: "yara",
      description: "Matches the file against curated and custom YARA rulesets.",
      outputType: "Matched rules, matched strings, severity", estimatedRuntime: "~20s", riskLevel: "Medium", isolationLevel: "None",
      fields: [
        { key: "ruleset", label: "Ruleset", type: "select", options: ["Malware", "Generic IOC", "Custom"], default: "Malware" },
        { key: "mode", label: "Scan Mode", type: "select", options: ["Quick", "Full"], default: "Full" },
        { key: "showMatchedStrings", label: "Show Matched Strings", type: "checkbox", default: true },
        { key: "extractIocs", label: "Extract IOCs", type: "checkbox", default: true },
      ] },
    { id: "recursive_artifact_extraction", name: "Recursive Artifact Extraction", category: "generic", tool: "binwalk / 7z / custom extractor",
      description: "Recursively unpacks embedded files and containers.",
      outputType: "Extracted embedded files", estimatedRuntime: "~30s", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [
        { key: "maxDepth", label: "Max Depth", type: "number", default: 3 },
        { key: "knownTypesOnly", label: "Known Types Only", type: "checkbox", default: true },
      ] },
  ];

  const BINARY_MODULES = [
    { id: "pe_header_analysis", name: "PE Header Analysis", category: "binary", tool: "pefile", supportedTypes: ["binary"],
      description: "Parses Windows PE headers, sections, and import/export tables.",
      outputType: "Sections, imports, exports, timestamps", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "Full headers + sections"], "Full headers + sections") },
    { id: "elf_header_analysis", name: "ELF Header Analysis", category: "binary", tool: "readelf / objdump", supportedTypes: ["binary"],
      description: "Parses ELF headers, sections, and symbol/library information.",
      outputType: "Sections, symbols, linked libraries", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "Full sections + symbols"], "Full sections + symbols") },
    { id: "import_export_analysis", name: "Import / Export Analysis", category: "binary", tool: "pefile / rabin2", supportedTypes: ["binary"],
      description: "Lists imported APIs and exported functions.",
      outputType: "Imported APIs, exported functions", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON") },
    { id: "packer_detection", name: "Packer Detection", category: "binary", tool: "Detect It Easy / custom entropy", supportedTypes: ["binary"],
      description: "Flags likely packers or compilers from signatures and entropy.",
      outputType: "Possible packer/compiler", estimatedRuntime: "~20s", riskLevel: "Medium", isolationLevel: "None",
      fields: sensitivityField() },
    { id: "capa_capability_detection", name: "Capa Capability Detection", category: "binary", tool: "capa", supportedTypes: ["binary"],
      description: "Maps binary behavior to recognizable malware capabilities.",
      outputType: "Malware capabilities", estimatedRuntime: "~1-2 minutes", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [{ key: "outputFormat", label: "Output Format", type: "select", options: ["Summary", "Full ATT&CK mapping"], default: "Full ATT&CK mapping" }] },
    { id: "floss_string_recovery", name: "FLOSS String Recovery", category: "binary", tool: "floss", supportedTypes: ["binary"],
      description: "Recovers obfuscated/decoded strings beyond a plain strings dump.",
      outputType: "Decoded strings", estimatedRuntime: "~1 minute", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "minLength", label: "Minimum Length", type: "number", default: 6 },
        { key: "decodeObfuscated", label: "Decode Obfuscated Strings", type: "checkbox", default: true },
      ] },
    { id: "disassembly_summary", name: "Disassembly Summary", category: "binary", tool: "objdump / radare2", supportedTypes: ["binary"],
      description: "Produces a function list and high-level assembly summary.",
      outputType: "Function list, assembly summary", estimatedRuntime: "~1-2 minutes", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "architecture", label: "Architecture", type: "select", options: ["Auto-detect", "x86", "x64", "ARM"], default: "Auto-detect" }] },
    { id: "ghidra_decompile", name: "Ghidra Decompile", category: "binary", tool: "ghidra headless", supportedTypes: ["binary"],
      description: "Decompiles functions and recovers symbol information.",
      outputType: "Decompiled functions, symbols", estimatedRuntime: "~5-10 minutes", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [
        { key: "architecture", label: "Architecture", type: "select", options: ["Auto-detect", "x86", "x64", "ARM"], default: "Auto-detect" },
        { key: "output", label: "Output", type: "select", options: ["Decompiled C", "Disassembly + C"], default: "Decompiled C" },
      ] },
    { id: "signature_certificate_check", name: "Signature / Certificate Check", category: "binary", tool: "osslsigncode / sigcheck equivalent", supportedTypes: ["binary"],
      description: "Verifies code-signing certificates and chain validity.",
      outputType: "Signing info, certificate status", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "verifyChain", label: "Verify Certificate Chain", type: "checkbox", default: true }] },
    { id: "suspicious_api_detection", name: "Suspicious API Detection", category: "binary", tool: "custom rules", supportedTypes: ["binary"],
      description: "Flags imported APIs associated with injection, networking, or persistence.",
      outputType: "Process injection, networking, persistence APIs", estimatedRuntime: "~20s", riskLevel: "Medium", isolationLevel: "None",
      fields: sensitivityField() },
  ];

  const PCAP_MODULES = [
    { id: "pcap_summary", name: "Pcap Summary", category: "pcap", tool: "capinfos / tshark", supportedTypes: ["pcap"],
      description: "Top-level capture stats: packet count, duration, protocols seen.",
      outputType: "Packet count, duration, protocols", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "timeRange", label: "Time Range", type: "select", options: ["Full capture", "First 10 minutes", "Custom range"], default: "Full capture" }] },
    { id: "protocol_statistics", name: "Protocol Statistics", category: "pcap", tool: "tshark", supportedTypes: ["pcap"],
      description: "Breaks down traffic by protocol.",
      outputType: "Protocol distribution", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "topN", label: "Top N Protocols", type: "number", default: 10 }] },
    { id: "dns_extraction", name: "DNS Extraction", category: "pcap", tool: "tshark / zeek", supportedTypes: ["pcap"],
      description: "Extracts queried domains and resolved IPs from DNS traffic.",
      outputType: "Queried domains, resolved IPs", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "timeRange", label: "Time Range", type: "select", options: ["Full capture", "Custom range"], default: "Full capture" },
        { key: "includeInternalDomains", label: "Include Internal Domains", type: "checkbox", default: false },
        { key: "extractSuspiciousDomains", label: "Extract Suspicious Domains", type: "checkbox", default: true },
        { key: "outputFormat", label: "Output Format", type: "select", options: ["Text", "JSON", "CSV"], default: "JSON" },
      ] },
    { id: "http_extraction", name: "HTTP Extraction", category: "pcap", tool: "tshark / zeek", supportedTypes: ["pcap"],
      description: "Extracts HTTP hosts, URLs, methods, and status codes.",
      outputType: "Hosts, URLs, methods, status codes", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "extract", label: "Extract", type: "select", options: ["Requests + responses", "Requests only"], default: "Requests + responses" },
        { key: "extractHeaders", label: "Extract Headers", type: "checkbox", default: true },
      ] },
    { id: "tls_ssl_analysis", name: "TLS / SSL Analysis", category: "pcap", tool: "tshark / ja3", supportedTypes: ["pcap"],
      description: "Extracts SNI, JA3/JA3S fingerprints, and certificate info.",
      outputType: "SNI, JA3/JA3S, certificates", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "extractCertificates", label: "Extract Certificates", type: "checkbox", default: true },
        { key: "computeJa3", label: "Compute JA3 / JA3S", type: "checkbox", default: true },
      ] },
    { id: "tcp_conversations", name: "TCP Conversations", category: "pcap", tool: "tshark", supportedTypes: ["pcap"],
      description: "Lists source/destination pairs with byte and packet counts.",
      outputType: "Source/destination pairs, bytes, packets", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "minBytes", label: "Minimum Bytes", type: "number", default: 0 }] },
    { id: "suspicious_connections", name: "Suspicious Connections", category: "pcap", tool: "custom rules", supportedTypes: ["pcap"],
      description: "Flags unusual ports, external IPs, and long-lived sessions.",
      outputType: "Unusual ports, external IPs, long sessions", estimatedRuntime: "~20s", riskLevel: "Medium", isolationLevel: "None",
      fields: [{ key: "flagExternalOnly", label: "Flag External IPs Only", type: "checkbox", default: true }] },
    { id: "pcap_file_extraction", name: "File Extraction", category: "pcap", tool: "zeek / tshark", supportedTypes: ["pcap"],
      description: "Carves out files transferred over the captured traffic.",
      outputType: "Extracted transferred files", estimatedRuntime: "~30s", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [{ key: "maxFileSize", label: "Max File Size", type: "select", options: ["No limit", "10 MB", "50 MB"], default: "No limit" }] },
    { id: "suricata_alert_scan", name: "Suricata Alert Scan", category: "pcap", tool: "suricata", supportedTypes: ["pcap"],
      description: "Replays the capture through Suricata IDS rules.",
      outputType: "IDS alerts", estimatedRuntime: "~1 minute", riskLevel: "Medium", isolationLevel: "None",
      fields: [{ key: "rulesetVersion", label: "Ruleset", type: "select", options: ["Emerging Threats", "Custom"], default: "Emerging Threats" }] },
    { id: "zeek_log_generation", name: "Zeek Log Generation", category: "pcap", tool: "zeek", supportedTypes: ["pcap"],
      description: "Generates Zeek's standard log set for the capture.",
      outputType: "conn.log, dns.log, http.log, ssl.log, files.log", estimatedRuntime: "~1 minute", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "logs", label: "Logs", type: "checklist", options: ["conn", "dns", "http", "ssl", "files"], default: ["conn", "dns", "http", "ssl", "files"] }] },
    { id: "network_ioc_extraction", name: "Network IOC Extraction", category: "pcap", tool: "custom parser", supportedTypes: ["pcap"],
      description: "Parses recognizable network indicators out of the capture.",
      outputType: "IPs, domains, URLs, hashes", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: iocFields() },
  ];

  const EMAIL_MODULES = [
    { id: "email_header_analysis", name: "Email Header Analysis", category: "email", tool: "mailparser", supportedTypes: ["email"],
      description: "Parses sender, receiver, subject, message-id, and routing headers.",
      outputType: "Sender, receiver, subject, message-id, routing", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "parseReceivedChain", label: "Parse Received Chain", type: "checkbox", default: true },
        { key: "extractSenderIps", label: "Extract Sender IPs", type: "checkbox", default: true },
        { key: "validateAuthResults", label: "Validate Authentication Results", type: "checkbox", default: true },
      ] },
    { id: "received_path_analysis", name: "Received Path Analysis", category: "email", tool: "custom parser", supportedTypes: ["email"],
      description: "Reconstructs the mail relay chain and per-hop timestamps.",
      outputType: "Mail relay chain and timestamps", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "parseReceivedChain", label: "Parse Received Chain", type: "checkbox", default: true },
        { key: "extractSenderIps", label: "Extract Sender IPs", type: "checkbox", default: true },
      ] },
    { id: "spf_dkim_dmarc_check", name: "SPF / DKIM / DMARC Check", category: "email", tool: "auth parser / DNS resolver if allowed", supportedTypes: ["email"],
      description: "Evaluates the message's sender-authentication results.",
      outputType: "Authentication result", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "Network-Restricted",
      fields: [{ key: "resolveDns", label: "Resolve DNS Live (if allowed)", type: "checkbox", default: false }] },
    { id: "email_url_extraction", name: "URL Extraction", category: "email", tool: "custom parser", supportedTypes: ["email"],
      description: "Extracts URLs and domains, optionally following redirect chains.",
      outputType: "URLs, domains, redirect chains if enabled", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "Network-Restricted",
      fields: [{ key: "followRedirects", label: "Follow Redirects (if allowed)", type: "checkbox", default: false }] },
    { id: "attachment_extraction", name: "Attachment Extraction", category: "email", tool: "ripmime / munpack", supportedTypes: ["email"],
      description: "Pulls attachments out of the message for separate analysis.",
      outputType: "Extracted attachments", estimatedRuntime: "~10s", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [{ key: "maxAttachments", label: "Max Attachments", type: "number", default: 10 }] },
    { id: "attachment_hashing", name: "Attachment Hashing", category: "email", tool: "hashdeep", supportedTypes: ["email"],
      description: "Hashes every extracted attachment for lookups.",
      outputType: "Hashes of attachments", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: hashFields() },
    { id: "phishing_indicator_scan", name: "Phishing Indicator Scan", category: "email", tool: "custom rules", supportedTypes: ["email"],
      description: "Flags suspicious senders, links, and domain mismatches.",
      outputType: "Suspicious sender, links, mismatched domains", estimatedRuntime: "~10s", riskLevel: "Medium", isolationLevel: "None",
      fields: sensitivityField() },
    { id: "email_ioc_extraction", name: "Email IOC Extraction", category: "email", tool: "custom parser", supportedTypes: ["email"],
      description: "Parses recognizable indicators out of the message and attachments.",
      outputType: "Sender IPs, domains, URLs, attachments", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: iocFields() },
  ];

  const IMAGE_MODULES = [
    { id: "image_metadata", name: "Image Metadata", category: "image", tool: "exiftool", supportedTypes: ["image"],
      description: "Reads camera, GPS, timestamp, and software metadata.",
      outputType: "Camera, GPS, timestamps, software", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "includeGps", label: "Include GPS", type: "checkbox", default: true },
        { key: "extractThumbnail", label: "Extract Thumbnail", type: "checkbox", default: true },
        { key: "outputFormat", label: "Output Format", type: "select", options: ["Summary", "JSON"], default: "JSON" },
      ] },
    { id: "image_integrity_check", name: "Image Integrity Check", category: "image", tool: "jpeginfo / pngcheck", supportedTypes: ["image"],
      description: "Checks for corrupted or modified file structure.",
      outputType: "Corrupted or modified structure", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "strictMode", label: "Strict Mode", type: "checkbox", default: true }] },
    { id: "thumbnail_extraction", name: "Thumbnail Extraction", category: "image", tool: "exiftool", supportedTypes: ["image"],
      description: "Pulls any embedded thumbnail image out of the file.",
      outputType: "Embedded thumbnails", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["JPEG", "PNG"], "JPEG") },
    { id: "hidden_data_check", name: "Hidden Data Check", category: "image", tool: "binwalk / zsteg / steghide check", supportedTypes: ["image"],
      description: "Looks for data appended or embedded beyond the visible image.",
      outputType: "Possible embedded data", estimatedRuntime: "~15s", riskLevel: "Medium", isolationLevel: "None",
      fields: sensitivityField() },
    { id: "image_hashing", name: "Image Hashing", category: "image", tool: "hashdeep", supportedTypes: ["image"],
      description: "Computes file hashes for integrity and lookups.",
      outputType: "File hashes", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: hashFields() },
    { id: "pixel_dimension_analysis", name: "Pixel / Dimension Analysis", category: "image", tool: "imagemagick identify", supportedTypes: ["image"],
      description: "Reads dimensions, color space, and compression details.",
      outputType: "Dimensions, color space, compression", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "Summary") },
    { id: "ocr_text_extraction", name: "OCR Text Extraction", category: "image", tool: "tesseract if available", supportedTypes: ["image"],
      description: "Runs OCR to recover any text rendered in the image.",
      outputType: "Detected text", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "language", label: "Language", type: "select", options: ["English", "Auto-detect"], default: "English" }] },
    { id: "steganography_triage", name: "Steganography Triage", category: "image", tool: "zsteg / stegdetect-style checks", supportedTypes: ["image"],
      description: "Runs quick checks for common steganographic channels.",
      outputType: "Possible hidden channels", estimatedRuntime: "~20s", riskLevel: "Medium", isolationLevel: "None",
      fields: sensitivityField() },
  ];

  const AUDIO_MODULES = [
    { id: "audio_metadata", name: "Audio Metadata", category: "audio", tool: "exiftool / mediainfo", supportedTypes: ["audio"],
      description: "Reads codec, bitrate, timestamp, and tag metadata.",
      outputType: "Codec, bitrate, timestamps, tags", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON") },
    { id: "waveform_summary", name: "Waveform Summary", category: "audio", tool: "ffmpeg / sox", supportedTypes: ["audio"],
      description: "Summarizes duration, channels, and sample rate.",
      outputType: "Duration, channels, sample rate", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "Summary") },
    { id: "spectrogram_generation", name: "Spectrogram Generation", category: "audio", tool: "sox / ffmpeg", supportedTypes: ["audio"],
      description: "Renders a spectrogram image artifact for visual review.",
      outputType: "Spectrogram image artifact", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "frequencyRange", label: "Frequency Range", type: "select", options: ["0-8 kHz", "0-16 kHz", "Full spectrum"], default: "Full spectrum" },
        { key: "generatePng", label: "Generate PNG Artifact", type: "checkbox", default: true },
        { key: "outputFormat", label: "Output Format", type: "select", options: ["PNG", "JSON"], default: "PNG" },
      ] },
    { id: "hidden_tone_dtmf_detection", name: "Hidden Tone / DTMF Detection", category: "audio", tool: "multimon-ng / custom analyzer", supportedTypes: ["audio"],
      description: "Detects DTMF tones or other encoded tone sequences.",
      outputType: "Detected tones or sequences", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: sensitivityField() },
    { id: "audio_hashing", name: "Audio Hashing", category: "audio", tool: "hashdeep", supportedTypes: ["audio"],
      description: "Computes file hashes for integrity and lookups.",
      outputType: "Hashes", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: hashFields() },
    { id: "silence_spike_detection", name: "Silence / Spike Detection", category: "audio", tool: "custom analyzer", supportedTypes: ["audio"],
      description: "Flags abnormal silence gaps or volume spikes.",
      outputType: "Suspicious silence, spikes, anomalies", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "thresholdDb", label: "Threshold (dB)", type: "number", default: -40 }] },
  ];

  const VIDEO_MODULES = [
    { id: "video_metadata", name: "Video Metadata", category: "video", tool: "mediainfo / exiftool", supportedTypes: ["video"],
      description: "Reads codec, duration, resolution, and timestamp metadata.",
      outputType: "Codec, duration, resolution, timestamps", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON") },
    { id: "frame_extraction", name: "Frame Extraction", category: "video", tool: "ffmpeg", supportedTypes: ["video"],
      description: "Extracts frames at a fixed interval for review.",
      outputType: "Selected frames", estimatedRuntime: "~30s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "interval", label: "Interval", type: "select", options: ["Every 1s", "Every 5s", "Every 10s"], default: "Every 5s" }] },
    { id: "keyframe_extraction", name: "Keyframe Extraction", category: "video", tool: "ffmpeg", supportedTypes: ["video"],
      description: "Extracts only the encoded keyframes.",
      outputType: "Keyframes", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "maxFrames", label: "Max Frames", type: "number", default: 20 }] },
    { id: "audio_track_extraction", name: "Audio Track Extraction", category: "video", tool: "ffmpeg", supportedTypes: ["video"],
      description: "Pulls the audio track out as a standalone artifact.",
      outputType: "Audio artifact", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["WAV", "MP3"], "WAV") },
    { id: "video_hashing", name: "Video Hashing", category: "video", tool: "hashdeep", supportedTypes: ["video"],
      description: "Computes file hashes for integrity and lookups.",
      outputType: "Hashes", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: hashFields() },
  ];

  const MEMORY_MODULES = [
    ["memory_image_info", "Memory Image Info", "volatility3", "OS info, symbols, architecture", "Low"],
    ["process_list", "Process List", "volatility3 pslist", "Process table", "Low"],
    ["process_tree", "Process Tree", "volatility3 pstree", "Parent-child process tree", "Low"],
    ["process_scan", "Process Scan", "volatility3 psscan", "Hidden/terminated process scan", "Medium"],
    ["network_connections", "Network Connections", "volatility3 netscan", "Sockets, connections, listening ports", "Medium"],
    ["command_line", "Command Line", "volatility3 cmdline", "Process command lines", "Low"],
    ["dll_list", "DLL List", "volatility3 dlllist", "Loaded DLLs/modules", "Low"],
    ["malfind", "Malfind", "volatility3 malfind", "Injected/suspicious memory regions", "High"],
    ["handles", "Handles", "volatility3 handles", "Process handles", "Low"],
    ["services", "Services", "volatility3 svcscan", "Windows services", "Low"],
    ["registry_hive_list", "Registry Hive List", "volatility3 hivelist", "Registry hives", "Low"],
    ["execution_artifacts", "UserAssist / Shimcache / Amcache", "volatility3 plugins", "Execution artifacts", "Medium"],
  ].map(([id, name, tool, output, risk]) => ({
    id, name, category: "memory", tool, supportedTypes: ["memory"],
    description: name + " via " + tool + ".",
    outputType: output, estimatedRuntime: "1-6 minutes", riskLevel: risk, isolationLevel: "None",
    fields: VOLATILITY_FIELDS,
  }));

  const DISK_MODULES = [
    { id: "partition_table", name: "Partition Table", category: "disk", tool: "mmls", supportedTypes: ["disk"],
      description: "Lists partitions and their offsets within the image.",
      outputType: "Partitions and offsets", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text") },
    { id: "filesystem_info", name: "File System Info", category: "disk", tool: "fsstat", supportedTypes: ["disk"],
      description: "Reads filesystem-level metadata for a partition.",
      outputType: "Filesystem metadata", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text") },
    { id: "file_listing", name: "File Listing", category: "disk", tool: "fls", supportedTypes: ["disk"],
      description: "Walks the filesystem tree and lists every file.",
      outputType: "File tree", estimatedRuntime: "~1-3 minutes", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "includeDeleted", label: "Include Deleted Entries", type: "checkbox", default: false }] },
    { id: "deleted_file_listing", name: "Deleted File Listing", category: "disk", tool: "fls with deleted entries", supportedTypes: ["disk"],
      description: "Lists filesystem entries marked deleted.",
      outputType: "Deleted files", estimatedRuntime: "~1-3 minutes", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "recoverableOnly", label: "Recoverable Only", type: "checkbox", default: true }] },
    { id: "disk_file_extraction", name: "File Extraction", category: "disk", tool: "icat / tsk_recover", supportedTypes: ["disk"],
      description: "Carves out specific files by inode/offset.",
      outputType: "Extracted selected files", estimatedRuntime: "~30s-2 minutes", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [{ key: "maxFileSize", label: "Max File Size", type: "select", options: ["No limit", "10 MB", "50 MB"], default: "No limit" }] },
    { id: "timeline_generation", name: "Timeline Generation", category: "disk", tool: "log2timeline / fls bodyfile", supportedTypes: ["disk"],
      description: "Builds a filesystem-wide MAC-time timeline.",
      outputType: "Filesystem timeline", estimatedRuntime: "3-10 minutes", riskLevel: "Low", isolationLevel: "None",
      fields: [
        { key: "timezone", label: "Timezone", type: "select", options: ["UTC", "System default", "Custom"], default: "UTC" },
        { key: "includeDeletedFiles", label: "Include Deleted Files", type: "checkbox", default: true },
        { key: "outputFormat", label: "Output Format", type: "select", options: ["CSV", "JSON"], default: "CSV" },
      ] },
    { id: "browser_artifact_scan", name: "Browser Artifact Scan", category: "disk", tool: "custom parser / sqlite parsers", supportedTypes: ["disk"],
      description: "Recovers browser history, downloads, and cookies if present.",
      outputType: "History, downloads, cookies if present", estimatedRuntime: "~1 minute", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "includeCookies", label: "Include Cookies", type: "checkbox", default: true }] },
    { id: "windows_registry_extraction", name: "Windows Registry Extraction", category: "disk", tool: "regripper / hivex", supportedTypes: ["disk"],
      description: "Extracts artifacts from the Windows registry hives.",
      outputType: "Registry artifacts", estimatedRuntime: "~1 minute", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "hives", label: "Hives", type: "checklist", options: ["SYSTEM", "SOFTWARE", "SAM", "NTUSER.DAT"], default: ["SYSTEM", "SOFTWARE"] }] },
    { id: "event_log_extraction", name: "Event Log Extraction", category: "disk", tool: "evtx_dump / chainsaw / hayabusa", supportedTypes: ["disk"],
      description: "Extracts and runs detections over Windows event logs.",
      outputType: "Windows event logs and detections", estimatedRuntime: "1-3 minutes", riskLevel: "Medium", isolationLevel: "None",
      fields: [{ key: "sigmaRules", label: "Run Sigma Rules", type: "checkbox", default: true }] },
    { id: "prefetch_analysis", name: "Prefetch Analysis", category: "disk", tool: "prefetch parser", supportedTypes: ["disk"],
      description: "Lists programs executed according to Prefetch records.",
      outputType: "Executed programs", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text") },
    { id: "lnk_jumplist_analysis", name: "LNK / JumpList Analysis", category: "disk", tool: "lnk parser", supportedTypes: ["disk"],
      description: "Parses shortcut and jump-list artifacts for accessed paths.",
      outputType: "Shortcut artifacts", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text") },
  ];

  const DOCUMENT_MODULES = [
    { id: "document_metadata", name: "Document Metadata", category: "document", tool: "exiftool", supportedTypes: ["document"],
      description: "Reads author, timestamp, and producer-software metadata.",
      outputType: "Author, timestamps, producer software", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON") },
    { id: "pdf_structure_analysis", name: "PDF Structure Analysis", category: "document", tool: "pdfid / pdf-parser", supportedTypes: ["document"],
      description: "Inspects PDF objects for embedded JavaScript and files.",
      outputType: "Objects, JavaScript, embedded files", estimatedRuntime: "~15s", riskLevel: "Medium", isolationLevel: "None",
      fields: [{ key: "extractJavascript", label: "Extract JavaScript", type: "checkbox", default: true }] },
    { id: "office_macro_analysis", name: "Office Macro Analysis", category: "document", tool: "olevba", supportedTypes: ["document"],
      description: "Extracts and flags suspicious VBA macro content.",
      outputType: "Macros, suspicious keywords", estimatedRuntime: "~15s", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [{ key: "deobfuscate", label: "Deobfuscate", type: "checkbox", default: true }] },
    { id: "embedded_object_extraction", name: "Embedded Object Extraction", category: "document", tool: "oletools / binwalk", supportedTypes: ["document"],
      description: "Pulls embedded OLE objects and files out of the document.",
      outputType: "Embedded files", estimatedRuntime: "~20s", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [{ key: "maxObjects", label: "Max Objects", type: "number", default: 50 }] },
    { id: "document_link_extraction", name: "Link Extraction", category: "document", tool: "custom parser", supportedTypes: ["document"],
      description: "Extracts URLs and domains referenced in the document.",
      outputType: "URLs/domains", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "Network-Restricted",
      fields: [{ key: "followRedirects", label: "Follow Redirects (if allowed)", type: "checkbox", default: false }] },
    { id: "suspicious_document_indicators", name: "Suspicious Document Indicators", category: "document", tool: "custom rules", supportedTypes: ["document"],
      description: "Flags auto-open macros, obfuscation, and external template injection.",
      outputType: "Auto-open macros, obfuscation, external templates", estimatedRuntime: "~15s", riskLevel: "Medium", isolationLevel: "None",
      fields: sensitivityField() },
  ];

  const ARCHIVE_MODULES = [
    { id: "archive_listing", name: "Archive Listing", category: "archive", tool: "7z / unzip / unrar", supportedTypes: ["archive"],
      description: "Lists the archive's contents without extracting.",
      outputType: "File list", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text") },
    { id: "archive_metadata", name: "Archive Metadata", category: "archive", tool: "7z / exiftool", supportedTypes: ["archive"],
      description: "Reads compression method and per-entry timestamps.",
      outputType: "Compression info, timestamps", estimatedRuntime: "~10s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "JSON") },
    { id: "archive_recursive_extraction", name: "Recursive Extraction", category: "archive", tool: "7z / custom extractor", supportedTypes: ["archive"],
      description: "Recursively extracts nested archives.",
      outputType: "Extracted files", estimatedRuntime: "~30s-2 minutes", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [{ key: "maxDepth", label: "Max Depth", type: "number", default: 5 }] },
    { id: "password_protection_check", name: "Password Protection Check", category: "archive", tool: "7z", supportedTypes: ["archive"],
      description: "Checks whether the archive is password-protected.",
      outputType: "Protected/not protected", estimatedRuntime: "~5s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "bruteForceCommon", label: "Try Common Passwords", type: "checkbox", default: false }] },
    { id: "nested_file_type_detection", name: "Nested File Type Detection", category: "archive", tool: "file / libmagic", supportedTypes: ["archive"],
      description: "Detects the real type of every extracted file.",
      outputType: "Detected types of extracted files", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "JSON") },
  ];

  const MOBILE_MODULES = [
    { id: "apk_manifest_analysis", name: "APK Manifest Analysis", category: "mobile", tool: "apktool / androguard", supportedTypes: ["mobile"],
      description: "Parses the manifest for package info, activities, and services.",
      outputType: "Package info, activities, services", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON") },
    { id: "apk_permission_analysis", name: "APK Permission Analysis", category: "mobile", tool: "androguard", supportedTypes: ["mobile"],
      description: "Lists requested permissions and flags dangerous ones.",
      outputType: "Requested permissions", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "flagDangerousOnly", label: "Flag Dangerous Permissions Only", type: "checkbox", default: true }] },
    { id: "jadx_decompile", name: "JADX Decompile", category: "mobile", tool: "jadx", supportedTypes: ["mobile"],
      description: "Decompiles the APK back to a Java source tree.",
      outputType: "Java source tree", estimatedRuntime: "1-3 minutes", riskLevel: "Medium", isolationLevel: "Sandboxed",
      fields: [{ key: "outputFormat", label: "Output Format", type: "select", options: ["Java source", "Smali"], default: "Java source" }] },
    { id: "mobile_resource_extraction", name: "Resource Extraction", category: "mobile", tool: "apktool", supportedTypes: ["mobile"],
      description: "Extracts resources and assets bundled in the package.",
      outputType: "Resources, assets", estimatedRuntime: "~30s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "maxFiles", label: "Max Files", type: "number", default: 200 }] },
    { id: "mobile_ioc_extraction", name: "Mobile IOC Extraction", category: "mobile", tool: "custom parser", supportedTypes: ["mobile"],
      description: "Parses recognizable indicators out of strings and resources.",
      outputType: "URLs, IPs, domains, keys", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: iocFields() },
    { id: "tracker_sdk_detection", name: "Tracker / SDK Detection", category: "mobile", tool: "custom signatures", supportedTypes: ["mobile"],
      description: "Flags known third-party tracker and ad-SDK libraries.",
      outputType: "Detected libraries/SDKs", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: sensitivityField() },
    { id: "ios_ipa_metadata", name: "iOS IPA Metadata", category: "mobile", tool: "unzip / plist parser", supportedTypes: ["mobile"],
      description: "Reads Info.plist and entitlements from an iOS package.",
      outputType: "Info.plist, entitlements", estimatedRuntime: "~15s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Summary", "JSON"], "JSON") },
  ];

  const LOGS_MODULES = [
    { id: "evtx_parse", name: "EVTX Parse", category: "logs", tool: "evtx_dump", supportedTypes: ["logs"],
      description: "Parses Windows EVTX records into a structured form.",
      outputType: "Parsed events", estimatedRuntime: "~30s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "eventIdFilter", label: "Event ID Filter", type: "select", options: ["All", "Security only", "System only"], default: "All" }] },
    { id: "sigma_rule_scan", name: "Sigma Rule Scan", category: "logs", tool: "chainsaw / hayabusa", supportedTypes: ["logs"],
      description: "Runs Sigma detection rules over the parsed log records.",
      outputType: "Detections", estimatedRuntime: "~1 minute", riskLevel: "Medium", isolationLevel: "None",
      fields: [{ key: "rulesetVersion", label: "Ruleset", type: "select", options: ["Default", "Custom"], default: "Default" }] },
    { id: "windows_logon_events", name: "Windows Logon Events", category: "logs", tool: "custom EVTX parser", supportedTypes: ["logs"],
      description: "Summarizes logon/logoff activity from Security events.",
      outputType: "Logon/logoff activity", estimatedRuntime: "~30s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "Text") },
    { id: "powershell_event_analysis", name: "PowerShell Event Analysis", category: "logs", tool: "chainsaw / custom rules", supportedTypes: ["logs"],
      description: "Flags script-block logging events and decodes obfuscation.",
      outputType: "Script block indicators", estimatedRuntime: "~30s", riskLevel: "Medium", isolationLevel: "None",
      fields: [{ key: "decodeBase64", label: "Decode Base64 Payloads", type: "checkbox", default: true }] },
    { id: "web_access_log_analysis", name: "Web Access Log Analysis", category: "logs", tool: "custom parser", supportedTypes: ["logs"],
      description: "Summarizes requests by IP, path, status code, and user agent.",
      outputType: "IPs, paths, status codes, user agents", estimatedRuntime: "~20s", riskLevel: "Low", isolationLevel: "None",
      fields: outputFormatField(["Text", "JSON"], "JSON") },
    { id: "auth_log_analysis", name: "Auth Log Analysis", category: "logs", tool: "custom parser", supportedTypes: ["logs"],
      description: "Flags failed logins, SSH activity, and sudo usage.",
      outputType: "Failed logins, SSH activity, sudo usage", estimatedRuntime: "~20s", riskLevel: "Medium", isolationLevel: "None",
      fields: [{ key: "flagFailedOnly", label: "Flag Failed Attempts Only", type: "checkbox", default: false }] },
    { id: "log_timeline_builder", name: "Timeline Builder", category: "logs", tool: "custom timeline normalizer", supportedTypes: ["logs"],
      description: "Normalizes parsed log events into a single timeline.",
      outputType: "Timeline events", estimatedRuntime: "~30s", riskLevel: "Low", isolationLevel: "None",
      fields: [{ key: "timezone", label: "Timezone", type: "select", options: ["UTC", "System default"], default: "UTC" }] },
  ];

  const MODULE_REGISTRY = [
    ...GENERIC_MODULES, ...BINARY_MODULES, ...PCAP_MODULES, ...EMAIL_MODULES,
    ...IMAGE_MODULES, ...AUDIO_MODULES, ...VIDEO_MODULES, ...MEMORY_MODULES,
    ...DISK_MODULES, ...DOCUMENT_MODULES, ...ARCHIVE_MODULES, ...MOBILE_MODULES,
    ...LOGS_MODULES,
  ];
  const MODULE_MAP = {};
  MODULE_REGISTRY.forEach((m) => {
    MODULE_MAP[m.id] = m;
  });

  function isModuleCompatible(module, evidenceType) {
    // "generic" category modules (hashing, strings, YARA, etc.) apply to
    // every evidence type, including files we couldn't classify at all.
    return module.category === "generic" || (module.supportedTypes || []).includes(evidenceType);
  }

  function mockOutputFor(module, evidenceName) {
    return "Mock " + module.outputType.toLowerCase() + " generated for " + evidenceName + " via " + module.tool + ".";
  }

  // Drives the Analyze tab's 3-column planner, the Review Analysis Plan and
  // Current Job Queue dialogs, and the Results tab (cases/detail.html) -
  // all one Alpine component instance shared across that markup (see the
  // single x-data on the page's outer wrapper). Pick evidence + a module +
  // that module's options, "Add to Plan" stages a job client-side; only
  // "Analyze N Jobs" "runs" anything, and since there's no real job runner
  // behind this, running a plan just mock-completes every staged job
  // instantly and drops its (fake) output into the Results tab.
  Alpine.data("analyzeWorkspace", (evidenceItems) => ({
    moduleMap: MODULE_MAP,
    evidenceTypeLabels: EVIDENCE_TYPE_LABELS,
    moduleCategoryLabels: MODULE_CATEGORY_LABELS,
    evidence: evidenceItems || [],
    evidenceFilter: "all",
    evidenceQuery: "",
    moduleFilter: "all",
    moduleQuery: "",
    selectedEvidence: [],
    selectedModule: null,
    targetEvidenceIds: [],
    moduleOptions: {},
    plan: [],
    queue: [],
    results: [],
    savedFindingIds: [],
    savedIocIds: [],
    viewingResult: null,

    evidenceTypeOf(item) {
      const ext = (item.filename || "").toLowerCase().split(".").pop();
      return EXT_TO_EVIDENCE_TYPE[ext] || "unknown";
    },

    evidenceTypeLabelOf(item) {
      return this.evidenceTypeLabels[this.evidenceTypeOf(item)];
    },

    filteredEvidence() {
      const q = this.evidenceQuery.trim().toLowerCase();
      return this.evidence.filter((item) => {
        if (q && !item.filename.toLowerCase().includes(q)) return false;
        if (this.evidenceFilter === "all" || this.evidenceFilter === "unanalyzed") return true;
        return this.evidenceTypeOf(item) === this.evidenceFilter;
      });
    },

    // Evidence filter pills are driven by whatever types are actually
    // present in this case's evidence, not a fixed guess at what a case
    // "usually" has.
    availableEvidenceTypes() {
      const types = new Set(this.evidence.map((item) => this.evidenceTypeOf(item)));
      return Array.from(types)
        .sort()
        .map((t) => [t, this.evidenceTypeLabels[t]]);
    },

    selectedFiles() {
      return this.selectedEvidence.map((id) => this.evidence.find((e) => e.id === id)).filter(Boolean);
    },

    // Groups a list of already-compatible modules by category, in a fixed
    // display order, applying the category pill + search box on top.
    groupModules(modules) {
      const q = this.moduleQuery.trim().toLowerCase();
      const filtered = modules.filter((m) => {
        if (this.moduleFilter !== "all" && m.category !== this.moduleFilter) return false;
        if (q && !m.name.toLowerCase().includes(q)) return false;
        return true;
      });
      const groups = [];
      MODULE_CATEGORY_ORDER.forEach((cat) => {
        const mods = filtered.filter((m) => m.category === cat);
        if (mods.length) groups.push({ category: cat, label: MODULE_CATEGORY_LABELS[cat], modules: mods });
      });
      return groups;
    },

    modulesForType(evidenceType) {
      return MODULE_REGISTRY.filter((m) => isModuleCompatible(m, evidenceType));
    },

    // Union of every compatible module across the current selection - used
    // only to compute which category pills are worth showing.
    allCompatibleModules() {
      const seen = new Set();
      const result = [];
      this.selectedFiles().forEach((f) => {
        this.modulesForType(this.evidenceTypeOf(f)).forEach((m) => {
          if (!seen.has(m.id)) {
            seen.add(m.id);
            result.push(m);
          }
        });
      });
      return result;
    },

    availableCategories() {
      const cats = new Set(this.allCompatibleModules().map((m) => m.category));
      return MODULE_CATEGORY_ORDER.filter((c) => cats.has(c));
    },

    // Drives requirements 2-4: one file -> one module list; several files of
    // the same type -> the same module list, applied to all of them; several
    // files of different types -> one module list per file.
    compatibleView() {
      const files = this.selectedFiles();
      if (!files.length) return { mode: "empty" };
      const types = new Set(files.map((f) => this.evidenceTypeOf(f)));
      if (types.size <= 1) {
        const evidenceType = this.evidenceTypeOf(files[0]);
        return {
          mode: "shared",
          evidenceType,
          evidenceLabel: this.evidenceTypeLabels[evidenceType],
          fileCount: files.length,
          groups: this.groupModules(this.modulesForType(evidenceType)),
        };
      }
      return {
        mode: "byFile",
        files: files.map((f) => {
          const evidenceType = this.evidenceTypeOf(f);
          return {
            evidenceId: f.id,
            evidenceName: f.filename,
            evidenceType,
            evidenceLabel: this.evidenceTypeLabels[evidenceType],
            groups: this.groupModules(this.modulesForType(evidenceType)),
          };
        }),
      };
    },

    toggleEvidence(id) {
      const idx = this.selectedEvidence.indexOf(id);
      if (idx === -1) this.selectedEvidence.push(id);
      else this.selectedEvidence.splice(idx, 1);
    },

    isEvidenceSelected(id) {
      return this.selectedEvidence.includes(id);
    },

    selectAllEvidence() {
      this.selectedEvidence = this.filteredEvidence().map((item) => item.id);
    },

    // evidenceIds is omitted when clicking a module from the "shared" view
    // (every selected file shares one type) and set to a single file's id
    // when clicking from the "byFile" view, so "Add to Plan" only targets
    // the file(s) that module is actually compatible with.
    selectModule(moduleId, evidenceIds) {
      this.selectedModule = moduleId;
      this.targetEvidenceIds = evidenceIds && evidenceIds.length ? evidenceIds.slice() : this.selectedEvidence.slice();
      this.resetOptions();
    },

    targetFiles() {
      return this.targetEvidenceIds.map((id) => this.evidence.find((e) => e.id === id)).filter(Boolean);
    },

    resetOptions() {
      if (!this.selectedModule) return;
      const mod = this.moduleMap[this.selectedModule];
      const opts = {};
      mod.fields.forEach((f) => {
        opts[f.key] = Array.isArray(f.default) ? [...f.default] : f.default;
      });
      this.moduleOptions = opts;
    },

    toggleChecklistValue(fieldKey, value) {
      const list = this.moduleOptions[fieldKey] || [];
      const idx = list.indexOf(value);
      if (idx === -1) list.push(value);
      else list.splice(idx, 1);
      this.moduleOptions[fieldKey] = list;
    },

    optionsSummary() {
      const mod = this.moduleMap[this.selectedModule];
      return mod.fields
        .map((f) => {
          const v = this.moduleOptions[f.key];
          const val = Array.isArray(v) ? v.join("/") : typeof v === "boolean" ? (v ? "Yes" : "No") : v;
          return f.label + ": " + val;
        })
        .join(", ");
    },

    addToPlan() {
      const ids = this.targetEvidenceIds.length ? this.targetEvidenceIds : this.selectedEvidence;
      if (!ids.length || !this.selectedModule) return;
      const mod = this.moduleMap[this.selectedModule];
      const summary = this.optionsSummary();
      const optionsSnapshot = JSON.parse(JSON.stringify(this.moduleOptions));
      ids.forEach((id) => {
        const item = this.evidence.find((e) => e.id === id);
        if (!item) return;
        // Re-staging the same file+module replaces the earlier entry rather
        // than stacking a duplicate job.
        this.plan = this.plan.filter((j) => !(j.evidenceId === id && j.moduleId === mod.id));
        this.plan.push({
          id: id + ":" + mod.id + ":" + Date.now(),
          evidenceId: id,
          evidenceName: item.filename,
          evidenceType: this.evidenceTypeOf(item),
          moduleId: mod.id,
          moduleName: mod.name,
          tool: mod.tool,
          selectedOptions: optionsSnapshot,
          summary,
          outputType: mod.outputType,
          risk: mod.riskLevel,
          isolation: mod.isolationLevel,
        });
      });
    },

    removeFromPlan(jobId) {
      this.plan = this.plan.filter((j) => j.id !== jobId);
    },

    clearPlan() {
      this.plan = [];
    },

    groupedPlan() {
      const groups = [];
      this.plan.forEach((job) => {
        let group = groups.find((g) => g.evidenceName === job.evidenceName);
        if (!group) {
          group = { evidenceName: job.evidenceName, jobs: [] };
          groups.push(group);
        }
        group.jobs.push(job);
      });
      return groups;
    },

    get estimatedMinutes() {
      return this.plan.length === 0 ? 0 : Math.max(2, this.plan.length * 3);
    },

    get riskLabel() {
      if (!this.plan.length) return "—";
      if (this.plan.some((j) => j.risk === "High")) return "High";
      if (this.plan.some((j) => j.risk === "Medium")) return "Medium";
      return "Low";
    },

    // Mock "execution": every staged job instantly completes and gets a
    // fabricated output dropped into Results - there's no real runner.
    startAnalysis() {
      if (!this.plan.length) return;
      const startedAt = Date.now();
      this.plan.forEach((job) => {
        this.queue = this.queue.filter((q) => q.id !== job.id);
        this.queue.push({ ...job, status: "Completed", progress: 100 });
        this.results = this.results.filter((r) => r.id !== job.id);
        this.results.push({
          ...job,
          completedAt: startedAt,
          output: mockOutputFor(this.moduleMap[job.moduleId], job.evidenceName),
        });
      });

      const reviewDialog = document.getElementById("review-analysis-plan");
      const queueDialog = document.getElementById("current-job-queue");
      if (reviewDialog) {
        reviewDialog.dataset.state = "closed";
        if (reviewDialog.open) reviewDialog.close();
      }
      if (queueDialog) {
        queueDialog.dataset.state = "open";
        if (!queueDialog.open) queueDialog.showModal();
      }
    },

    groupedResults() {
      const groups = [];
      this.results.forEach((r) => {
        let group = groups.find((g) => g.evidenceName === r.evidenceName);
        if (!group) {
          group = { evidenceName: r.evidenceName, results: [] };
          groups.push(group);
        }
        group.results.push(r);
      });
      return groups;
    },

    isFindingSaved(resultId) {
      return this.savedFindingIds.includes(resultId);
    },

    saveToReport(resultId) {
      if (!this.savedFindingIds.includes(resultId)) this.savedFindingIds.push(resultId);
    },

    removeFromReport(resultId) {
      this.savedFindingIds = this.savedFindingIds.filter((id) => id !== resultId);
    },

    savedFindings() {
      return this.results.filter((r) => this.savedFindingIds.includes(r.id));
    },

    isSavedAsIoc(resultId) {
      return this.savedIocIds.includes(resultId);
    },

    saveAsIoc(resultId) {
      if (!this.savedIocIds.includes(resultId)) this.savedIocIds.push(resultId);
    },

    viewResult(result) {
      this.viewingResult = result;
    },

    exportResult(result) {
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.evidenceName + "-" + result.moduleId + ".json";
      a.click();
      URL.revokeObjectURL(url);
    },
  }));

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
        .filter((m) => !q || m.name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q))
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
});
