-- Tracks whether a finding/indicator has already been inserted into the
-- case report draft. Previously this lived only in browser memory
-- (case-workspace.js state), so it reset to "not inserted" on every page
-- refresh even for items the analyst had already inserted.

ALTER TABLE `case_findings`
  ADD COLUMN `included_in_report` tinyint(1) NOT NULL DEFAULT 0 AFTER `source_module`;

ALTER TABLE `case_indicators`
  ADD COLUMN `included_in_report` tinyint(1) NOT NULL DEFAULT 0 AFTER `source_module`;
