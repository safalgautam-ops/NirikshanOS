"""

This file is the friendly front desk that the rest of your app actually talks to.

Logos and avatars are public assets (anyone with the org's invite link, or
viewing a profile, sees one) - they go to the anonymous-read public bucket
and the value stored in the DB is the final, directly-usable URL. Government
documents (registration certificates, PAN cards, owner IDs) are sensitive
and must never be reachable by guessing a URL - they go to the private
bucket and the DB stores a bare object key, only ever turned into a
short-lived presigned link via get_document_url().

Filenames are always generated server-side (new_id() + the original
extension) - the browser-supplied filename is never used to build a key,
which rules out path traversal/overwrite regardless of what a client sends.
"""

from __future__ import annotations

from werkzeug.datastructures import FileStorage

from app.config import Config
from app.core import object_storage
from app.core.utils.ids import new_id

ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
ALLOWED_AVATAR_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

# real upload limits for org-branding/KYC uploads (logo/document/avatar)
MAX_LOGO_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_DOCUMENT_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
# Matches MAX_CONTENT_LENGTH/nginx's client_max_body_size (app/config.py,
# docker/nginx/nginx.conf) - a single piece of evidence (e.g. a disk image)
# is exactly the kind of upload those ceilings exist for.
MAX_EVIDENCE_SIZE_BYTES = 100 * 1024 * 1024 * 1024  # 100 GB

_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
}


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


# converts bytes to a readable MB string
def _format_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.0f}MB"


def _content_type(ext: str) -> str:
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


# saves an uploaded organization logo
async def save_logo(file: FileStorage) -> str:
    """Save an uploaded logo to the public bucket. Returns the final,
    directly-usable URL."""
    ext = _extension(file.filename or "")
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise ValueError("Logo must be a PNG, JPG, WEBP, or SVG image.")
    # FileStorage.read() is plain Werkzeug, not Quart's async save()/load()
    # overrides - it returns bytes directly, nothing to await.
    data = file.read()
    if len(data) > MAX_LOGO_SIZE_BYTES:
        raise ValueError(
            f"Logo must be smaller than {_format_mb(MAX_LOGO_SIZE_BYTES)}."
        )
    key = f"org_logos/{new_id()}.{ext}"
    await object_storage.put_object(
        Config.MINIO_BUCKET_PUBLIC, key, data, _content_type(ext)
    )
    return object_storage.public_url(
        key
    )  # returns a stable, public URL that can be shared


async def save_document(file: FileStorage) -> tuple[str, str]:
    """Save an uploaded government document to the private bucket. Returns
    (object key - what gets stored in the DB, original filename - what gets
    shown to the user)."""
    ext = _extension(file.filename or "")
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValueError("Documents must be a PDF, PNG, or JPG file.")
    # FileStorage.read() is plain Werkzeug, not Quart's async save()/load()
    # overrides - it returns bytes directly, nothing to await.
    data = file.read()
    if len(data) > MAX_DOCUMENT_SIZE_BYTES:
        raise ValueError(
            f"Documents must be smaller than {_format_mb(MAX_DOCUMENT_SIZE_BYTES)}."
        )
    key = f"org_documents/{new_id()}.{ext}"
    await object_storage.put_object(
        Config.MINIO_BUCKET_PRIVATE, key, data, _content_type(ext)
    )
    return key, (file.filename or key)  # returns the object key and original filename


async def save_avatar(file: FileStorage) -> str:
    """Save an uploaded profile picture to the public bucket. Returns the
    final, directly-usable URL - same recipe as save_logo()."""
    ext = _extension(file.filename or "")
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        raise ValueError("Profile picture must be a PNG, JPG, or WEBP image.")
    # FileStorage.read() is plain Werkzeug, not Quart's async save()/load()
    # overrides - it returns bytes directly, nothing to await.
    data = file.read()
    if len(data) > MAX_AVATAR_SIZE_BYTES:
        raise ValueError(
            f"Profile picture must be smaller than {_format_mb(MAX_AVATAR_SIZE_BYTES)}."
        )
    key = f"avatars/{new_id()}.{ext}"
    await object_storage.put_object(
        Config.MINIO_BUCKET_PUBLIC, key, data, _content_type(ext)
    )
    return object_storage.public_url(key)


async def get_document_url(key: str) -> str:
    """A short-lived signed link for a private-bucket document - the
    download routes redirect here instead of streaming the file
    themselves."""
    return await object_storage.presigned_get_url(Config.MINIO_BUCKET_PRIVATE, key)


async def delete_file(value: str) -> None:
    """Best-effort delete of a previously-saved logo/avatar (always a full
    public_url) or document (always a bare private-bucket key) - used when
    an organization is deleted or a file is replaced, so uploads don't
    linger as orphans. Which bucket to delete from is disambiguated by
    shape (public values are always URLs, private values are always bare
    keys), so callers don't need to know or pass that themselves. A missing
    object is not an error - the DB row being gone is what matters.

    If the value starts with the public URL prefix, it must be a public file
    → strip that prefix to recover the key, delete from the public bucket.
    Otherwise it's a bare key → it's private → delete from the private bucket.

    """
    public_prefix = f"{Config.MINIO_PUBLIC_URL}/"
    if value.startswith(public_prefix):
        await object_storage.delete_object(
            Config.MINIO_BUCKET_PUBLIC, value[len(public_prefix) :]
        )
    else:
        await object_storage.delete_object(Config.MINIO_BUCKET_PRIVATE, value)
