"""Jinja globals used by app/templates/components/ui/*.html.

These mirror the two helpers the reference Jinja component kit assumes exist
(cn() for joining conditional class fragments, html_attrs() for spreading a
caller-supplied dict of extra attributes) - the component templates call
them directly, so they have to be registered as globals, not imported.
"""

import os
from markupsafe import Markup, escape
from flask import current_app


def asset_version(relative_path: str) -> str:
    """mtime of a file under app/static/, for a cache-busting `?v=` query
    string on script/link tags. nginx serves /static/ with only ETag/
    Last-Modified validators and no Cache-Control (see nginx config) - a
    browser that already has an old copy in its disk cache from earlier in
    a long-lived tab isn't guaranteed to revalidate on every load, so an
    edited JS/CSS file can keep being served stale until a hard refresh.
    Appending the real mtime changes the URL itself whenever the file
    changes, which forces a fresh fetch regardless of cache heuristics."""
    full_path = os.path.join(current_app.static_folder, relative_path)
    try:
        return str(int(os.path.getmtime(full_path)))
    except OSError:
        return "0"


def cn(*classes: object) -> str:
    """Join truthy class fragments with a space, skipping empty/None/False ones."""
    return " ".join(str(c) for c in classes if c)


def html_attrs(**attrs: object) -> Markup:
    """Render a dict of extra attributes as ` key="value"` pairs.

    True -> bare attribute (e.g. disabled), False/None -> omitted entirely,
    anything else -> key="escaped value". Underscores in keys become hyphens
    so callers can pass data_foo=/aria_foo= as normal Python kwargs.
    """
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
