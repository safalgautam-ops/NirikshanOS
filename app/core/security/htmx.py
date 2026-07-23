"""This code defines a helper function called redirect_or_htmx() that redirects users correctly whether the request came from a normal browser page load or from htmx."""

from __future__ import annotations

from flask import Response, redirect, request


def redirect_or_htmx(location: str):
    """Like redirect(), but htmx-aware."""
    if request.headers.get("HX-Request") == "true":
        response = Response(status=200)
        response.headers["HX-Redirect"] = location
        return response
    return redirect(location)
