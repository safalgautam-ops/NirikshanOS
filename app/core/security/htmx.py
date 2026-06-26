"""This code defines a helper function called redirect_or_htmx()
that redirects users correctly whether the request came from a normal
browser page load or from htmx.

redirect_or_htmx() is a safe redirect helper that uses a normal redirect
for normal browser requests, but uses HX-Redirect for htmx requests so a
full login/onboarding page does not get inserted into a small part of the
current page.
"""

from __future__ import annotations

from quart import Response, redirect, request


def redirect_or_htmx(location: str):
    """Like redirect(), but htmx-aware.

    A plain 302 gets auto-followed by htmx's underlying XHR, and whatever
    the followed URL returns - here, a full login or onboarding *page* -
    gets swapped into whatever small partial the original request was
    targeting (e.g. a case page's "Add member" search-results div), instead
    of replacing the whole browser page. That's what produces a login form
    rendered inside a search-results box: the request that triggered it
    (e.g. the member-search GET) hit this gate after the session had
    expired, and htmx dutifully swapped the entire followed login page into
    its small target element.

    HX-Redirect is htmx's documented escape hatch for this: a response
    header that tells it to do a real top-level navigation instead of a
    swap. Used by every redirect-on-auth-failure gate (login_required,
    require_permission, require_org_permission, the password-change and
    organization-onboarding before_request hooks in app/__init__.py).
    """
    if request.headers.get("HX-Request") == "true":
        response = Response(status=200)
        response.headers["HX-Redirect"] = location
        return response
    return redirect(location)
