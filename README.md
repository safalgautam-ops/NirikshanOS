# NirikshanOS

**NirikshanOS** is a browser-based Digital Forensics & Incident Response (DFIR) case management platform. It lets forensic teams create cases, upload and hash evidence, run real forensic analysis tools against that evidence in isolated containers, and build investigation reports — all from a single web workspace, with full audit logging and organization-level access control throughout.

## Features

### Case Management
- Create, edit, and delete cases, with classification, severity, and status tracking (open/active/closed/archived) alongside a separate forensic examination status
- Row-level case visibility — an organization owner sees every case, while other members only see cases they created or were explicitly added to
- Per-case members, activity audit trail, and a notes section

### Evidence Handling
- Chunked, resumable evidence uploads streamed directly to S3-compatible storage (MinIO)
- Automatic SHA-256/MD5 hashing for chain-of-custody integrity

### Forensic Analysis
- A tiered container system (light/medium/heavy/full instances) that runs real forensic tools — ExifTool, Sleuthkit, Volatility3, Plaso, capa, foremost/scalpel, and more — each in an isolated, ephemeral Docker container per job
- An in-browser module IDE for authoring analysis modules: YAML-based tool definitions, multi-step pipelines, configurable options, and a real sandboxed test-run feature against sample files
- Raw, unmodified stdout/stderr captured and shown per module — no lossy parsing layer
- Module access gated by subscription plan/tier, with admin tooling to edit, test, or delete modules

### Reporting & Timeline
- A markdown-based investigation report builder per case, with saved findings, IOCs, and timeline events insertable directly into the draft
- A dedicated case timeline view for chronological incident reconstruction

### Organizations & Access Control
- Organization onboarding with an admin approval workflow (pending/approved/rejected) and government-document verification
- Discord-style role-based access control at both the system level (platform staff) and the organization level (custom roles/permissions per org), kept as fully separate scopes
- Staff management, invite codes, and org profile management

### Billing & Subscriptions
- Tiered subscription plans (Free/Basic/Pro/Enterprise) gating which module tiers and container instances an organization can run
- Real payment processing via eSewa, with coupon codes and per-organization discounts
- Automatic free-plan assignment on organization creation, plan-switch confirmation flow, and an admin transaction ledger

### Dashboards
- A role-aware dashboard: System Admins see platform-wide analytics (user/org growth, revenue trends, platform traffic, popular modules and plans); organization members see a scoped view (their cases, org members, subscription status, recent activity) shaped by their actual permissions
- Dependency-free bar, line, and pie/donut charts built with plain CSS and SVG — no charting library required

### Security
- Argon2id password hashing, server-side Redis-backed sessions, CSRF protection, and rate limiting
- Two-factor authentication (TOTP) and WebAuthn support
- Full audit logging of case, evidence, and organization actions
- Strict Content-Security-Policy throughout, including a CSP-safe (no `unsafe-eval`) Alpine.js build

---

*This README covers the project's purpose and current feature set only. A complete README — including setup, architecture, and configuration instructions — will follow.*
