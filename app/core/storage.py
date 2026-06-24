"""Local disk storage for organization-onboarding uploads.

Logos are public assets (anyone with the org's invite link sees one), so
they live under app/static/uploads - nginx serves that directory directly,
same as every other static asset. Government documents (registration
certificates, PAN cards, owner IDs) are sensitive and must never be
reachable by guessing a URL, so they live outside app/static entirely and
can only be read back through the authenticated download route in
app/features/onboarding/routes.py.

Filenames are always generated server-side (new_id() + the original
extension) - the browser-supplied filename is never used to build a path,
which rules out path traversal/overwrite regardless of what a client sends.
Paths are stored in the DB relative to the project root, not absolute, so
they stay valid no matter where the checkout lives.
"""

from __future__ import annotations

from pathlib import Path

from werkzeug.datastructures import FileStorage

from app.core.utils.ids import new_id

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_LOGO_DIR = PROJECT_ROOT / "app" / "static" / "uploads" / "org_logos"
_DOCUMENT_DIR = PROJECT_ROOT / "storage" / "org_documents"

ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


async def save_logo(file: FileStorage) -> str:
    """Save an uploaded logo. Returns a path relative to app/static, ready
    for url_for('static', filename=...)."""
    ext = _extension(file.filename or "")
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise ValueError("Logo must be a PNG, JPG, WEBP, or SVG image.")
    _LOGO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{new_id()}.{ext}"
    # Quart's FileStorage.save() is async (unlike werkzeug's) - it streams
    # the upload to disk with aiofiles instead of blocking the event loop.
    await file.save(_LOGO_DIR / name)
    return f"uploads/org_logos/{name}"


async def save_document(file: FileStorage) -> tuple[str, str]:
    """Save an uploaded government document outside app/static. Returns
    (path relative to the project root - what gets stored in the DB,
    original filename - what gets shown to the user)."""
    ext = _extension(file.filename or "")
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValueError("Documents must be a PDF, PNG, or JPG file.")
    _DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{new_id()}.{ext}"
    await file.save(_DOCUMENT_DIR / name)
    return f"storage/org_documents/{name}", (file.filename or name)


def resolve_document_path(relative_path: str) -> Path:
    """The download route's only way to turn a DB-stored path back into a
    real filesystem path - keeps callers from ever building paths by hand."""
    return PROJECT_ROOT / relative_path


def delete_file(relative_path: str) -> None:
    """Best-effort delete of a previously-saved logo/document by its stored
    relative path - used when an organization is deleted, so its uploads
    don't linger on disk as orphans. Missing files are not an error (the DB
    row being gone is what matters)."""
    (PROJECT_ROOT / relative_path).unlink(missing_ok=True)
