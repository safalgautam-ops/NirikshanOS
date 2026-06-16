# NirikshanOS — Architecture, Folder Structure & 4-Week Roadmap

This document refines `plan.md` into a concrete, build-ready structure for NirikshanOS, a browser-based DFIR (Digital Forensics & Incident Response) platform. It updates the original stack in three ways:

1. **ASGI instead of WSGI** — Quart (async, Flask-like) served by uvicorn.
2. **No SQLAlchemy, no third-party ORM/validation packages** — a fully custom, class-based ORM-like data-access layer over raw async MySQL, custom input validation, a shared pagination helper, and a Jinja macros/components convention.
3. **Security-first** — RBAC, rate limiting, CSRF protection, SQL-injection prevention, security headers, and audit logging are all hand-built, part of the architecture from week 1, not bolted on later via libraries.

This is a planning document: no code, no diagrams other than the folder tree in Section B.

> **On dependencies**: the only third-party packages in this project are the web framework (Quart), the ASGI server (uvicorn), and a low-level MySQL wire-protocol driver (see below) — none of these provide ORM, validation, CSRF, rate-limiting, or session logic. Everything in those categories (Sections A.4–A.9) is custom code written for this project.

---

## A. Technology Stack & Rationale

### Web framework — Quart
Quart is an async, ASGI-native framework with the same mental model as Flask (app factory, blueprints, `request`, `render_template`, decorators). This keeps the API familiar while giving native `async`/`await`, which is needed for async MySQL queries, Redis pub/sub, and WebSockets. Quart has first-class WebSocket route support (`@app.websocket(...)`), which directly satisfies the "pure raw WebSocket, no SSE/Socket.IO" requirement.

### ASGI server — uvicorn (Hypercorn as documented fallback)
Quart apps are standard ASGI3 applications, so uvicorn can run them for HTTP, WebSocket, and lifespan events. uvicorn is used as the primary server per the chosen stack. Note for later: Quart is developed and tested primarily against Hypercorn, so if any WebSocket edge case (ping/pong, graceful shutdown) ever surfaces under uvicorn, Hypercorn is a one-line drop-in replacement in the Docker command — no application code changes needed.

### Database driver — minimal MySQL wire-protocol client only
A single low-level async MySQL driver (e.g. `asyncmy`, or pure-Python `PyMySQL`/`aiomysql` if a pure-Python option is preferred) is used **only** to open connections, send queries with parameter placeholders, and read result rows. This is the one unavoidable dependency — talking to MySQL means speaking its wire protocol, which is impractical to reimplement. Critically, the driver provides **no** ORM, query-builder, or validation features — everything above the socket level (models, queries, pagination, validation) is custom code described below. Connection pooling itself is also implemented in custom code (`core/db/pool.py`) on top of the driver's raw connections.

### Custom ORM — class-based models + query builder (`core/db/model.py`, `core/db/query_builder.py`, `core/db/fields.py`)
Instead of an ORM library, the project defines its own lightweight Active-Record-style layer:

- **`core/db/fields.py`** — small `Field` descriptor classes (`StringField`, `IntField`, `BoolField`, `DateTimeField`, `ForeignKeyField`, etc.). Each field declares a Python type, constraints (max length, required, default), and a `validate(value)` method. These descriptors double as the project's input-validation building blocks (see Validation below) — one definition serves both DB schema intent and form validation.
- **`core/db/model.py`** — a `Model` base class. Subclasses (in each feature's `models.py`) declare `__table__` (table name) and class-level `Field` attributes. `Model` provides instance methods (`save()`, `delete()`, `to_dict()`) and classmethods (`find(id)`, `where(**conditions)`, `all()`). Internally these build parameterized SQL using only the column names declared as `Field` attributes (a closed, whitelisted set) and `%s` placeholders for values — user input is **never** interpolated into the SQL string.
- **`core/db/query_builder.py`** — a small `QueryBuilder` class for queries the basic `Model` methods don't cover (ordering, multi-condition filters, limit/offset, counts). It composes SQL from a fixed set of clause templates plus whitelisted column names from `Model.fields()`, with all values passed as parameters to the driver — the same SQLi-prevention guarantee as `Model`.
- **`core/db/pagination.py`** — a `paginate()` function that wraps `QueryBuilder` with `LIMIT`/`OFFSET` plus a `COUNT(*)` query, returning a small `Page` object (items, total count, page number, total pages) consumed by `components/ui/pagination.html`.

Each feature's `repositories.py` becomes a thin layer of feature-specific queries built from `Model`/`QueryBuilder`, keeping business-specific data access out of the generic ORM core.

### Schema management — plain SQL, no migration runner
No migration tooling. Table definitions live as plain `.sql` files (e.g. `schema/*.sql`) applied manually against MySQL as the schema evolves. `app/core/db/` is intentionally limited to runtime concerns — connection pool, query builder, and pagination — not schema versioning.

### Validation — custom Field/Form classes (`core/validation/validators.py`)
No Pydantic or other validation library. Validation is built from the same `Field` descriptors used by the ORM (`core/db/fields.py`), plus a small `Form` base class in `core/validation/validators.py`:

- A `Form` subclass (in each feature's `forms.py`) declares the same kind of `Field` attributes as a `Model`, but represents *input* shape rather than a table — e.g. a `LoginForm` with `email` and `password` fields, independent of the `User` model.
- `Form.validate(data)` runs each field's `validate(value)` (type checks, required, max length, regex/format checks for things like email or filenames) and collects errors into a dict, returned to the route for re-rendering with error messages.
- Because the same `Field` classes back both `Model` columns and `Form` inputs, validation rules (e.g. "case title max 255 chars") are defined once and reused, without pulling in a schema library.

### Sessions — Redis-backed, server-side
Session data (user id, roles cache, etc.) is stored server-side in Redis, keyed by a session id. Cookies carry only the session id and are set `HttpOnly`, `Secure`, and `SameSite=Lax` (or `Strict` for sensitive flows). This avoids storing sensitive data client-side and allows centralized session invalidation (logout, forced re-auth after role changes, future 2FA/passkey flows).

### CSRF protection — custom middleware
Quart has no built-in CSRF protection (unlike Flask-WTF). A small `core/security/csrf.py` module generates a per-session signed token, exposes it to templates via a Jinja macro (`macros/csrf.html`), and validates it on every state-changing request (POST/PUT/PATCH/DELETE) via a `before_request` hook.

### Rate limiting — custom Redis-backed middleware
`core/security/rate_limit.py` implements request counters in Redis (fixed-window counters to start; sliding-window sorted sets as a later improvement), applied globally and/or per-route. Sensitive endpoints (`/auth/login`, `/auth/register`, evidence upload, analysis run) get stricter limits than general browsing.

### Security headers — custom middleware
`core/security/headers.py` sets `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Strict-Transport-Security` on every response via an `after_request` hook, applied from week 1.

### Redis — multi-purpose
A single Redis instance serves three roles for the MVP:
1. Pub/sub channel for worker → WebSocket live updates (per-case channels, e.g. `case:{id}:events`).
2. Server-side session storage.
3. Rate-limit counters.

These can be split into separate logical databases (`SELECT 0/1/2`) later if needed.

### Templating — Jinja2 with macros + components convention
- `layouts/` — base page skeletons (base, auth, dashboard).
- `macros/` — small, parameterized, reusable snippets: buttons, form fields, alerts, pagination controls, the CSRF hidden field.
- `components/` — larger composable blocks built from macros: navbar, sidebar, case card, evidence row, modal, activity feed.
- Per-feature template directories hold actual pages, composed from layouts + macros + components.

### File storage — local filesystem, structured by case/evidence id
- `storage/evidence/<case_id>/<evidence_id>/` — original uploaded files, treated as read-only after upload.
- `storage/outputs/<case_id>/<evidence_id>/<job_id>/` — analyzer-generated artifacts.

Physically separating originals from generated output enforces the "never execute uploaded files, separate evidence from output" rule at the filesystem level.

---

## B. Project Folder Structure

```
NirikshanOS/
├── README.md
├── plan.md
├── structure.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
│
├── docker/
│   ├── web/
│   │   └── Dockerfile
│   ├── worker/
│   │   └── Dockerfile
│   └── nginx/
│       ├── Dockerfile
│       └── nginx.conf
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── extensions.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── pool.py
│   │   │   ├── model.py
│   │   │   ├── fields.py
│   │   │   ├── query_builder.py
│   │   │   └── pagination.py
│   │   ├── security/
│   │   │   ├── __init__.py
│   │   │   ├── csrf.py
│   │   │   ├── rate_limit.py
│   │   │   ├── headers.py
│   │   │   ├── sessions.py
│   │   │   └── permissions.py
│   │   ├── validation/
│   │   │   ├── __init__.py
│   │   │   └── validators.py
│   │   ├── ws/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py
│   │   │   └── pubsub.py
│   │   ├── audit/
│   │   │   ├── __init__.py
│   │   │   └── logger.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── hashing.py
│   │       ├── mimetypes.py
│   │       └── files.py
│   │
│   ├── features/
│   │   ├── __init__.py
│   │   │
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   ├── repositories.py
│   │   │   └── forms.py
│   │   │
│   │   ├── rbac/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   ├── repositories.py
│   │   │   └── permissions.py
│   │   │
│   │   ├── cases/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   ├── repositories.py
│   │   │   ├── forms.py
│   │   │   └── permissions.py
│   │   │
│   │   ├── evidence/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   ├── repositories.py
│   │   │   ├── forms.py
│   │   │   └── permissions.py
│   │   │
│   │   ├── analysis/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   ├── repositories.py
│   │   │   ├── templates_registry.py
│   │   │   └── permissions.py
│   │   │
│   │   ├── notes/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   ├── repositories.py
│   │   │   └── forms.py
│   │   │
│   │   ├── reports/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   ├── repositories.py
│   │   │   └── forms.py
│   │   │
│   │   └── audit/
│   │       ├── __init__.py
│   │       ├── models.py
│   │       ├── routes.py
│   │       ├── services.py
│   │       └── repositories.py
│   │
│   ├── templates/
│   │   ├── layouts/
│   │   │   ├── base.html
│   │   │   ├── auth.html
│   │   │   └── dashboard.html
│   │   │
│   │   ├── macros/
│   │   │   ├── buttons.html
│   │   │   ├── forms.html
│   │   │   ├── alerts.html
│   │   │   ├── pagination.html
│   │   │   └── csrf.html
│   │   │
│   │   ├── components/
│   │   │   ├── navbar.html
│   │   │   ├── sidebar.html
│   │   │   ├── case_card.html
│   │   │   ├── evidence_row.html
│   │   │   ├── modal.html
│   │   │   └── activity_feed.html
│   │   │
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── register.html
│   │   │
│   │   ├── cases/
│   │   │   ├── list.html
│   │   │   ├── detail.html
│   │   │   ├── create.html
│   │   │   └── edit.html
│   │   │
│   │   ├── evidence/
│   │   │   ├── list.html
│   │   │   ├── detail.html
│   │   │   └── upload.html
│   │   │
│   │   ├── analysis/
│   │   │   ├── job_list.html
│   │   │   └── job_detail.html
│   │   │
│   │   ├── notes/
│   │   │   └── list.html
│   │   │
│   │   ├── reports/
│   │   │   ├── list.html
│   │   │   └── editor.html
│   │   │
│   │   ├── rbac/
│   │   │   └── roles.html
│   │   │
│   │   └── dashboard/
│   │       └── index.html
│   │
│   └── static/
│       ├── css/
│       │   ├── base.css
│       │   ├── components.css
│       │   └── pages/
│       ├── js/
│       │   ├── ws_client.js
│       │   ├── case_activity.js
│       │   ├── evidence_upload.js
│       │   └── csrf.js
│       └── img/
│
├── schema/
│   ├── 0001_create_users_roles_permissions.sql
│   ├── 0002_create_cases.sql
│   ├── 0003_create_evidence.sql
│   ├── 0004_create_analysis_tables.sql
│   ├── 0005_create_notes_reports.sql
│   └── 0006_create_audit_logs.sql
│
├── workers/
│   ├── __init__.py
│   ├── worker_main.py
│   ├── job_runner.py
│   └── analyzers/
│       ├── __init__.py
│       ├── base.py
│       ├── strings_analyzer.py
│       ├── exiftool_analyzer.py
│       ├── binwalk_analyzer.py
│       ├── hash_analyzer.py
│       └── file_type_analyzer.py
│
├── storage/
│   ├── evidence/
│   └── outputs/
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── core/
    │   ├── test_pagination.py
    │   ├── test_csrf.py
    │   └── test_rate_limit.py
    └── features/
        ├── auth/
        ├── rbac/
        ├── cases/
        ├── evidence/
        ├── analysis/
        ├── notes/
        └── reports/
```

---

## C. 4-Week Roadmap

This compresses the original 7-phase plan into 4 weekly milestones, each ending with something runnable. By the end of week 4 there is a working MVP slice: register → login → create case → upload evidence → run an analyzer → watch live logs over WebSocket → see results → add a note.

### Week 1 — Foundation: Platform, Database, Data-Access Layer

**Goal**: a running Dockerized Quart app behind nginx, connected to MySQL and Redis, with the first slice of the custom ORM (`Model`, `Field`, `QueryBuilder`) proven on a single table.

Deliverables:
- Docker Compose with nginx, web (Quart/uvicorn), mysql, redis containers; worker container scaffolded but idle.
- nginx config proxying `/` to the web app, `/static` to static files, `/ws/` reserved for week 4.
- Quart app factory (`app/main.py`, `app/config.py`) loading configuration from environment variables (`.env` / `.env.example`).
- `core/db/pool.py` — custom connection pool over the raw MySQL driver, verified with a simple health-check query.
- `schema/0001_create_users_roles_permissions.sql` applied manually against MySQL as the first table.
- `core/db/fields.py` and `core/db/model.py` — first version of `Field` descriptors and the `Model` base class (`find`, `where`, `save`, `delete`), demonstrated against one trivial table.
- Base layout templates (`layouts/base.html`, `components/navbar.html`) and a placeholder dashboard page proving Jinja rendering end-to-end.
- `core/security/headers.py` security-headers middleware applied globally from the start.

Backlog: anything beyond a working skeleton — no real features yet.

### Week 2 — Auth, RBAC, and Security Middleware

**Goal**: users can register/login/logout, sessions are Redis-backed, RBAC tables exist and gate at least one route, and CSRF + rate limiting are wired in.

Deliverables:
- `schema/` SQL for `users`, `roles`, `permissions`, `role_permissions`, `user_roles`, applied manually.
- `features/auth`: register, login, logout — routes, services, repositories; password hashing via a small wrapper (e.g. argon2/bcrypt).
- Redis-backed session handling (`core/security/sessions.py`): login sets session, logout clears it.
- CSRF middleware (`core/security/csrf.py`) applied to all POST forms (including login/register), with `macros/csrf.html` rendering the hidden token field.
- Rate limiting (`core/security/rate_limit.py`) applied first to `/auth/login` and `/auth/register`.
- `features/rbac`: roles/permissions repositories, `permission_required(...)` decorator in `core/security/permissions.py`, and a seed step granting an `admin` role full permissions and assigning it to a bootstrap user.
- A protected `/dashboard` route requiring login, demonstrating the permission decorator.
- Audit logging skeleton (`features/audit` + `core/audit/logger.py`): records login/logout/register events in `audit_logs` (schema included).

Backlog: social login, 2FA, passkeys — explicitly deferred.

### Week 3 — Case Management, Evidence Upload, and Pagination

**Goal**: authenticated users with the right permissions can create/list/view cases, and upload evidence into a case with hashing and metadata; pagination is implemented and reused.

Deliverables:
- `schema/` SQL for `cases`, `case_members`, `evidence`, applied manually.
- `features/cases`: create/list/view/edit routes, services, repositories — gated by `case.view`/`case.create` via the RBAC decorator.
- `core/db/pagination.py` — shared limit/offset pagination helper; `macros/pagination.html` renders page-number controls; case list page uses both.
- `features/evidence`: multipart upload route, file saved to `storage/evidence/<case_id>/<evidence_id>/`, SHA256 hashing (`core/utils/hashing.py`), mime-type detection (`core/utils/mimetypes.py`), metadata stored in `evidence`.
- Evidence list (within case detail) and evidence detail pages, using the pagination macro where relevant.
- Custom validation (`core/validation/validators.py` `Form` base class + feature `forms.py`, reusing `Field` descriptors from `core/db/fields.py`) for case creation and evidence upload (filename/size checks).
- `core/db/query_builder.py` extended as needed for case-list filtering/ordering beyond what `Model.where()` covers, still fully parameterized.
- Audit logging extended to case creation/edit and evidence upload.
- `components/case_card.html` and `components/evidence_row.html` built and used on list pages — first real use of the components convention.

Backlog: case tags, evidence tags, chain-of-custody log, evidence preview rendering.

### Week 4 — Realtime WebSocket, First Analysis Job, and Notes

**Goal**: a working MVP slice — case activity has live updates over WebSocket, at least one approved analyzer runs via the worker with live status streamed, and basic case notes exist.

Deliverables:
- `/ws/cases/<case_id>` WebSocket route (`core/ws/manager.py` tracks connected clients per case).
- Redis pub/sub bridge (`core/ws/pubsub.py`): publishing helper used by routes/worker; subscriber loop pushes messages to connected clients for that case.
- `static/js/ws_client.js` + `components/activity_feed.html`: browser connects to the case WebSocket and appends incoming events to a live feed on the case detail page.
- `schema/` SQL for `analysis_jobs`, `analysis_results`, and (if time allows) `artifacts`.
- `features/analysis`: approved-analyzer registry (`templates_registry.py`) with 1–2 analyzers (e.g. hash calc and `strings`); "run analyzer" route creates an `analysis_jobs` row and enqueues work via a simple Redis list (no Celery needed for MVP).
- `workers/worker_main.py` + `job_runner.py` + `analyzers/hash_analyzer.py` (and optionally `strings_analyzer.py`): worker picks up queued jobs, runs the approved tool with a timeout, writes results to `analysis_results`, and publishes progress/log lines via Redis pub/sub to the case channel.
- `schema/` SQL for `notes`; `features/notes`: minimal case notes — create/list, rendered on case detail page.
- End-to-end MVP smoke test through `http://localhost`: register → login → create case → upload evidence → run hash analyzer → watch live log via WebSocket → see result → add a note.

Backlog (explicitly pushed beyond week 4): reports/report editor and export, exiftool/binwalk/tshark/audio analyzers, timeline events, report versions, evidence/case tags, `api_keys`, refined sessions table, social login/2FA/passkeys, sliding-window rate limiting, full test suite (smoke tests only by week 4).

---

## D. Security Checklist Mapping

- **RBAC (roles & permissions enforcement)** — `app/features/rbac/` repositories + `core/security/permissions.py` `permission_required` decorator, applied to routes in `cases`, `evidence`, `analysis`, `reports`, `rbac`. Tables `roles`, `permissions`, `role_permissions`, `user_roles` created in week 2.

- **Rate limiting** — `core/security/rate_limit.py`, Redis-backed counters as a `before_request` hook and/or route decorator. Applied to `/auth/login`, `/auth/register` from week 2; extended to evidence upload and analysis-run routes by week 4.

- **SQL injection prevention** — enforced structurally by the custom ORM: `core/db/model.py` and `core/db/query_builder.py` are the only places SQL is composed, table/column names come exclusively from each `Model`'s declared `Field` attributes (a closed whitelist), and all values are passed to the driver as `%s` parameters — never interpolated into the SQL string. No feature code (`repositories.py`) builds raw SQL by hand; this convention is a hard rule for every feature.

- **CSRF protection** — `core/security/csrf.py` generates and validates per-session signed tokens; `templates/macros/csrf.html` renders the hidden field in every form; validation runs on all state-changing requests (POST/PUT/PATCH/DELETE) from week 2.

- **Security headers** — `core/security/headers.py` `after_request` hook sets CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, HSTS — applied globally from week 1.

- **Audit logging** — `features/audit/` + `core/audit/logger.py` write to `audit_logs` for auth events (week 2), case/evidence events (week 3), and analysis job events (week 4) — covers "log every analysis action."

- **Session security** — `core/security/sessions.py`, Redis-backed server-side sessions; cookies are `HttpOnly`/`Secure`/`SameSite`; the session id is the only client-side artifact, so sessions can be invalidated centrally.

- **Input validation** — `core/validation/validators.py` `Form` base class + per-feature `forms.py`, built on the shared `Field` descriptors from `core/db/fields.py`; validates case creation, evidence upload metadata (filename, declared size/type), and analysis job parameters before they reach the repository layer.

- **Evidence handling safety**:
  - *Never execute uploaded files* — `storage/evidence/` files are only ever passed as input arguments to approved analyzers in `workers/analyzers/`, never executed or used to build shell commands directly.
  - *Approved analyzer templates only* — `features/analysis/templates_registry.py` is the single source of allowed tools/commands; `workers/job_runner.py` only dispatches jobs matching a registered template — no arbitrary command strings from user input.
  - *Timeouts on tool execution* — `workers/analyzers/base.py` enforces a per-analyzer timeout around each subprocess call.
  - *Hash all uploads* — `core/utils/hashing.py` computes SHA256 at upload time in `features/evidence/services.py`, stored in `evidence.sha256`.
  - *Separate evidence from generated output* — `storage/evidence/` (read-only originals) vs `storage/outputs/` (worker-generated artifacts), enforced by path conventions in `core/utils/files.py`.

---

## Critical Files to Create First

When implementation begins, these are the highest-priority files, in rough build order:

1. `docker-compose.yml`
2. `app/main.py`
3. `app/core/db/pool.py`
4. `app/core/db/fields.py` and `app/core/db/model.py`
5. `app/core/db/query_builder.py`
6. `app/core/validation/validators.py`
7. `app/core/security/csrf.py`
8. `app/core/ws/manager.py` and `app/core/ws/pubsub.py`
