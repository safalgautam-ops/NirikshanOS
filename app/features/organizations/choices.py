"""Fixed choice lists for the onboarding wizard's selects."""

ORG_TYPES: list[tuple[str, str]] = [
    ("private_limited", "Private Limited Company"),
    ("public_limited", "Public Limited Company"),
    ("partnership", "Partnership"),
    ("llp", "Limited Liability Partnership"),
    ("sole_proprietorship", "Sole Proprietorship"),
    ("ngo_trust", "NGO / Trust"),
    ("government", "Government Body"),
    ("other", "Other"),
]

EMPLOYEE_COUNT_RANGES: list[str] = ["1-10", "11-50", "51-200", "201-500", "500+"]
