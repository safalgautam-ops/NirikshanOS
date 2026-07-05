Build the DFIR case workspace UI exactly based on my wireframe concept.

This is for a forensic investigation platform called **Nirikshan OS**. The UI must be professional, clean, minimal, and case-based. Do not make it look like a random terminal wrapper. The workflow is:

Evidence upload → choose compatible modules → review/run analysis → progress drawer → result canvas → save IOC/finding → report tab.

Use realistic data structures, reusable components, and module registry data. Do not hardcode only one fake example everywhere. Use arrays/objects so later backend data can replace the mock data easily.

Main layout:

* Left sidebar
* Top search bar
* Main content area
* Case workspace tabs

Sidebar sections:

Platform:

* Dashboard
* Organization
* Staff
* Roles

Application:

* Case
* Timeline
* Billing

Case workspace tabs:

* Overview
* Evidences
* Results
* Report
* Members
* Activity

The important pages/components to build:

1. **Evidences Tab**
2. **Analyze Evidence Page**
3. **Analysis Progress Drawer/Page**
4. **Results Tab**
5. **Result Canvas**
6. **Raw Output Dialog/Drawer**
7. **Report Tab**

Use clean card borders, simple spacing, professional typography, and a structured forensic UI.

---

## 1. Evidences Tab UI

Route concept:

`/cases/:caseId/evidences`

Purpose:

Show uploaded evidence files, metadata, hashes, file type, chain of custody, and action buttons.

Layout:

* Left sidebar remains visible
* Case tabs at top
* Page description:
  “Manage uploaded files, view metadata, hashes, file types, and chain of custody.”
* Evidence files shown as cards or rows.

Each evidence card should show:

* File name
* Detected file type
* MIME type
* Size
* SHA256
* Uploaded by
* Uploaded at
* Analysis status
* Completed module count
* Running module count
* Failed module count
* Buttons:

  * Download
  * Comment / Evidence Note
  * Analyze


Clicking **Analyze** should open the analyze page for that evidence:

`/cases/:caseId/evidences/:evidenceId/analyze`

---

## 2. Analyze Evidence Page

Route concept:

`/cases/:caseId/evidences/:evidenceId/analyze`

Page title should be dynamic:

`Choose Compatible Modules for {fileName}`

This page has two main panels:

Left panel: Compatible Modules
Right panel: Module Configuration

Top area:

* Evidence file name
* File type
* Size
* SHA256 short hash
* Back button

Left panel should list compatible modules based on file type.

Use a module registry 

Group modules visually by category:

* Basic Triage Bundle
* Standard Modules
* Advanced Modules
* Network Modules
* Email Modules
* Memory Modules

Only show categories that contain compatible modules for the selected evidence.

Locked modules:

* If user plan is Free and module tier is Analyst or Advanced, show lock icon.
* If user plan is Analyst and module tier is Advanced, show lock icon.
* Locked modules should still be visible but disabled.
* Clicking locked module opens upgrade dialog.

Right panel:

When a module is selected, show:

* Selected module name
* Description
* Required plan
* Runtime
* Estimated time
* Batchable yes/no
* Configuration options

Example options:

YARA Scan:

* Ruleset select:

  * Malware Rules
  * Suspicious Rules
  * Office Document Rules
  * Webshell Rules
* Scan mode:

  * Normal
  * Recursive
  * Strict
* Checkboxes:

  * Show matched strings
  * Extract IOCs

Strings Extraction:

* Minimum string length
* Encoding:

  * ASCII
  * Unicode
  * Both
* Checkboxes:

  * Extract URLs
  * Extract IPs
  * Extract emails

PCAP DNS Extraction:

* Include internal domains
* Extract suspicious domains
* Output unique domains only

Memory pslist:

* Symbol/profile mode
* Include process tree
* Extract command line if available

Bottom area:

Show selected analysis plan summary:

* Selected file
* Selected modules
* Number of module tasks
* Optimized container runs
* Estimated runtime
* Button: Next

---

## 3. Analysis Progress UI

After clicking Next/Analyze, show progress page or drawer.

Purpose:

Show jobs and module tasks.

Important concept:

Light modules can be grouped as one batch job.

Example:

Basic Triage Bundle runs in one container but contains many tasks:

* File Identification
* Hashing
* Metadata Extraction
* Strings Extraction
* Entropy Analysis

Standard/heavy modules can run separately:

* YARA Scan
* Capa
* Ghidra
* Volatility

Progress UI should show:

* Evidence file name
* Bundle/job name
* Module task
* Status
* Progress bar
* Action button

Wireframe content:

Analysis Progress
Evidence: unknown_payload.exe

Basic Triage Bundle

| Module Task         | Status    | Progress | Action |
| ------------------- | --------- | -------- | ------ |
| File Identification | Completed | 100%     | Delete |
| Hashing             | Running   | 60%      | Cancel |
| Metadata Extraction | Queued    | 0%       | Cancel |
| Strings Extraction  | Queued    | 0%       | Cancel |

Standard Module

| Module Task | Status | Progress | Action |
| ----------- | ------ | -------- | ------ |
| YARA Scan   | Queued | 0%       | Cancel |

Bottom button:

* Open Result Canvas

Status values:

* Queued
* Preparing
* Running
* Completed
* Failed
* Timeout
* Cancelled

---

## 4. Results Tab

Route concept:

`/cases/:caseId/results`

Purpose:

Case-wide result index. It should not show deep output. It only lists evidence files and result status.

Page description:

“Review analysis outputs, extracted artifacts, findings, and create analyst notes.”

Table columns:

* Evidence
* Type
* Completed
* Running
* Failed
* Last analyzed
* Actions

Mock result rows should come from evidence data and job data.

Actions:

* Open Canvas
* View Jobs
* Re-analyze

Clicking Open Canvas opens:

`/cases/:caseId/evidences/:evidenceId/results`

---

## 5. Result Canvas

Route concept:

`/cases/:caseId/evidences/:evidenceId/results`

This is the deep output page for one evidence file.

Layout should match the wireframe:

Three columns:

Left: Module Outputs
Center: Output Viewer
Right: Analyst Notes / Actions

Header:

* Evidence file name
* Re-analyze button
* Export button

Left column:

Module Outputs list should show modules for that evidence:

* Completed modules with check icon
* Running modules with spinner/status
* Not-run modules with empty circle
* Failed modules with warning icon

Example for PE evidence:

* File Identification
* Hashing
* Metadata Extraction
* Strings Extraction
* Entropy Analysis
* YARA Scan
* Capa
* FLOSS
* Ghidra Decompile
* Dynamic Malware Analysis

Do not hardcode only these; derive from compatible module registry and result data.

Center Output Viewer:

Keep it simple. Only two tabs:

* Overview
* Raw Output

Overview should contain:

* Module name
* Status
* Runtime
* Risk
* Summary
* Key Findings
* Extracted IOCs
* Artifacts


Raw Output tab:

Show managed terminal output, not messy.

Sections:

* stdout
* stderr
* execution details collapsed
* Copy button
* Download button

Right column:

Analyst Notes:

* Textarea
* Save Note button

Actions:

* Add Indicator
* Create Finding

Use clearer names:

* Add Indicator instead of Save as IOC
* Create Finding instead of Save Finding

Action behavior:

Add Indicator:

* Opens dialog to confirm IOC type, value, severity, confidence, source evidence, source module.
* Saves to case IOC list.
* It appears in:

  * Case Report tab
  * Sidebar IOCs page
  * Case Results IOC section if implemented

Create Finding:

* Opens dialog to create case-level finding with title, severity, confidence, description, source evidence, source module.
* Saves to case findings.
* It appears in:

  * Case Report tab
  * Sidebar Findings page
  * Dashboard findings count

Add to Timeline:

* Opens dialog to create timeline event from this result.
* Saves to case timeline.

Add to Report:

* Adds selected result/finding/IOC to current report draft if report exists.
* If no report exists, ask to create report draft first.

---

## 6. Raw Output Dialog/Drawer

Raw output can appear as a dialog or side drawer when user clicks Raw Output tab or View Raw.

Wireframe content:

Raw Output

Top buttons:

* Copy
* Download

Sections:

stdout:

* show monospace block
* line numbers optional
* wrap lines toggle

stderr:

* show “No errors” if empty

Execution details collapsed:

* Job ID
* Worker
* Runtime image
* Queue
* Isolation
* Network
* CPU limit
* Memory limit
* Timeout
* Exit code

Do not show raw command execution as editable. It is read-only.

---

## 7. Report Tab

Route concept:

`/cases/:caseId/report`

Purpose:

Build the final case report from saved findings, saved IOCs, timeline events, notes, and custom markdown text.

Important:

Use Markdown `.md`, not MD5. MD5 is a hash. The report should be stored as Markdown.

Report UI should have:

* Title
* Visibility selector
* Status
* Save Draft
* Preview
* Export PDF
* Export DOCX
* Submit for Review

Visibility options:

* Personal Draft
* Case Shared

Personal Draft:

* Only creator can view/edit.

Case Shared:

* Case members with permission can view.
* Editors/reviewers can comment/edit based on role.

Report statuses:

* Draft
* In Review
* Changes Requested
* Approved
* Final
* Exported

Report tab layout:

Left panel: Report Sections
Center panel: Markdown Report Editor
Right panel: Saved Items

Left Report Sections:

* Cover Page
* Executive Summary
* Scope
* Evidence Summary
* Timeline
* Key Findings
* Indicators of Compromise
* Recommendations
* Appendix

Center Editor:

Use a markdown editor or textarea placeholder for now.

The report content should be editable markdown.

Example markdown:

```md
# Network Intrusion Investigation Report

## Executive Summary

Write the executive summary here.

## Scope

- Case ID: CASE-2026-0012
- Category: Network Intrusion
- Severity: Critical

## Key Findings

Saved findings inserted here.

## Indicators of Compromise

Saved IOCs inserted here.

## Incident Timeline

Selected timeline events inserted here.

## Recommendations

Write recommendations here.

## Appendix

Supporting evidence and raw tool outputs are referenced here.
```

Right Saved Items panel:

Tabs or collapsible sections:

* Saved Findings
* Saved IOCs
* Timeline Events
* Evidence References
* Images / Artifacts

Keep this compact. Do not create too many tabs inside the editor.

Saved Findings section:

Show finding cards:

* Title
* Severity
* Confidence
* Source evidence
* Source module
* Insert button

Example:

Malware contacted suspicious external infrastructure
Severity: High
Confidence: Medium
Source: unknown_payload.exe → YARA Scan
Button: Insert into Report

Saved IOCs section:

Show IOC table:

* Type
* Value
* Severity
* Confidence
* Source
* Insert button

Example:

URL | http://malicious-update-check.example/payload | High | Medium | YARA Scan
IP | 185.20.10.44 | Medium | Medium | PCAP DNS Extraction

Timeline Events section:

Show event cards:

* Time
* Title
* Event type
* Source
* Insert button

When clicking Insert:

* Insert markdown into the current report editor.
* Do not duplicate same item if already inserted.
* Mark item as included in report.

Report bottom buttons:

* Preview
* Export PDF
* Export DOCX

Submit for Review:

Opens dialog:

Title: Submit Report for Review

Fields:

* Reviewer select
* Visibility:

  * Reviewer Only
  * Case Shared
* Message
* Submit button

After submit:

* Report status becomes In Review
* Visibility changes from Personal Draft to Reviewer Only or Case Shared
* Reviewer can see it in Reports → Review Queue


---


## UX rules

Very important:

Do not make too many tabs.

Use this simple rule:

Main case tabs:

* Overview
* Evidences
* Results
* Report
* Members
* Activity

For output viewer, use only:

* Overview
* Raw Output

Inside Overview, show:

* Summary
* Key Findings
* Extracted IOCs
* Artifacts

Raw Output stays hidden until needed.

Use side drawers/dialogs for:

* Add Indicator
* Create Finding
* Add to Timeline
* Raw Output
* Submit for Review
* Upgrade Plan

Do not show fake hardcoded terminal output everywhere. Use mock data objects and render from data.

Use professional labels:

* Add Indicator
* Create Finding
* Add to Timeline
* Add to Report
* Evidence Note
* Analyst Note

Avoid confusing labels like only “Save” or “Note”.

---

## Visual design requirements

* Thin borders
* Rounded cards
* Good spacing
* Clear hierarchy
* No colorful dashboard unless status badges need color
* Status badges:

  * Completed
  * Running
  * Queued
  * Failed
  * Locked
* Locked advanced modules should show a lock icon and required plan.

---

## Final flow to implement

1. User opens case Evidences tab.
2. User clicks Analyze on an evidence file.
3. Analyze page shows only compatible modules for that file type.
4. User selects modules.
5. Basic lightweight modules are grouped into Basic Triage Bundle.
6. User clicks Next / Analyze.
7. Analysis Progress shows bundle tasks and separate module jobs.
8. User opens Result Canvas.
9. Output Viewer shows Overview and Raw Output.
10. User can Add Indicator, Create Finding, Add to Timeline, or Add to Report.
11. Report tab shows saved findings, saved IOCs, and timeline events.
12. User inserts selected items into editable Markdown report.
13. User can save as Personal Draft or Case Shared.
14. User can preview/export PDF/DOCX.
15. Submit for Review changes report status to In Review and sends to reviewer queue.

Build the UI with reusable components and make the comptabile modules panel data-driven and large(a complete mock module register in the frontend and render modules from it, and keep things according to subscription basis), but keep the structure clean, and professional.
