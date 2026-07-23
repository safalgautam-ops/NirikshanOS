"""Jinja globals used by app/templates/components/ui/*.html."""

import os
from markupsafe import Markup, escape
from flask import current_app


def asset_version(relative_path: str) -> str:
    """mtime of a file under app/static/, for a cache-busting `?v=` query string on script/link tags."""
    full_path = os.path.join(current_app.static_folder, relative_path)
    try:
        return str(int(os.path.getmtime(full_path)))
    except OSError:
        return "0"


def cn(*classes: object) -> str:
    """Join truthy class fragments with a space, skipping empty/None/False ones."""
    return " ".join(str(c) for c in classes if c)


def html_attrs(**attrs: object) -> Markup:
    """Render a dict of extra attributes as ` key="value"` pairs."""
    parts: list[str] = []
    for key, value in attrs.items():
        if value is False or value is None:
            continue
        name = key.replace("_", "-")
        if value is True:
            parts.append(name)
        else:
            parts.append(f'{name}="{escape(value)}"')
    return Markup(" ".join(parts))
