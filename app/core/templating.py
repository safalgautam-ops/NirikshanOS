"""Jinja globals used by app/templates/components/ui/*.html.

These mirror the two helpers the reference Jinja component kit assumes exist
(cn() for joining conditional class fragments, html_attrs() for spreading a
caller-supplied dict of extra attributes) - the component templates call
them directly, so they have to be registered as globals, not imported.
"""

from markupsafe import Markup, escape


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
