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
_AVATAR_DIR = PROJECT_ROOT / "app" / "static" / "uploads" / "avatars"

ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
ALLOWED_AVATAR_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

# These are org-branding/KYC uploads (a logo image, a scanned registration
# certificate or ID), not forensic evidence - the platform's actual large-
# file workloads (disk/memory images, 30-100GB+) belong to a separate
# evidence-upload feature with its own, much larger limit declared the same
# way (a constant + a post-save size check), not by raising these.
MAX_LOGO_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_DOCUMENT_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _format_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.0f}MB"


async def save_logo(file: FileStorage) -> str:
    """Save an uploaded logo. Returns a path relative to app/static, ready
    for url_for('static', filename=...)."""
    ext = _extension(file.filename or "")
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise ValueError("Logo must be a PNG, JPG, WEBP, or SVG image.")
    _LOGO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{new_id()}.{ext}"
    path = _LOGO_DIR / name
    # Quart's FileStorage.save() is async (unlike werkzeug's) - it streams
    # the upload to disk with aiofiles instead of blocking the event loop.
    await file.save(path)
    # Checked after saving, not via the Content-Length header beforehand -
    # that header is client-supplied and can't be trusted to actually match
    # what gets sent.
    if path.stat().st_size > MAX_LOGO_SIZE_BYTES:
        path.unlink(missing_ok=True)
        raise ValueError(f"Logo must be smaller than {_format_mb(MAX_LOGO_SIZE_BYTES)}.")
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
    path = _DOCUMENT_DIR / name
    await file.save(path)
    if path.stat().st_size > MAX_DOCUMENT_SIZE_BYTES:
        path.unlink(missing_ok=True)
        raise ValueError(f"Documents must be smaller than {_format_mb(MAX_DOCUMENT_SIZE_BYTES)}.")
    return f"storage/org_documents/{name}", (file.filename or name)


async def save_avatar(file: FileStorage) -> str:
    """Save an uploaded profile picture. Returns a path relative to
    app/static, ready for url_for('static', filename=...) - same recipe as
    save_logo()."""
    ext = _extension(file.filename or "")
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        raise ValueError("Profile picture must be a PNG, JPG, or WEBP image.")
    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{new_id()}.{ext}"
    path = _AVATAR_DIR / name
    await file.save(path)
    if path.stat().st_size > MAX_AVATAR_SIZE_BYTES:
        path.unlink(missing_ok=True)
        raise ValueError(f"Profile picture must be smaller than {_format_mb(MAX_AVATAR_SIZE_BYTES)}.")
    return f"uploads/avatars/{name}"


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
