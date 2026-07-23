"""Evidence type taxonomy — standalone constants, no module catalog dependency."""

from __future__ import annotations

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

_EVIDENCE_TYPE_EXTENSIONS: dict[str, list[str]] = {
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
    "generic": [
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
}

_EXT_MAP: dict[str, str] = {ext: et for et, exts in _EVIDENCE_TYPE_EXTENSIONS.items() for ext in exts}


def detect_evidence_type_from_filename(filename: str) -> str:
    if "." not in filename:
        return "unknown"
    ext = filename.rsplit(".", 1)[-1].lower()
    return _EXT_MAP.get(ext, "unknown")
