# DFIR Platform — AI Agent Build Context

## 1. Project Goal

Build a browser-based **Digital Forensics and Incident Response platform** using:

* Flask
* Python
* Jinja
* HTML
* CSS
* JavaScript
* MySQL
* Redis
* Nginx
* Docker Compose

The platform should allow users to create forensic cases, upload evidence, run analyzers, view live tool output, manage notes, and generate reports.

This is not a React/Next.js project. Keep everything server-rendered with Flask + Jinja and enhance pages using plain JavaScript.

---

## 2. Core Architecture

Use **MVC with feature-first architecture**.

Each feature should contain its own:

* `models.py`
* `routes.py`
* `services.py`
* `repositories.py`
* optional `forms.py`
* optional `permissions.py`

Example:

```txt
app/features/cases/
├── models.py
├── routes.py
├── services.py
├── repositories.py
└── permissions.py
```

Avoid dumping all routes, models, and logic into global files.

---

## 3. Main Docker Architecture

Use separate containers:

```txt
nginx     → public entrypoint
web       → Flask application
worker    → background analysis jobs
mysql     → database
redis     → WebSocket pub/sub and job queue
```

The browser should access only:

```txt
http://localhost
```

Do not expose Flask directly with `localhost:5000` or `localhost:8000`.

Nginx should proxy:

```txt
/       → Flask web app
/ws/*   → Flask WebSocket endpoints
/static → static files
```

The Flask app must run with local mount:

```yaml
volumes:
  - .:/app
```

This allows live local development.

---

## 4. Realtime Requirement

Use **pure WebSocket only**.

Do not use:

* SSE
* long polling
* Socket.IO

Use raw WebSocket routes such as:

```txt
/ws/cases/<case_id>
```

Realtime flow:

```txt
worker / Flask route
→ Redis pub/sub
→ Flask WebSocket
→ browser JavaScript
```

Use WebSocket for:

* live analyzer logs
* job status updates
* case activity updates
* report collaboration later
* evidence processing progress

---

## 5. Core Features

### Auth

Required:

* login
* register
* logout
* password hashing
* session handling
* user roles
* social login
* 2FA
* passkeys

---

### RBAC

Use Discord-like role system.

Tables:

* `users`
* `roles`
* `permissions`
* `role_permissions`
* `user_roles`

Example permissions:

* `case.view`
* `case.create`
* `case.delete`
* `evidence.upload`
* `analysis.run`
* `report.export`
* `roles.manage`
* `admin.access`

---

### Cases

Everything belongs to a case.

A case should contain:

* evidence files
* notes
* analysis jobs
* results
* artifacts
* reports
* collaborators
* timeline
* audit logs

Basic case fields:

* title
* description
* status
* created_by
* created_at
* updated_at

---

### Evidence

Evidence means uploaded forensic files.

Required:

* upload file
* store original file
* calculate hash
* identify file type
* store metadata
* link evidence to case

Evidence fields:

* case_id
* filename
* original_filename
* file_path
* mime_type
* size
* sha256
* status
* uploaded_by
* created_at

---

### Analysis

Analysis should run through background workers, not directly inside request routes.

Basic flow:

```txt
User clicks analyzer
→ create analysis job
→ worker runs tool
→ output saved
→ Redis publishes live logs
→ browser receives logs through WebSocket
```

Analyzer examples:

* strings
* exiftool
* binwalk
* tshark summary
* audio spectrogram
* file command
* hash calculation

Use approved analyzer templates. Do not allow arbitrary shell commands from users.

---

### Reports

Reports are linked to cases.

Required:

* create report
* edit report
* save report content
* include evidence findings
* export later to PDF/HTML

Report fields:

* case_id
* title
* content
* status
* created_by
* created_at
* updated_at

---

### Notes

Notes should be simple at first.

Required:

* case notes
* evidence notes
* analyzer result notes

Later:

* version history
* collaborative editing
* pinned notes

---

## 7. Database Tables

Minimum MVP tables:

```txt
users
roles
permissions
role_permissions
user_roles

cases
case_members

evidence
analysis_jobs
analysis_results
artifacts

notes
reports
audit_logs
```

Later:

```txt
templates
job_logs
timeline_events
report_versions
evidence_tags
case_tags
api_keys
sessions
```

---

## 8. Important Development Rules

Do not change the stack.

Use:

* Flask for backend
* Jinja for templates
* plain JavaScript for frontend behavior
* MySQL for database
* Redis for pub/sub and queues
* Nginx as reverse proxy
* Docker Compose for local setup

Do not use:

* React
* Next.js
* FastAPI
* PostgreSQL
* SSE
* Socket.IO
* arbitrary shell command execution

---

## 9. Security Rules

Forensic files can be malicious, so follow these rules:

* never execute uploaded files directly
* run analyzers through approved templates
* log every analysis action
* use timeouts for tool execution
* store original evidence safely
* hash every uploaded file
* restrict analyzer access through permissions
* do not allow user-controlled raw shell commands
* separate uploaded evidence from generated output

---

## 10. MVP Build Order

### Phase 1 — Base Platform

Build:

* Docker Compose
* Nginx proxy
* Flask app factory
* MySQL connection
* Redis connection
* base layout
* dashboard page

---

### Phase 2 — Auth and RBAC

Build:

* user model
* login
* register
* logout
* role model
* permission model
* permission decorators

---

### Phase 3 — Case Management

Build:

* create case
* list cases
* view case
* edit case
* case members
* basic audit logs

---

### Phase 4 — Evidence Upload

Build:

* upload evidence
* save file to storage
* calculate SHA256
* detect file size/type
* list evidence inside case
* evidence detail page

---

### Phase 5 — Realtime WebSocket

Build:

* `/ws/cases/<case_id>`
* Redis pub/sub
* browser WebSocket client
* live case event log panel

---

### Phase 6 — Analysis Jobs

Build:

* analysis job model
* worker container
* job queue
* demo analyzer
* live analyzer logs
* save analysis result

---

### Phase 7 — Reports and Notes

Build:

* case notes
* report editor
* save report
* attach analysis results to report
* basic HTML export

---

## 11. Target MVP

The MVP is complete when the user can:

1. register and login
2. create a forensic case
3. upload evidence to the case
4. run a basic analyzer
5. see live analyzer logs through WebSocket
6. save results
7. write notes
8. create a simple case report
9. access everything through `http://localhost`
10. run the full system using Docker Compose

---

## 12. Final Product Vision

The final platform should become a complete browser-based DFIR workspace with:

* case management
* evidence management
* forensic analyzers
* live job output
* artifact extraction
* timeline generation
* role-based access
* report generation
* audit logs
* plugin-based analyzer system
* safe containerized tool execution

more details: 
This is a strong idea. What you are describing is basically an **all-in-one DFIR / forensics OS in the browser**: upload or connect evidence, run analyzers, save artifacts, write reports, and collaborate in a lab workspace.

A good way to build it is to split it into **core platform + analysis engines + lab/reporting**.

## Core platform

**1) Authentication and RBAC**
Use:

* social login
* normal user / admin
* custom roles like Discord
* permissions such as:

  * upload evidence
  * run analyzer
  * export report
  * manage roles
  * manage templates
  * delete case
  * view sensitive artifacts

A practical model is:

* **User**
* **Role**
* **Permission**
* **RolePermission**
* **UserRole**

Admins can create roles and assign permissions per workspace or globally.

**2) Case-based workflow**
Everything should live inside a **case**:

* evidence files
* notes
* command history
* tool outputs
* extracted artifacts
* timelines
* reports
* screenshots
* tags
* collaborators

That makes the system feel like a real DFIR platform instead of just a tool collection.

**3) Evidence storage**
For large files, use a hybrid approach:

* **client-side preview / light parsing**
* **server-side storage for originals and outputs**
* chunked upload for big files
* object storage for evidence
* database for metadata and results

Recommended storage split:

* raw files → object storage
* parsed metadata → PostgreSQL
* jobs and queue → Redis / RabbitMQ
* logs and outputs → PostgreSQL or object storage depending on size

**4) Job system**
Analysis should run as background jobs:

* upload file
* choose analyzer
* queue job
* worker executes tool/template
* save output
* show result in UI

This is essential for:

* large files
* long-running analysis
* repeatable automation

---

## Analysis modules

Organize the app by evidence type:

**File forensics**

* binwalk
* strings
* hexdump
* entropy
* file carving
* embedded object detection

**Image forensics**

* exiftool
* metadata extraction
* thumbnail analysis
* hash comparison
* stego checks

**Audio forensics**

* spectrogram
* waveform view
* DTMF detection
* SSTV decoder
* frequency separation
* silence detection
* voice artifact inspection

**PCAP / network forensics**

* protocol summary
* DNS/HTTP/TLS extraction
* session reconstruction
* file carving from traffic
* suspicious host detection

**Email forensics**

* header parsing
* MIME structure
* attachments
* URLs
* sender spoof checks
* timeline extraction

**Memory forensics**

* process list
* DLLs/modules
* sockets
* command history
* strings scan
* suspicious regions

**Disk / storage forensics**

* partitions
* deleted files
* filesystem metadata
* MFT / inode analysis
* timeline generation

**Windows/Linux artifact forensics**

* event logs
* registry
* shell history
* auth logs
* cron/systemd traces
* browser artifacts

**Malware static analysis**

* hash
* strings
* imports/exports
* sections
* packer hints
* YARA scan
* PE triage

**Database forensics**

* SQLite
* WAL / journal
* MySQL logs
* PostgreSQL WAL
* Redis snapshots

---

## Auto-analysis pipeline

This is one of the best features.

When a file is uploaded, the system can do:

1. **file identification**
2. **hashing**
3. **metadata extraction**
4. **entropy scan**
5. **signature check**
6. **type-specific analyzer**
7. **IOC extraction**
8. **timeline/artifact generation**
9. **summary creation**
10. **report draft**

For example:

* email uploaded → parse headers, attachments, URLs, sender chain, suspicious domains
* audio uploaded → waveform, spectrogram, DTMF, SSTV, frequency peaks
* pcap uploaded → host map, conversations, DNS, HTTP objects, files
* image uploaded → EXIF, hidden data, thumbnails, hashes
* binary uploaded → strings, imports, sections, YARA, entropy

This can work like a **forensic triage engine**.

---

## Lab / split-screen mode

This is a great differentiator.

Use a layout like:

* left: evidence browser / outputs / tools
* right: notes / report editor / command runner / timeline

Features:

* drag and drop evidence into the lab
* pin important artifacts
* write notes beside findings
* copy command output into report
* save screenshots
* compare multiple analyzers side by side

This makes it feel like a proper investigation workspace.

---

## Script and command templates

This should be handled as **approved templates**, not free-form dangerous execution.

Example:

* “Run exiftool”
* “Run binwalk”
* “Run strings + grep”
* “Run tshark summary”
* “Run audio spectrogram”
* “Run YARA scan”

Each template can define:

* command
* required input type
* output parser
* tags
* permission needed
* timeout
* allowed arguments

This gives you safe automation without chaos.

A good model is:

* user drags a template into a case
* system asks for parameters
* worker executes it in sandbox
* result gets saved automatically

---

## Suggested architecture

### Frontend

* React / Next.js
* Split screen lab UI
* file previewers
* timeline view
* artifact panels
* report editor
* role management dashboard

### Backend API

* Python FastAPI or Quart
* auth
* RBAC
* case management
* upload handling
* job orchestration
* report saving

### Workers

Separate worker services for:

* file analysis
* audio analysis
* pcap analysis
* malware triage
* parsing and extraction

### Storage

* PostgreSQL for metadata
* S3-compatible storage for files
* Redis for jobs/cache
* optional Elasticsearch/OpenSearch for searching artifacts

### Sandbox

Run tools in isolated containers:

* no direct host access
* per-job resource limits
* timeout
* read-only inputs
* controlled outputs

That matters a lot because forensic inputs can be malicious.

---

## Data model idea

At minimum:

* `users`
* `roles`
* `permissions`
* `role_permissions`
* `user_roles`
* `cases`
* `case_members`
* `evidence`
* `analysis_jobs`
* `analysis_results`
* `artifacts`
* `notes`
* `reports`
* `templates`
* `job_logs`
* `audit_logs`

This gives you traceability, which is very important in DFIR.

---

## Features worth adding early

These are high-value:

* hash all files automatically
* auto-tag evidence by type
* artifact search across cases
* timeline builder
* export report to PDF/HTML
* audit log for every action
* versioning for notes and reports
* evidence chain-of-custody log

---

## A realistic MVP

Do not try to build everything first. Start with:

**MVP v1**

* login
* cases
* upload files
* evidence storage
* simple RBAC
* notes
* report editor
* 5 analyzers:

  * exiftool
  * strings
  * binwalk
  * tshark summary
  * audio spectrogram

**MVP v2**

* template-based execution
* auto-analysis pipeline
* job queue
* search
* timeline
* export reports

**MVP v3**

* memory/disk/windows artifacts
* malware static analysis
* advanced permissions
* collaboration
* lab split screen
* plugin system

---

## Best design choice for the plugin system

Make every tool a plugin with a manifest like:

* name
* supported input types
* command
* output schema
* required permissions
* UI widget type

That way, adding a new analyzer later is easy.

---

## One important caution

A platform like this can become unsafe if you let users run arbitrary shell commands directly. Keep command execution:

* sandboxed
* permission-controlled
* template-based
* logged
* resource-limited

---

If you want, I can turn this into a **full system architecture document** with:

1. module diagram
2. database schema
3. role/permission matrix
4. MVP feature list
5. API endpoint list
6. folder structure for the project
