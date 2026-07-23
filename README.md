# NirikshanOS

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/tests-57%20passing-2ea44f)

**NirikshanOS** is a browser-based Digital Forensics & Incident Response (DFIR) case management platform. It lets forensic teams create cases, upload and hash evidence, run real forensic analysis tools against that evidence in isolated containers, and build investigation reports and timelines — all from a single web workspace, with full audit logging and organization-level access control throughout.

## Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Setup](#setup)
- [Testing](#testing)

---

## Features

### Case Management
- Create, edit, and delete cases, with classification, severity, and status tracking (open/active/closed/archived) alongside a separate forensic examination status
- Row-level case visibility — an organization owner sees every case, while other members only see cases they created or were explicitly added to
- Per-case members, a shared notes scratchpad, and a full activity audit trail

### Evidence Handling
- Chunked, resumable evidence uploads streamed directly to S3-compatible storage (MinIO), with pause/resume/retry that survives a dropped connection
- Automatic SHA-256/MD5 hashing for chain-of-custody integrity

### Forensic Analysis
- A tiered container system (light/medium/heavy/full instances) that runs real forensic tools — ExifTool, Sleuthkit, Volatility3, Plaso, capa, FLOSS, YARA, tshark, foremost, and more — each in an isolated, ephemeral Docker container per job
- An in-browser module IDE for authoring analysis modules: YAML-based tool definitions, multi-step pipelines, configurable options, and a real sandboxed test-run feature against sample files
- Raw, unmodified stdout/stderr captured and shown per module — no lossy parsing layer
- Module access gated by subscription plan/tier, enforced independently on the server regardless of what the interface displays

### Reporting & Timeline
- A markdown-based investigation report builder per case, with saved findings and IOCs insertable directly into the draft, and a persistent record of what has already been inserted
- A dedicated per-case investigation timeline — tasks, notes, and milestones, each with their own date and description, built up by the analyst over the life of the case

### Organizations & Access Control
- Organization onboarding with an admin approval workflow (pending/approved/rejected) and government-document verification
- Role-based access control at both the system level (platform staff) and the organization level (custom roles/permissions per org), kept as fully separate, independently managed scopes
- Staff management, invite codes, and org profile management

### Billing & Subscriptions
- Tiered subscription plans (Free/Basic/Pro/Enterprise) gating which module tiers and container instances an organization can run
- Real payment processing via eSewa, with HMAC-signed callbacks and an independent server-to-server status check
- Coupon codes, per-organization discounts, automatic free-plan assignment on organization creation, plan-switch confirmation flow, and an admin transaction ledger

### Dashboards
- A role-aware dashboard: System Admins see platform-wide analytics (user/org growth, revenue trends, platform traffic, popular modules and plans); organization members see a scoped view (their cases, org members, subscription status, recent activity) shaped by their actual permissions
- Dependency-free bar, line, and pie/donut charts built with plain CSS and SVG — no charting library required

### Security
- Argon2id password hashing, server-side sessions stored in MySQL (not Redis — a stolen session token is meaningless without the matching database row, and revoking one takes effect on the very next request)
- Two-factor authentication (TOTP) with Argon2-hashed backup codes, plus Google and GitHub OAuth login
- Double-submit cookie CSRF protection and Redis-backed rate limiting
- Full audit logging of case, evidence, notes, report, and organization activity
- Strict Content-Security-Policy throughout; jsDelivr is permitted only for Tailwind's browser compiler, while application scripts remain same-origin
- Untrusted forensic tools run in a locked-down container with no Docker socket, dropped capabilities, a read-only evidence mount, and guaranteed teardown after every job

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Flask (WSGI, served by Gunicorn) with a persistent asynchronous data/worker layer |
| Frontend | Server-rendered Jinja2 + Tailwind's browser compiler — no Node install or build step |
| Database | MySQL 8, migrated via a flat sequence of SQL files in `migrations/` |
| Cache / Rate limiting | Redis |
| Object storage | MinIO (S3-compatible), for evidence uploads |
| Forensic execution | Ephemeral, isolated Docker containers per analysis job (light/medium/heavy/full tiers) |
| Reverse proxy | nginx |
| Testing | pytest (unit/functional/integration/security) + Playwright (end-to-end) |

---

## Setup

### Prerequisites
- Docker and Docker Compose

### 1. Configure environment
```bash
cp .env.example .env
```
The defaults in `.env.example` work as-is for local development, including a working eSewa sandbox key. `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`, and `RESEND_API_KEY` are optional — leave them blank to skip OAuth login and have outgoing email print to stdout instead of actually sending.

### 2. Start the stack
```bash
docker compose up --build
```
This builds and starts `nginx`, `web`, `worker`, `mysql`, `redis`, and `minio`, and runs the one-shot `migrate` service (applying every file in `migrations/`) before `web` is allowed to start. Once it's up, the app is at **http://localhost**.

### 3. Create a System Admin account
```bash
docker compose exec web python3 seed.py
```
Creates (or reuses, if it already exists) a dev System Admin account — logs in with `deadeye@gmail.com` / `deadeye@123` (change these constants at the top of `seed.py` before using this anywhere other people can reach it).

### 4. (Optional) Enable real forensic analysis
The four analyzer container images are a separate, `build-only` Compose profile — not built by step 2, since they're only needed once you actually want to run analysis jobs:
```bash
docker compose --profile build-only build analyzer-base analyzer-light analyzer-medium analyzer-heavy analyzer-full
```
Then populate a real, working module catalogue, the four analyzer instances, and the four subscription plans in one go:
```bash
docker compose exec web python3 seed_catalog.py
```
Each instance is seeded with `image_status: unknown` until something actually confirms the image was built — as the System Admin, open **Admin → Instances** and click **Recheck** on each of the four instances to flip them to `ready` (modules assigned to an instance that isn't `ready` are correctly refused at analysis time, not just hidden in the UI).

---

## Testing

The project ships a 57-test automated suite spanning unit, functional, integration, security, and end-to-end tiers, run against a disposable database and an isolated Redis keyspace so it can never touch real data:

```bash
python3 tests/run_all.py
```

This provisions the test database from every migration file, runs the backend tiers inside the `web` container, runs the end-to-end tier from the host against the live stack, and prints one consolidated pass/fail summary.
