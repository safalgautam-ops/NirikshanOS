"""Fixed choice lists for the case-creation dialog's selects."""

CLASSIFICATIONS: list[tuple[str, str]] = [
    ("email_investigation", "Email Investigation"),
    ("log_audit_investigation", "Log/Audit Investigation"),
    ("device_forensics", "Device Forensics"),
    ("network_intrusion", "Network Intrusion"),
    ("account_compromise", "Account Compromise"),
    ("unauthorized_access", "Unauthorized Access"),
    ("malware_investigation", "Malware Investigation"),
    ("harassment_misconduct", "Harassment / Misconduct"),
    ("database_compromise", "Database Compromise"),
    ("system_damage", "System Damage"),
    ("memory_forensics", "Memory Forensics"),
    ("file_system_corruption", "File System Corruption"),
]

SEVERITIES: list[tuple[str, str]] = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

FORENSIC_STATUSES: list[tuple[str, str]] = [
    ("not_started", "Not Started"),
    ("queued", "Queued for Processing"),
    ("hash_verified", "Hash Verified"),
    ("hash_matching", "Hash Matching"),
    ("review_in_progress", "Review in Progress"),
    ("report_generation", "Report Generation"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("paused", "Paused"),
    ("cancelled", "Cancelled"),
]
