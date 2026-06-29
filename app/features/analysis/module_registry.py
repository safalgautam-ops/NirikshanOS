"""Analysis module registry: the backend's authoritative catalog of every
analysis module Nirikshan OS can run against evidence.

This answers, for any module:
  - What does it do, and which tool implements it?
  - Which evidence type(s) is it compatible with?
  - Which plan does an analyst need to run it?
  - Which queue should run it later, and in which container image?
  - Can it be batched together with other modules in one container?
  - Which parser will read its output later?

The frontend (app/static/js/components.js) used to keep its own copy of
this catalog as the *source of truth* for the Analyze dialog. That has
been flipped: the frontend's copy is now a clearly-labelled dev-only
fallback (DEV_MOCK_MODULE_REGISTRY), and this file is the real one. The
Analyze UI should eventually fetch modules from
GET /cases/<case_id>/evidence/<evidence_id>/modules instead.

Important: this module only *describes* modules. It never runs anything.
Actual execution (Docker runner, Redis queue, worker, result parser) is a
later phase - see service.py's module docstring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Plan = Literal["free", "analyst", "advanced"]
QueueName = Literal["fast_queue", "standard_queue", "heavy_queue", "sandbox_queue"]
RiskLevel = Literal["low", "medium", "high"]
IsolationLevel = Literal["none", "sandboxed", "network_restricted", "vm"]
ModuleTier = Literal[
    "basic_triage",
    "standard",
    "advanced",
    "network",
    "email",
    "memory",
]

# Evidence type buckets a module can declare compatibility with.
# "unknown" is its own bucket (file couldn't be classified at all) and "*"
# is the wildcard used by generic modules that run against anything.
EVIDENCE_TYPES: dict[str, str] = {
    "generic": "Generic / Any File",
    "binary": "Binary / Executable",
    "pcap": "PCAP / Network Capture",
    "email": "EML / Email File",
    "image": "Image Forensics",
    "audio": "Audio Forensics",
    "video": "Video Forensics",
    "memory": "Memory Dump",
    "disk": "Disk Image",
    "document": "Document / PDF / Office",
    "archive": "Archive File",
    "mobile": "Mobile / APK",
    "logs": "Logs / EVTX / System Logs",
    "unknown": "Unknown File",
}

# Extension -> evidence type, used as a fallback when an evidence row has
# no detected type yet (see service.detect_evidence_type). Mirrors the
# mapping the frontend fallback catalog used before this registry existed.
EVIDENCE_TYPE_EXTENSIONS: dict[str, list[str]] = {
    "binary": ["exe", "dll", "elf", "bin", "so", "sys", "macho", "o"],
    "pcap": ["pcap", "pcapng", "cap"],
    "email": ["eml", "msg", "mbox"],
    "image": ["jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"],
    "audio": ["wav", "mp3", "flac", "m4a", "ogg", "aac"],
    "video": ["mp4", "mov", "avi", "mkv", "webm"],
    "memory": ["mem", "vmem", "dmp", "lime", "raw"],
    "disk": ["img", "dd", "e01", "aff", "vmdk", "qcow2", "iso"],
    "document": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "rtf", "odt"],
    "archive": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"],
    "mobile": ["apk", "aab", "dex", "jar", "ipa"],
    "logs": ["evtx", "log", "jsonl", "syslog"],
    "generic": ["txt", "csv", "json", "xml", "ini", "cfg", "dat", "plist", "db", "sqlite", "html", "htm", "md", "yaml", "yml"],
}

_EXTENSION_TO_EVIDENCE_TYPE: dict[str, str] = {
    ext: evidence_type
    for evidence_type, extensions in EVIDENCE_TYPE_EXTENSIONS.items()
    for ext in extensions
}


def detect_evidence_type_from_filename(filename: str) -> str:
    """Best-effort evidence type guess from the file extension alone - the
    fallback used when an evidence row has no real detected type yet."""
    if "." not in filename:
        return "unknown"
    extension = filename.rsplit(".", 1)[-1].lower()
    return _EXTENSION_TO_EVIDENCE_TYPE.get(extension, "unknown")


@dataclass(frozen=True)
class ModuleOption:
    """One configurable field a module exposes in the Analyze dialog (e.g.
    "Output Format" as a select, "Extract URLs" as a checkbox)."""

    key: str
    label: str
    type: str
    default: Any = None
    options: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisModule:
    id: str
    name: str
    category: str
    tool: str
    description: str
    output_type: str
    supported_types: list[str]
    required_plan: Plan
    queue_name: QueueName
    runtime_image: str
    batchable: bool
    batch_group: str | None
    timeout_seconds: int
    parser_name: str
    estimated_runtime: str
    risk_level: RiskLevel
    isolation_level: IsolationLevel
    tier: ModuleTier
    fields: list[ModuleOption] = field(default_factory=list)
    enabled: bool = True


# --------------------------------------------------------------------------
# Small helpers that derive a few fields instead of hand-typing them on
# every one of the ~90 modules below. Each one mirrors logic the frontend
# fallback catalog already used (moduleTierOf/requiredPlanOf in
# components.js) - the registry is the new authority, but the *reasoning*
# carries over. Every helper's result can still be overridden per-module
# by passing the field explicitly to _module().
# --------------------------------------------------------------------------

# Modules in these categories are never batched: memory/disk modules run
# multi-minute heavy_queue jobs against multi-GB images, which is the
# opposite of "lightweight enough to share a container".
_NEVER_BATCH_CATEGORIES = {"memory", "disk"}

# A handful of specific modules are explicitly called out as not batchable
# even though their risk/isolation would otherwise qualify them (they are
# slow, sandboxed-in-spirit, or simply too heavy to share a container).
_EXPLICITLY_NOT_BATCHABLE = {
    "generic.yara_scan",
    "generic.recursive_artifact_extraction",
    "binary.ghidra_decompile",
    "binary.capa_capability_detection",
    "binary.floss_string_recovery",
    "pcap.zeek_log_generation",
    "pcap.suricata_alert_scan",
    "document.office_macro_analysis",
    "archive.archive_recursive_extraction",
    "mobile.jadx_decompile",
}

_BATCH_GROUP_BY_CATEGORY = {
    "generic": "basic_triage",
    "binary": "binary_static_quick",
    "pcap": "pcap_quick",
    "email": "email_quick",
    "image": "image_quick",
    "audio": "audio_quick",
    "video": "video_quick",
    "logs": "logs_quick",
}

_RUNTIME_IMAGE_BY_CATEGORY = {
    "generic": "dfir/basic-tools:1.0",
    "binary": "dfir/binary-tools:1.0",
    "pcap": "dfir/network-tools:1.0",
    "email": "dfir/mail-tools:1.0",
    "image": "dfir/media-tools:1.0",
    "audio": "dfir/media-tools:1.0",
    "video": "dfir/media-tools:1.0",
    "memory": "dfir/volatility-tools:1.0",
    "disk": "dfir/disk-tools:1.0",
    "document": "dfir/document-tools:1.0",
    "archive": "dfir/archive-tools:1.0",
    "mobile": "dfir/mobile-tools:1.0",
    "logs": "dfir/log-tools:1.0",
}


def _derive_tier(category: str, risk_level: RiskLevel, isolation_level: IsolationLevel) -> ModuleTier:
    if category == "pcap":
        return "network"
    if category == "email":
        return "email"
    if category == "memory":
        return "memory"
    if category == "generic":
        return "basic_triage"
    if risk_level == "high" or isolation_level != "none":
        return "advanced"
    return "standard"


def _derive_required_plan(tier: ModuleTier, risk_level: RiskLevel) -> Plan:
    if tier == "advanced":
        return "advanced"
    if tier == "basic_triage":
        return "free"
    return "free" if risk_level == "low" else "analyst"


def _derive_batchable(module_id: str, category: str, risk_level: RiskLevel, isolation_level: IsolationLevel) -> bool:
    if module_id in _EXPLICITLY_NOT_BATCHABLE:
        return False
    if category in _NEVER_BATCH_CATEGORIES:
        return False
    return risk_level == "low" and isolation_level == "none"


def _module(
    id: str,
    name: str,
    category: str,
    tool: str,
    description: str,
    output_type: str,
    supported_types: list[str],
    *,
    risk_level: RiskLevel = "low",
    isolation_level: IsolationLevel = "none",
    required_plan: Plan | None = None,
    queue_name: QueueName = "fast_queue",
    runtime_image: str | None = None,
    batchable: bool | None = None,
    batch_group: str | None = None,
    timeout_seconds: int = 60,
    estimated_runtime: str = "~10s",
    tier: ModuleTier | None = None,
    fields: list[ModuleOption] | None = None,
    enabled: bool = True,
) -> AnalysisModule:
    """Builds one AnalysisModule. Every field can be overridden explicitly;
    anything left out is derived from category/risk/isolation the same way
    the old frontend mock derived tier/plan instead of hand-tagging every
    module - see the _derive_* helpers above."""
    resolved_tier = tier or _derive_tier(category, risk_level, isolation_level)
    resolved_plan = required_plan or _derive_required_plan(resolved_tier, risk_level)
    resolved_batchable = (
        batchable if batchable is not None else _derive_batchable(id, category, risk_level, isolation_level)
    )
    resolved_batch_group = batch_group
    if resolved_batch_group is None and resolved_batchable:
        resolved_batch_group = _BATCH_GROUP_BY_CATEGORY.get(category)
    return AnalysisModule(
        id=id,
        name=name,
        category=category,
        tool=tool,
        description=description,
        output_type=output_type,
        supported_types=supported_types,
        required_plan=resolved_plan,
        queue_name=queue_name,
        runtime_image=runtime_image or _RUNTIME_IMAGE_BY_CATEGORY.get(category, "dfir/basic-tools:1.0"),
        batchable=resolved_batchable,
        batch_group=resolved_batch_group,
        timeout_seconds=timeout_seconds,
        parser_name=f"{id.split('.')[-1]}_parser",
        estimated_runtime=estimated_runtime,
        risk_level=risk_level,
        isolation_level=isolation_level,
        tier=resolved_tier,
        fields=fields or [],
        enabled=enabled,
    )


def _select(key: str, label: str, options: list[str], default: str) -> ModuleOption:
    return ModuleOption(key=key, label=label, type="select", options=options, default=default)


def _checkbox(key: str, label: str, default: bool = True) -> ModuleOption:
    return ModuleOption(key=key, label=label, type="checkbox", default=default)


def _number(key: str, label: str, default: int) -> ModuleOption:
    return ModuleOption(key=key, label=label, type="number", default=default)


def _output_format_field(options: list[str] | None = None, default: str | None = None) -> list[ModuleOption]:
    opts = options or ["Text", "JSON"]
    return [_select("output_format", "Output Format", opts, default or opts[0])]


def _hash_fields() -> list[ModuleOption]:
    return [
        ModuleOption(
            key="hash_types",
            label="Hash Types",
            type="checklist",
            options=["MD5", "SHA1", "SHA256", "SHA512"],
            default=["MD5", "SHA1", "SHA256"],
        ),
        _select("output", "Output", ["Summary", "JSON", "Summary + JSON"], "Summary + JSON"),
    ]


def _ioc_fields() -> list[ModuleOption]:
    return [
        _checkbox("extract_ips", "Extract IPs"),
        _checkbox("extract_domains", "Extract Domains"),
        _checkbox("extract_urls", "Extract URLs"),
        _checkbox("extract_emails", "Extract Emails"),
        _checkbox("extract_hashes", "Extract Hashes"),
    ]


def _sensitivity_field() -> list[ModuleOption]:
    return [_select("sensitivity", "Sensitivity", ["Low", "Medium", "High"], "Medium")]


# --------------------------------------------------------------------------
# Generic modules - compatible with every evidence type ("*"), including
# files that couldn't be classified at all.
# --------------------------------------------------------------------------

GENERIC_MODULES: list[AnalysisModule] = [
    _module(
        "generic.file_identification", "File Identification", "generic", "file / libmagic",
        "Detects the real file type from magic bytes, independent of the extension.",
        "Detected type, MIME, magic bytes", ["*"],
        estimated_runtime="~5s", fields=_output_format_field(["Text", "JSON"], "JSON"),
    ),
    _module(
        "generic.hash_calculation", "Hash Calculation", "generic", "hashdeep / sha256sum",
        "Computes cryptographic hashes for integrity verification and hash-set lookups.",
        "MD5, SHA1, SHA256, SHA512", ["*"],
        estimated_runtime="~10s", fields=_hash_fields(),
    ),
    _module(
        "generic.metadata_extraction", "Metadata Extraction", "generic", "exiftool",
        "Extracts whatever embedded metadata the file carries.",
        "Metadata table + JSON", ["*"],
        estimated_runtime="~10s", fields=_output_format_field(["Table", "JSON"], "JSON"),
    ),
    _module(
        "generic.entropy_analysis", "Entropy Analysis", "generic", "binwalk / custom entropy analyzer",
        "Scores byte-level randomness across the file to flag packed or encrypted regions.",
        "Entropy score, suspicious packed regions", ["*"],
        estimated_runtime="~20s",
        fields=[
            _select("chunk_size", "Chunk Size", ["Auto", "4 KB", "64 KB"], "Auto"),
            _number("highlight_threshold", "Highlight Threshold", 7),
        ],
    ),
    _module(
        "generic.strings_extraction", "Strings Extraction", "generic", "strings / FLOSS",
        "Pulls printable strings and flags embedded indicators among them.",
        "Strings table, URLs, IPs, emails", ["*"],
        estimated_runtime="~15s",
        fields=[
            _number("min_length", "Minimum Length", 6),
            _select("encoding", "Encoding", ["ASCII", "Unicode", "Both"], "Both"),
            _checkbox("extract_urls", "Extract URLs"),
            _checkbox("extract_ips", "Extract IPs"),
            _checkbox("extract_emails", "Extract Emails"),
        ],
    ),
    _module(
        "generic.ioc_extraction", "IOC Extraction", "generic", "custom parser",
        "Parses recognizable indicators of compromise out of the file.",
        "IPs, domains, URLs, emails, hashes", ["*"],
        estimated_runtime="~15s", fields=_ioc_fields(),
    ),
    _module(
        "generic.yara_scan", "YARA Scan", "generic", "yara",
        "Matches the file against curated and custom YARA rulesets.",
        "Matched rules, matched strings, severity", ["*"],
        risk_level="medium", required_plan="analyst", queue_name="standard_queue",
        estimated_runtime="~20s",
        fields=[
            _select("ruleset", "Ruleset", ["Malware", "Generic IOC", "Custom"], "Malware"),
            _select("mode", "Scan Mode", ["Quick", "Full"], "Full"),
            _checkbox("show_matched_strings", "Show Matched Strings"),
            _checkbox("extract_iocs", "Extract IOCs"),
        ],
    ),
    _module(
        "generic.recursive_artifact_extraction", "Recursive Artifact Extraction", "generic",
        "binwalk / 7z / custom extractor",
        "Recursively unpacks embedded files and containers.",
        "Extracted embedded files", ["*"],
        risk_level="medium", isolation_level="sandboxed", required_plan="advanced",
        queue_name="sandbox_queue", estimated_runtime="~30s",
        fields=[_number("max_depth", "Max Depth", 3), _checkbox("known_types_only", "Known Types Only")],
    ),
]

# --------------------------------------------------------------------------
# Binary / executable modules.
# --------------------------------------------------------------------------

BINARY_MODULES: list[AnalysisModule] = [
    _module(
        "binary.pe_header_analysis", "PE Header Analysis", "binary", "pefile",
        "Parses Windows PE headers, sections, and import/export tables.",
        "Sections, imports, exports, timestamps", ["binary"],
        estimated_runtime="~15s",
        fields=_output_format_field(["Summary", "Full headers + sections"], "Full headers + sections"),
    ),
    _module(
        "binary.elf_header_analysis", "ELF Header Analysis", "binary", "readelf / objdump",
        "Parses ELF headers, sections, and symbol/library information.",
        "Sections, symbols, linked libraries", ["binary"],
        estimated_runtime="~15s",
        fields=_output_format_field(["Summary", "Full sections + symbols"], "Full sections + symbols"),
    ),
    _module(
        "binary.import_export_analysis", "Import / Export Analysis", "binary", "pefile / rabin2",
        "Lists imported APIs and exported functions.",
        "Imported APIs, exported functions", ["binary"],
        estimated_runtime="~15s", fields=_output_format_field(["Summary", "JSON"], "JSON"),
    ),
    _module(
        "binary.packer_detection", "Packer Detection", "binary", "Detect It Easy / custom entropy",
        "Flags likely packers or compilers from signatures and entropy.",
        "Possible packer/compiler", ["binary"],
        risk_level="medium", estimated_runtime="~20s", fields=_sensitivity_field(),
    ),
    _module(
        "binary.capa_capability_detection", "Capa Capability Detection", "binary", "capa",
        "Maps binary behavior to recognizable malware capabilities.",
        "Malware capabilities", ["binary"],
        risk_level="medium", isolation_level="sandboxed", required_plan="analyst",
        queue_name="standard_queue", estimated_runtime="~1-2 minutes",
        fields=[_select("output_format", "Output Format", ["Summary", "Full ATT&CK mapping"], "Full ATT&CK mapping")],
    ),
    _module(
        "binary.floss_string_recovery", "FLOSS String Recovery", "binary", "floss",
        "Recovers obfuscated/decoded strings beyond a plain strings dump.",
        "Decoded strings", ["binary"],
        required_plan="advanced", queue_name="standard_queue", estimated_runtime="~1 minute",
        fields=[_number("min_length", "Minimum Length", 6), _checkbox("decode_obfuscated", "Decode Obfuscated Strings")],
    ),
    _module(
        "binary.disassembly_summary", "Disassembly Summary", "binary", "objdump / radare2",
        "Produces a function list and high-level assembly summary.",
        "Function list, assembly summary", ["binary"],
        estimated_runtime="~1-2 minutes",
        fields=[_select("architecture", "Architecture", ["Auto-detect", "x86", "x64", "ARM"], "Auto-detect")],
    ),
    _module(
        "binary.ghidra_decompile", "Ghidra Decompile", "binary", "ghidra headless",
        "Decompiles functions and recovers symbol information.",
        "Decompiled functions, symbols", ["binary"],
        risk_level="medium", isolation_level="sandboxed", required_plan="advanced",
        queue_name="heavy_queue", timeout_seconds=900, estimated_runtime="~5-10 minutes",
        fields=[
            _select("architecture", "Architecture", ["Auto-detect", "x86", "x64", "ARM"], "Auto-detect"),
            _select("output", "Output", ["Decompiled C", "Disassembly + C"], "Decompiled C"),
        ],
    ),
    _module(
        "binary.signature_certificate_check", "Signature / Certificate Check", "binary",
        "osslsigncode / sigcheck equivalent",
        "Verifies code-signing certificates and chain validity.",
        "Signing info, certificate status", ["binary"],
        estimated_runtime="~10s", fields=[_checkbox("verify_chain", "Verify Certificate Chain")],
    ),
    _module(
        "binary.suspicious_api_detection", "Suspicious API Detection", "binary", "custom rules",
        "Flags imported APIs associated with injection, networking, or persistence.",
        "Process injection, networking, persistence APIs", ["binary"],
        risk_level="medium", estimated_runtime="~20s", fields=_sensitivity_field(),
    ),
]

# --------------------------------------------------------------------------
# PCAP / network modules.
# --------------------------------------------------------------------------

PCAP_MODULES: list[AnalysisModule] = [
    _module(
        "pcap.pcap_summary", "Pcap Summary", "pcap", "capinfos / tshark",
        "Top-level capture stats: packet count, duration, protocols seen.",
        "Packet count, duration, protocols", ["pcap"],
        estimated_runtime="~10s",
        fields=[_select("time_range", "Time Range", ["Full capture", "First 10 minutes", "Custom range"], "Full capture")],
    ),
    _module(
        "pcap.protocol_statistics", "Protocol Statistics", "pcap", "tshark",
        "Breaks down traffic by protocol.",
        "Protocol distribution", ["pcap"],
        estimated_runtime="~15s", fields=[_number("top_n", "Top N Protocols", 10)],
    ),
    _module(
        "pcap.dns_extraction", "DNS Extraction", "pcap", "tshark / zeek",
        "Extracts queried domains and resolved IPs from DNS traffic.",
        "Queried domains, resolved IPs", ["pcap"],
        estimated_runtime="~20s",
        fields=[
            _select("time_range", "Time Range", ["Full capture", "Custom range"], "Full capture"),
            _checkbox("include_internal_domains", "Include Internal Domains", False),
            _checkbox("extract_suspicious_domains", "Extract Suspicious Domains"),
            _select("output_format", "Output Format", ["Text", "JSON", "CSV"], "JSON"),
        ],
    ),
    _module(
        "pcap.http_extraction", "HTTP Extraction", "pcap", "tshark / zeek",
        "Extracts HTTP hosts, URLs, methods, and status codes.",
        "Hosts, URLs, methods, status codes", ["pcap"],
        estimated_runtime="~20s",
        fields=[
            _select("extract", "Extract", ["Requests + responses", "Requests only"], "Requests + responses"),
            _checkbox("extract_headers", "Extract Headers"),
        ],
    ),
    _module(
        "pcap.tls_ssl_analysis", "TLS / SSL Analysis", "pcap", "tshark / ja3",
        "Extracts SNI, JA3/JA3S fingerprints, and certificate info.",
        "SNI, JA3/JA3S, certificates", ["pcap"],
        estimated_runtime="~20s",
        fields=[_checkbox("extract_certificates", "Extract Certificates"), _checkbox("compute_ja3", "Compute JA3 / JA3S")],
    ),
    _module(
        "pcap.tcp_conversations", "TCP Conversations", "pcap", "tshark",
        "Lists source/destination pairs with byte and packet counts.",
        "Source/destination pairs, bytes, packets", ["pcap"],
        estimated_runtime="~15s", fields=[_number("min_bytes", "Minimum Bytes", 0)],
    ),
    _module(
        "pcap.suspicious_connections", "Suspicious Connections", "pcap", "custom rules",
        "Flags unusual ports, external IPs, and long-lived sessions.",
        "Unusual ports, external IPs, long sessions", ["pcap"],
        risk_level="medium", estimated_runtime="~20s",
        fields=[_checkbox("flag_external_only", "Flag External IPs Only")],
    ),
    _module(
        "pcap.pcap_file_extraction", "File Extraction", "pcap", "zeek / tshark",
        "Carves out files transferred over the captured traffic.",
        "Extracted transferred files", ["pcap"],
        risk_level="medium", isolation_level="sandboxed", queue_name="sandbox_queue",
        estimated_runtime="~30s",
        fields=[_select("max_file_size", "Max File Size", ["No limit", "10 MB", "50 MB"], "No limit")],
    ),
    _module(
        "pcap.suricata_alert_scan", "Suricata Alert Scan", "pcap", "suricata",
        "Replays the capture through Suricata IDS rules.",
        "IDS alerts", ["pcap"],
        risk_level="medium", required_plan="advanced", queue_name="standard_queue",
        estimated_runtime="~1 minute",
        fields=[_select("ruleset_version", "Ruleset", ["Emerging Threats", "Custom"], "Emerging Threats")],
    ),
    _module(
        "pcap.zeek_log_generation", "Zeek Log Generation", "pcap", "zeek",
        "Generates Zeek's standard log set for the capture.",
        "conn.log, dns.log, http.log, ssl.log, files.log", ["pcap"],
        required_plan="analyst", queue_name="standard_queue", estimated_runtime="~1 minute",
        fields=[
            ModuleOption(
                key="logs", label="Logs", type="checklist",
                options=["conn", "dns", "http", "ssl", "files"],
                default=["conn", "dns", "http", "ssl", "files"],
            )
        ],
    ),
    _module(
        "pcap.network_ioc_extraction", "Network IOC Extraction", "pcap", "custom parser",
        "Parses recognizable network indicators out of the capture.",
        "IPs, domains, URLs, hashes", ["pcap"],
        estimated_runtime="~20s", fields=_ioc_fields(),
    ),
]

# --------------------------------------------------------------------------
# Email / EML modules.
# --------------------------------------------------------------------------

EMAIL_MODULES: list[AnalysisModule] = [
    _module(
        "email.email_header_analysis", "Email Header Analysis", "email", "mailparser",
        "Parses sender, receiver, subject, message-id, and routing headers.",
        "Sender, receiver, subject, message-id, routing", ["email"],
        estimated_runtime="~5s",
        fields=[
            _checkbox("parse_received_chain", "Parse Received Chain"),
            _checkbox("extract_sender_ips", "Extract Sender IPs"),
            _checkbox("validate_auth_results", "Validate Authentication Results"),
        ],
    ),
    _module(
        "email.received_path_analysis", "Received Path Analysis", "email", "custom parser",
        "Reconstructs the mail relay chain and per-hop timestamps.",
        "Mail relay chain and timestamps", ["email"],
        estimated_runtime="~5s",
        fields=[_checkbox("parse_received_chain", "Parse Received Chain"), _checkbox("extract_sender_ips", "Extract Sender IPs")],
    ),
    _module(
        "email.spf_dkim_dmarc_check", "SPF / DKIM / DMARC Check", "email", "auth parser / DNS resolver if allowed",
        "Evaluates the message's sender-authentication results.",
        "Authentication result", ["email"],
        isolation_level="network_restricted", estimated_runtime="~10s",
        fields=[_checkbox("resolve_dns", "Resolve DNS Live (if allowed)", False)],
    ),
    _module(
        "email.email_url_extraction", "URL Extraction", "email", "custom parser",
        "Extracts URLs and domains, optionally following redirect chains.",
        "URLs, domains, redirect chains if enabled", ["email"],
        isolation_level="network_restricted", estimated_runtime="~10s",
        fields=[_checkbox("follow_redirects", "Follow Redirects (if allowed)", False)],
    ),
    _module(
        "email.attachment_extraction", "Attachment Extraction", "email", "ripmime / munpack",
        "Pulls attachments out of the message for separate analysis.",
        "Extracted attachments", ["email"],
        risk_level="medium", isolation_level="sandboxed", queue_name="sandbox_queue",
        estimated_runtime="~10s", fields=[_number("max_attachments", "Max Attachments", 10)],
    ),
    _module(
        "email.attachment_hashing", "Attachment Hashing", "email", "hashdeep",
        "Hashes every extracted attachment for lookups.",
        "Hashes of attachments", ["email"],
        estimated_runtime="~10s", fields=_hash_fields(),
    ),
    _module(
        "email.phishing_indicator_scan", "Phishing Indicator Scan", "email", "custom rules",
        "Flags suspicious senders, links, and domain mismatches.",
        "Suspicious sender, links, mismatched domains", ["email"],
        risk_level="medium", required_plan="analyst", estimated_runtime="~10s", fields=_sensitivity_field(),
    ),
    _module(
        "email.email_ioc_extraction", "Email IOC Extraction", "email", "custom parser",
        "Parses recognizable indicators out of the message and attachments.",
        "Sender IPs, domains, URLs, attachments", ["email"],
        estimated_runtime="~10s", fields=_ioc_fields(),
    ),
]

# --------------------------------------------------------------------------
# Image forensics modules.
# --------------------------------------------------------------------------

IMAGE_MODULES: list[AnalysisModule] = [
    _module(
        "image.image_metadata", "Image Metadata", "image", "exiftool",
        "Reads camera, GPS, timestamp, and software metadata.",
        "Camera, GPS, timestamps, software", ["image"],
        estimated_runtime="~5s",
        fields=[
            _checkbox("include_gps", "Include GPS"),
            _checkbox("extract_thumbnail", "Extract Thumbnail"),
            _select("output_format", "Output Format", ["Summary", "JSON"], "JSON"),
        ],
    ),
    _module(
        "image.image_integrity_check", "Image Integrity Check", "image", "jpeginfo / pngcheck",
        "Checks for corrupted or modified file structure.",
        "Corrupted or modified structure", ["image"],
        estimated_runtime="~5s", fields=[_checkbox("strict_mode", "Strict Mode")],
    ),
    _module(
        "image.thumbnail_extraction", "Thumbnail Extraction", "image", "exiftool",
        "Pulls any embedded thumbnail image out of the file.",
        "Embedded thumbnails", ["image"],
        estimated_runtime="~5s", fields=_output_format_field(["JPEG", "PNG"], "JPEG"),
    ),
    _module(
        "image.hidden_data_check", "Hidden Data Check", "image", "binwalk / zsteg / steghide check",
        "Looks for data appended or embedded beyond the visible image.",
        "Possible embedded data", ["image"],
        risk_level="medium", estimated_runtime="~15s", fields=_sensitivity_field(),
    ),
    _module(
        "image.image_hashing", "Image Hashing", "image", "hashdeep",
        "Computes file hashes for integrity and lookups.",
        "File hashes", ["image"],
        estimated_runtime="~5s", fields=_hash_fields(),
    ),
    _module(
        "image.pixel_dimension_analysis", "Pixel / Dimension Analysis", "image", "imagemagick identify",
        "Reads dimensions, color space, and compression details.",
        "Dimensions, color space, compression", ["image"],
        estimated_runtime="~5s", fields=_output_format_field(["Summary", "JSON"], "Summary"),
    ),
    _module(
        "image.ocr_text_extraction", "OCR Text Extraction", "image", "tesseract if available",
        "Runs OCR to recover any text rendered in the image.",
        "Detected text", ["image"],
        estimated_runtime="~15s", fields=[_select("language", "Language", ["English", "Auto-detect"], "English")],
    ),
    _module(
        "image.steganography_triage", "Steganography Triage", "image", "zsteg / stegdetect-style checks",
        "Runs quick checks for common steganographic channels.",
        "Possible hidden channels", ["image"],
        risk_level="medium", estimated_runtime="~20s", fields=_sensitivity_field(),
    ),
]

# --------------------------------------------------------------------------
# Audio forensics modules.
# --------------------------------------------------------------------------

AUDIO_MODULES: list[AnalysisModule] = [
    _module(
        "audio.audio_metadata", "Audio Metadata", "audio", "exiftool / mediainfo",
        "Reads codec, bitrate, timestamp, and tag metadata.",
        "Codec, bitrate, timestamps, tags", ["audio"],
        estimated_runtime="~5s", fields=_output_format_field(["Summary", "JSON"], "JSON"),
    ),
    _module(
        "audio.waveform_summary", "Waveform Summary", "audio", "ffmpeg / sox",
        "Summarizes duration, channels, and sample rate.",
        "Duration, channels, sample rate", ["audio"],
        estimated_runtime="~10s", fields=_output_format_field(["Summary", "JSON"], "Summary"),
    ),
    _module(
        "audio.spectrogram_generation", "Spectrogram Generation", "audio", "sox / ffmpeg",
        "Renders a spectrogram image artifact for visual review.",
        "Spectrogram image artifact", ["audio"],
        estimated_runtime="~20s",
        fields=[
            _select("frequency_range", "Frequency Range", ["0-8 kHz", "0-16 kHz", "Full spectrum"], "Full spectrum"),
            _checkbox("generate_png", "Generate PNG Artifact"),
            _select("output_format", "Output Format", ["PNG", "JSON"], "PNG"),
        ],
    ),
    _module(
        "audio.hidden_tone_dtmf_detection", "Hidden Tone / DTMF Detection", "audio", "multimon-ng / custom analyzer",
        "Detects DTMF tones or other encoded tone sequences.",
        "Detected tones or sequences", ["audio"],
        estimated_runtime="~20s", fields=_sensitivity_field(),
    ),
    _module(
        "audio.audio_hashing", "Audio Hashing", "audio", "hashdeep",
        "Computes file hashes for integrity and lookups.",
        "Hashes", ["audio"],
        estimated_runtime="~5s", fields=_hash_fields(),
    ),
    _module(
        "audio.silence_spike_detection", "Silence / Spike Detection", "audio", "custom analyzer",
        "Flags abnormal silence gaps or volume spikes.",
        "Suspicious silence, spikes, anomalies", ["audio"],
        estimated_runtime="~15s", fields=[_number("threshold_db", "Threshold (dB)", -40)],
    ),
]

# --------------------------------------------------------------------------
# Video forensics modules.
# --------------------------------------------------------------------------

VIDEO_MODULES: list[AnalysisModule] = [
    _module(
        "video.video_metadata", "Video Metadata", "video", "mediainfo / exiftool",
        "Reads codec, duration, resolution, and timestamp metadata.",
        "Codec, duration, resolution, timestamps", ["video"],
        estimated_runtime="~10s", fields=_output_format_field(["Summary", "JSON"], "JSON"),
    ),
    _module(
        "video.frame_extraction", "Frame Extraction", "video", "ffmpeg",
        "Extracts frames at a fixed interval for review.",
        "Selected frames", ["video"],
        estimated_runtime="~30s",
        fields=[_select("interval", "Interval", ["Every 1s", "Every 5s", "Every 10s"], "Every 5s")],
    ),
    _module(
        "video.keyframe_extraction", "Keyframe Extraction", "video", "ffmpeg",
        "Extracts only the encoded keyframes.",
        "Keyframes", ["video"],
        estimated_runtime="~20s", fields=[_number("max_frames", "Max Frames", 20)],
    ),
    _module(
        "video.audio_track_extraction", "Audio Track Extraction", "video", "ffmpeg",
        "Pulls the audio track out as a standalone artifact.",
        "Audio artifact", ["video"],
        estimated_runtime="~15s", fields=_output_format_field(["WAV", "MP3"], "WAV"),
    ),
    _module(
        "video.video_hashing", "Video Hashing", "video", "hashdeep",
        "Computes file hashes for integrity and lookups.",
        "Hashes", ["video"],
        estimated_runtime="~10s", fields=_hash_fields(),
    ),
]

# --------------------------------------------------------------------------
# Memory forensics modules - all advanced plan, heavy_queue, never batched.
# --------------------------------------------------------------------------

_MEMORY_VOLATILITY_FIELDS = [
    _select("os_type", "OS Type", ["Auto-detect", "Windows", "Linux", "macOS"], "Auto-detect"),
    _select("symbol_mode", "Symbol Mode", ["Online symbol server", "Local symbol cache", "Offline / none"], "Online symbol server"),
    _select("output_format", "Plugin Output Format", ["Text", "JSON"], "JSON"),
]

_MEMORY_MODULE_DEFS = [
    ("memory_image_info", "Memory Image Info", "volatility3", "OS info, symbols, architecture", "low"),
    ("process_list", "Process List", "volatility3 pslist", "Process table", "low"),
    ("process_tree", "Process Tree", "volatility3 pstree", "Parent-child process tree", "low"),
    ("process_scan", "Process Scan", "volatility3 psscan", "Hidden/terminated process scan", "medium"),
    ("network_connections", "Network Connections", "volatility3 netscan", "Sockets, connections, listening ports", "medium"),
    ("command_line", "Command Line", "volatility3 cmdline", "Process command lines", "low"),
    ("dll_list", "DLL List", "volatility3 dlllist", "Loaded DLLs/modules", "low"),
    ("malfind", "Malfind", "volatility3 malfind", "Injected/suspicious memory regions", "high"),
    ("handles", "Handles", "volatility3 handles", "Process handles", "low"),
    ("services", "Services", "volatility3 svcscan", "Windows services", "low"),
    ("registry_hive_list", "Registry Hive List", "volatility3 hivelist", "Registry hives", "low"),
    ("execution_artifacts", "UserAssist / Shimcache / Amcache", "volatility3 plugins", "Execution artifacts", "medium"),
]

MEMORY_MODULES: list[AnalysisModule] = [
    _module(
        f"memory.{module_id}", name, "memory", tool,
        f"{name} via {tool}.", output, ["memory"],
        risk_level=risk_level, required_plan="advanced", queue_name="heavy_queue",
        timeout_seconds=600, estimated_runtime="1-6 minutes",
        batchable=False, fields=_MEMORY_VOLATILITY_FIELDS,
    )
    for module_id, name, tool, output, risk_level in _MEMORY_MODULE_DEFS
]

# --------------------------------------------------------------------------
# Disk image modules - all advanced plan, heavy_queue.
# --------------------------------------------------------------------------

DISK_MODULES: list[AnalysisModule] = [
    _module(
        "disk.partition_table", "Partition Table", "disk", "mmls",
        "Lists partitions and their offsets within the image.",
        "Partitions and offsets", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", estimated_runtime="~10s",
        fields=_output_format_field(["Text", "JSON"], "Text"),
    ),
    _module(
        "disk.filesystem_info", "File System Info", "disk", "fsstat",
        "Reads filesystem-level metadata for a partition.",
        "Filesystem metadata", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", estimated_runtime="~15s",
        fields=_output_format_field(["Text", "JSON"], "Text"),
    ),
    _module(
        "disk.file_listing", "File Listing", "disk", "fls",
        "Walks the filesystem tree and lists every file.",
        "File tree", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", timeout_seconds=300,
        estimated_runtime="~1-3 minutes", fields=[_checkbox("include_deleted", "Include Deleted Entries", False)],
    ),
    _module(
        "disk.deleted_file_listing", "Deleted File Listing", "disk", "fls with deleted entries",
        "Lists filesystem entries marked deleted.",
        "Deleted files", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", timeout_seconds=300,
        estimated_runtime="~1-3 minutes", fields=[_checkbox("recoverable_only", "Recoverable Only")],
    ),
    _module(
        "disk.disk_file_extraction", "File Extraction", "disk", "icat / tsk_recover",
        "Carves out specific files by inode/offset.",
        "Extracted selected files", ["disk"],
        risk_level="medium", isolation_level="sandboxed", required_plan="advanced",
        queue_name="sandbox_queue", timeout_seconds=240, estimated_runtime="~30s-2 minutes",
        fields=[_select("max_file_size", "Max File Size", ["No limit", "10 MB", "50 MB"], "No limit")],
    ),
    _module(
        "disk.timeline_generation", "Timeline Generation", "disk", "log2timeline / fls bodyfile",
        "Builds a filesystem-wide MAC-time timeline.",
        "Filesystem timeline", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", timeout_seconds=900,
        estimated_runtime="3-10 minutes",
        fields=[
            _select("timezone", "Timezone", ["UTC", "System default", "Custom"], "UTC"),
            _checkbox("include_deleted_files", "Include Deleted Files"),
            _select("output_format", "Output Format", ["CSV", "JSON"], "CSV"),
        ],
    ),
    _module(
        "disk.browser_artifact_scan", "Browser Artifact Scan", "disk", "custom parser / sqlite parsers",
        "Recovers browser history, downloads, and cookies if present.",
        "History, downloads, cookies if present", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", timeout_seconds=180,
        estimated_runtime="~1 minute", fields=[_checkbox("include_cookies", "Include Cookies")],
    ),
    _module(
        "disk.windows_registry_extraction", "Windows Registry Extraction", "disk", "regripper / hivex",
        "Extracts artifacts from the Windows registry hives.",
        "Registry artifacts", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", timeout_seconds=180,
        estimated_runtime="~1 minute",
        fields=[
            ModuleOption(
                key="hives", label="Hives", type="checklist",
                options=["SYSTEM", "SOFTWARE", "SAM", "NTUSER.DAT"], default=["SYSTEM", "SOFTWARE"],
            )
        ],
    ),
    _module(
        "disk.event_log_extraction", "Event Log Extraction", "disk", "evtx_dump / chainsaw / hayabusa",
        "Extracts and runs detections over Windows event logs.",
        "Windows event logs and detections", ["disk"],
        risk_level="medium", required_plan="advanced", queue_name="heavy_queue", timeout_seconds=300,
        estimated_runtime="1-3 minutes", fields=[_checkbox("sigma_rules", "Run Sigma Rules")],
    ),
    _module(
        "disk.prefetch_analysis", "Prefetch Analysis", "disk", "prefetch parser",
        "Lists programs executed according to Prefetch records.",
        "Executed programs", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", estimated_runtime="~20s",
        fields=_output_format_field(["Text", "JSON"], "Text"),
    ),
    _module(
        "disk.lnk_jumplist_analysis", "LNK / JumpList Analysis", "disk", "lnk parser",
        "Parses shortcut and jump-list artifacts for accessed paths.",
        "Shortcut artifacts", ["disk"],
        required_plan="advanced", queue_name="heavy_queue", estimated_runtime="~20s",
        fields=_output_format_field(["Text", "JSON"], "Text"),
    ),
]

# --------------------------------------------------------------------------
# Document forensics modules.
# --------------------------------------------------------------------------

DOCUMENT_MODULES: list[AnalysisModule] = [
    _module(
        "document.document_metadata", "Document Metadata", "document", "exiftool",
        "Reads author, timestamp, and producer-software metadata.",
        "Author, timestamps, producer software", ["document"],
        estimated_runtime="~5s", fields=_output_format_field(["Summary", "JSON"], "JSON"),
    ),
    _module(
        "document.pdf_structure_analysis", "PDF Structure Analysis", "document", "pdfid / pdf-parser",
        "Inspects PDF objects for embedded JavaScript and files.",
        "Objects, JavaScript, embedded files", ["document"],
        risk_level="medium", required_plan="analyst", estimated_runtime="~15s",
        fields=[_checkbox("extract_javascript", "Extract JavaScript")],
    ),
    _module(
        "document.office_macro_analysis", "Office Macro Analysis", "document", "olevba",
        "Extracts and flags suspicious VBA macro content.",
        "Macros, suspicious keywords", ["document"],
        risk_level="medium", isolation_level="sandboxed", required_plan="analyst",
        queue_name="sandbox_queue", estimated_runtime="~15s",
        fields=[_checkbox("deobfuscate", "Deobfuscate")],
    ),
    _module(
        "document.embedded_object_extraction", "Embedded Object Extraction", "document", "oletools / binwalk",
        "Pulls embedded OLE objects and files out of the document.",
        "Embedded files", ["document"],
        risk_level="medium", isolation_level="sandboxed", queue_name="sandbox_queue",
        estimated_runtime="~20s", fields=[_number("max_objects", "Max Objects", 50)],
    ),
    _module(
        "document.document_link_extraction", "Link Extraction", "document", "custom parser",
        "Extracts URLs and domains referenced in the document.",
        "URLs/domains", ["document"],
        isolation_level="network_restricted", required_plan="analyst", estimated_runtime="~10s",
        fields=[_checkbox("follow_redirects", "Follow Redirects (if allowed)", False)],
    ),
    _module(
        "document.suspicious_document_indicators", "Suspicious Document Indicators", "document", "custom rules",
        "Flags auto-open macros, obfuscation, and external template injection.",
        "Auto-open macros, obfuscation, external templates", ["document"],
        risk_level="medium", estimated_runtime="~15s", fields=_sensitivity_field(),
    ),
]

# --------------------------------------------------------------------------
# Archive modules.
# --------------------------------------------------------------------------

ARCHIVE_MODULES: list[AnalysisModule] = [
    _module(
        "archive.archive_listing", "Archive Listing", "archive", "7z / unzip / unrar",
        "Lists the archive's contents without extracting.",
        "File list", ["archive"],
        estimated_runtime="~10s", fields=_output_format_field(["Text", "JSON"], "Text"),
    ),
    _module(
        "archive.archive_metadata", "Archive Metadata", "archive", "7z / exiftool",
        "Reads compression method and per-entry timestamps.",
        "Compression info, timestamps", ["archive"],
        estimated_runtime="~10s", fields=_output_format_field(["Text", "JSON"], "JSON"),
    ),
    _module(
        "archive.archive_recursive_extraction", "Recursive Extraction", "archive", "7z / custom extractor",
        "Recursively extracts nested archives.",
        "Extracted files", ["archive"],
        risk_level="medium", isolation_level="sandboxed", required_plan="advanced",
        queue_name="sandbox_queue", timeout_seconds=240, estimated_runtime="~30s-2 minutes",
        fields=[_number("max_depth", "Max Depth", 5)],
    ),
    _module(
        "archive.password_protection_check", "Password Protection Check", "archive", "7z",
        "Checks whether the archive is password-protected.",
        "Protected/not protected", ["archive"],
        estimated_runtime="~5s", fields=[_checkbox("brute_force_common", "Try Common Passwords", False)],
    ),
    _module(
        "archive.nested_file_type_detection", "Nested File Type Detection", "archive", "file / libmagic",
        "Detects the real type of every extracted file.",
        "Detected types of extracted files", ["archive"],
        estimated_runtime="~15s", fields=_output_format_field(["Text", "JSON"], "JSON"),
    ),
]

# --------------------------------------------------------------------------
# Mobile / APK modules.
# --------------------------------------------------------------------------

MOBILE_MODULES: list[AnalysisModule] = [
    _module(
        "mobile.apk_manifest_analysis", "APK Manifest Analysis", "mobile", "apktool / androguard",
        "Parses the manifest for package info, activities, and services.",
        "Package info, activities, services", ["mobile"],
        required_plan="analyst", estimated_runtime="~20s", fields=_output_format_field(["Summary", "JSON"], "JSON"),
    ),
    _module(
        "mobile.apk_permission_analysis", "APK Permission Analysis", "mobile", "androguard",
        "Lists requested permissions and flags dangerous ones.",
        "Requested permissions", ["mobile"],
        required_plan="analyst", estimated_runtime="~20s",
        fields=[_checkbox("flag_dangerous_only", "Flag Dangerous Permissions Only")],
    ),
    _module(
        "mobile.jadx_decompile", "JADX Decompile", "mobile", "jadx",
        "Decompiles the APK back to a Java source tree.",
        "Java source tree", ["mobile"],
        risk_level="medium", isolation_level="sandboxed", required_plan="advanced",
        queue_name="heavy_queue", timeout_seconds=300, estimated_runtime="1-3 minutes",
        fields=[_select("output_format", "Output Format", ["Java source", "Smali"], "Java source")],
    ),
    _module(
        "mobile.mobile_resource_extraction", "Resource Extraction", "mobile", "apktool",
        "Extracts resources and assets bundled in the package.",
        "Resources, assets", ["mobile"],
        required_plan="analyst", estimated_runtime="~30s", fields=[_number("max_files", "Max Files", 200)],
    ),
    _module(
        "mobile.mobile_ioc_extraction", "Mobile IOC Extraction", "mobile", "custom parser",
        "Parses recognizable indicators out of strings and resources.",
        "URLs, IPs, domains, keys", ["mobile"],
        required_plan="analyst", estimated_runtime="~20s", fields=_ioc_fields(),
    ),
    _module(
        "mobile.tracker_sdk_detection", "Tracker / SDK Detection", "mobile", "custom signatures",
        "Flags known third-party tracker and ad-SDK libraries.",
        "Detected libraries/SDKs", ["mobile"],
        required_plan="analyst", estimated_runtime="~20s", fields=_sensitivity_field(),
    ),
    _module(
        "mobile.ios_ipa_metadata", "iOS IPA Metadata", "mobile", "unzip / plist parser",
        "Reads Info.plist and entitlements from an iOS package.",
        "Info.plist, entitlements", ["mobile"],
        required_plan="analyst", estimated_runtime="~15s", fields=_output_format_field(["Summary", "JSON"], "JSON"),
    ),
]

# --------------------------------------------------------------------------
# Logs / EVTX modules - all on standard_queue per spec.
# --------------------------------------------------------------------------

LOGS_MODULES: list[AnalysisModule] = [
    _module(
        "logs.evtx_parse", "EVTX Parse", "logs", "evtx_dump",
        "Parses Windows EVTX records into a structured form.",
        "Parsed events", ["logs"],
        required_plan="analyst", queue_name="standard_queue", estimated_runtime="~30s",
        fields=[_select("event_id_filter", "Event ID Filter", ["All", "Security only", "System only"], "All")],
    ),
    _module(
        "logs.sigma_rule_scan", "Sigma Rule Scan", "logs", "chainsaw / hayabusa",
        "Runs Sigma detection rules over the parsed log records.",
        "Detections", ["logs"],
        risk_level="medium", required_plan="advanced", queue_name="standard_queue",
        estimated_runtime="~1 minute",
        fields=[_select("ruleset_version", "Ruleset", ["Default", "Custom"], "Default")],
    ),
    _module(
        "logs.windows_logon_events", "Windows Logon Events", "logs", "custom EVTX parser",
        "Summarizes logon/logoff activity from Security events.",
        "Logon/logoff activity", ["logs"],
        required_plan="analyst", queue_name="standard_queue", estimated_runtime="~30s",
        fields=_output_format_field(["Text", "JSON"], "Text"),
    ),
    _module(
        "logs.powershell_event_analysis", "PowerShell Event Analysis", "logs", "chainsaw / custom rules",
        "Flags script-block logging events and decodes obfuscation.",
        "Script block indicators", ["logs"],
        risk_level="medium", required_plan="advanced", queue_name="standard_queue",
        estimated_runtime="~30s", fields=[_checkbox("decode_base64", "Decode Base64 Payloads")],
    ),
    _module(
        "logs.web_access_log_analysis", "Web Access Log Analysis", "logs", "custom parser",
        "Summarizes requests by IP, path, status code, and user agent.",
        "IPs, paths, status codes, user agents", ["logs"],
        required_plan="analyst", queue_name="standard_queue", estimated_runtime="~20s",
        fields=_output_format_field(["Text", "JSON"], "JSON"),
    ),
    _module(
        "logs.auth_log_analysis", "Auth Log Analysis", "logs", "custom parser",
        "Flags failed logins, SSH activity, and sudo usage.",
        "Failed logins, SSH activity, sudo usage", ["logs"],
        risk_level="medium", required_plan="advanced", queue_name="standard_queue",
        estimated_runtime="~20s", fields=[_checkbox("flag_failed_only", "Flag Failed Attempts Only", False)],
    ),
    _module(
        "logs.log_timeline_builder", "Timeline Builder", "logs", "custom timeline normalizer",
        "Normalizes parsed log events into a single timeline.",
        "Timeline events", ["logs"],
        required_plan="analyst", queue_name="standard_queue", estimated_runtime="~30s",
        fields=[_select("timezone", "Timezone", ["UTC", "System default"], "UTC")],
    ),
]

# A registry of every module available for analysis, keyed by id.
MODULES: dict[str, AnalysisModule] = {
    module.id: module
    for module in [
        *GENERIC_MODULES,
        *BINARY_MODULES,
        *PCAP_MODULES,
        *EMAIL_MODULES,
        *IMAGE_MODULES,
        *AUDIO_MODULES,
        *VIDEO_MODULES,
        *MEMORY_MODULES,
        *DISK_MODULES,
        *DOCUMENT_MODULES,
        *ARCHIVE_MODULES,
        *MOBILE_MODULES,
        *LOGS_MODULES,
    ]
}
