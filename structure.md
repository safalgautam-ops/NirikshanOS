# NirikshanOS Architecture and Project Structure

This file describes the current repository. It is not a future roadmap.

## Runtime architecture

NirikshanOS is a **Flask WSGI application** served by Gunicorn. The HTTP and
Jinja layer uses Flask, while the existing asynchronous repositories and
services continue to run on one persistent application event loop through
`app/core/async_runtime.py`.

This bridge is intentional:

- Flask owns routing, request contexts, responses, sessions, and templates.
- Existing `asyncmy`, Redis, MinIO, and asynchronous service calls remain
  asynchronous and are not rewritten into a second data-access stack.
- Request context variables are copied to the persistent loop so asynchronous
  handlers can safely access `request`, `g`, and `current_app`.
- Background tasks created by application services are not cancelled when an
  HTTP response completes.

The worker remains a separate process under `workers/` and is not converted
into Flask code. Non-empty legacy files that were present under `storage/` in
the working source archive are preserved, although current uploads use MinIO
and analysis workspaces use the configured external `JOBS_DIR` mount.

## Services

`docker-compose.yml` starts the existing service topology:

- `web`: Flask application served by Gunicorn on port 8000 inside the network.
- `worker`: analysis worker and Docker-based job execution.
- `mysql`: application database.
- `redis`: sessions, rate limiting, queues, and transient runtime state.
- `minio`: public/private S3-compatible object storage.
- `minio-init`: idempotent bucket setup.
- `nginx`: local reverse proxy.

The original SQL migration files and migration order are preserved under
`migrations/`. The Flask conversion does not replace, reorder, or auto-rewrite
the database schema.

## Backend layout

```text
app/
├── __init__.py                 Flask application factory and blueprint setup
├── core/
│   ├── async_runtime.py        Persistent asyncio bridge used by AsyncFlask
│   ├── db/                     Existing async MySQL pool, ORM, and query layer
│   ├── security/               CSRF, headers, rate limits, sessions, permissions
│   ├── audit/                  Shared audit support
│   ├── email/                  Email infrastructure
│   └── templating.py           Shared Jinja helpers
├── features/                   Domain blueprints, services, and repositories
├── static/                     Page CSS/JS, vendor assets, and images
└── templates/                  Layouts, style.css, pages, and UI macros

workers/                        Existing background analysis worker
migrations/                     Existing ordered SQL migrations
storage/                        Non-empty legacy files preserved from the source archive
docker/                         Docker and Nginx configuration
run.py                          WSGI entry point
```

Feature modules keep their existing contracts. Routes may be asynchronous, but
Flask invokes them through `AsyncFlask.ensure_sync()` on the persistent loop.

## Frontend layout

Tailwind uses the CodeSandbox-style browser setup and one Jinja-included source:

```text
app/templates/
├── style.css                   Tailwind v4 design tokens and application styles
└── layouts/base.html           Loads Tailwind browser runtime and includes style.css

app/static/css/
└── vendor/                     Third-party styles used by CodeMirror

app/static/js/
├── app.js                      Theme, CSRF, shared UI behavior and validation
├── pages/                      Page-specific behavior loaded only where required
└── vendor/                     HTMX, CodeMirror and other third-party code
```

There is no `package.json`, compiled `tailwind.css`, Node dependency, or frontend
build command. The application remains server-rendered Flask/Jinja; it does not
use a client-side router.

## Template and component conventions

`app/templates/layouts/base.html` is the common document shell. Page templates
compose controls from `app/templates/components/ui/` rather than writing native
form controls directly.

Examples:

```jinja
{% import "components/ui/button.html" as button %}
{% import "components/ui/input.html" as input %}
{% import "components/ui/select-native.html" as select_native %}

{% call button.button(type="submit") %}Save{% endcall %}
{{ input.input(name="title", value=case.title) }}
{% call select_native.select_native(name="status") %}
  <option value="open">Open</option>
{% endcall %}
```

Rules:

1. Use `components/ui/` for generic controls and interaction primitives.
2. Use feature-local macros only for domain-specific composition.
3. Preserve stable `id`, `name`, HTMX attributes, and JavaScript data
   attributes when refactoring markup.
4. Native `<button>`, `<input>`, `<select>`, and `<textarea>` elements belong
   inside the shared component implementation, not page templates.
5. Put first-party page JavaScript in `app/static/js/pages/`; do not create a
   new directory per page.
6. Keep third-party files under `vendor/` and do not edit them as application
   source.

## Security boundaries

The existing controls remain in place:

- Redis-backed server-side sessions.
- CSRF validation for state-changing HTTP requests.
- Permission and organization guards.
- Rate limiting.
- Security headers and local-asset Content Security Policy.
- Parameterized database access through the existing async data layer.
- MinIO separation between public and private objects.
- Isolated worker containers for analysis jobs.

## Startup

```bash
docker compose up --build
```

For direct development outside Docker, install Python dependencies, build the
Tailwind output when templates/styles change, and run the WSGI entry point with
Gunicorn. External MySQL, Redis, and MinIO services are still required for
authenticated application workflows.
