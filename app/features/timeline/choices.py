"""Fixed choice lists for the timeline item dialogs - same pattern as
app/features/cases/choices.py."""

ITEM_TYPES: list[tuple[str, str]] = [
    ("task", "Task"),
    ("note", "Note"),
    ("milestone", "Milestone"),
]

TASK_STATUSES: list[tuple[str, str]] = [
    ("pending", "Pending"),
    ("in_progress", "In Progress"),
    ("done", "Done"),
    ("blocked", "Blocked"),
    ("cancelled", "Cancelled"),
]

TASK_PRIORITIES: list[tuple[str, str]] = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
]

NOTE_VISIBILITIES: list[tuple[str, str]] = [
    ("private", "Private"),
    ("case_shared", "Case Shared"),
]
