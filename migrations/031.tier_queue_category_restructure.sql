-- Collapse the 5-value tier system (free/basic_triage/standard/advanced/
-- enterprise) into the 4 tiers actually used going forward: basic,
-- core_forensics, specialized_forensics, enterprise. Rename the 3 queues
-- that don't already match the light/medium/heavy/full container naming
-- convention. Seed the 6 real tool categories (separate axis from tier -
-- purely for grouping/display in the Modules admin page).

-- ── Tiers: modules ────────────────────────────────────────────────────────────
UPDATE `analysis_module_defs` SET `tier` = 'basic'                 WHERE `tier` IN ('free', 'basic_triage');
UPDATE `analysis_module_defs` SET `tier` = 'core_forensics'        WHERE `tier` = 'standard';
UPDATE `analysis_module_defs` SET `tier` = 'specialized_forensics' WHERE `tier` = 'advanced';
-- 'enterprise' already matches the new name - no change needed.

-- ── Tiers: plans.allowed_tiers (JSON array column) ────────────────────────────
-- One-time remap of the rows that exist today. Going forward, the admin UI
-- only ever offers the 4 new tier checkboxes, so no ongoing translation is
-- needed after this.
UPDATE `plans` SET `allowed_tiers` = JSON_ARRAY('basic')
  WHERE JSON_CONTAINS(`allowed_tiers`, '"free"') AND NOT JSON_CONTAINS(`allowed_tiers`, '"standard"')
    AND NOT JSON_CONTAINS(`allowed_tiers`, '"advanced"') AND NOT JSON_CONTAINS(`allowed_tiers`, '"enterprise"');

UPDATE `plans` SET `allowed_tiers` = JSON_ARRAY('basic', 'core_forensics')
  WHERE JSON_CONTAINS(`allowed_tiers`, '"standard"') AND NOT JSON_CONTAINS(`allowed_tiers`, '"advanced"')
    AND NOT JSON_CONTAINS(`allowed_tiers`, '"enterprise"');

UPDATE `plans` SET `allowed_tiers` = JSON_ARRAY('basic', 'core_forensics', 'specialized_forensics')
  WHERE JSON_CONTAINS(`allowed_tiers`, '"advanced"') AND NOT JSON_CONTAINS(`allowed_tiers`, '"enterprise"');

UPDATE `plans` SET `allowed_tiers` = JSON_ARRAY('basic', 'core_forensics', 'specialized_forensics', 'enterprise')
  WHERE JSON_CONTAINS(`allowed_tiers`, '"enterprise"');

-- ── Queues: rename to match the light/medium/heavy/full container convention ──
-- fast_queue -> light_queue, standard_queue -> medium_queue,
-- sandbox_queue -> full_queue. heavy_queue already matches, unchanged.
ALTER TABLE `instances` MODIFY COLUMN `queue_name` VARCHAR(32) NOT NULL DEFAULT 'medium_queue';

UPDATE `instances` SET `queue_name` = 'light_queue'  WHERE `queue_name` = 'fast_queue';
UPDATE `instances` SET `queue_name` = 'medium_queue' WHERE `queue_name` = 'standard_queue';
UPDATE `instances` SET `queue_name` = 'full_queue'   WHERE `queue_name` = 'sandbox_queue';

ALTER TABLE `instances`
  MODIFY COLUMN `queue_name` enum('light_queue','medium_queue','heavy_queue','full_queue')
  NOT NULL DEFAULT 'medium_queue';

-- ── Categories: tool-organizing axis, independent of tier ─────────────────────
INSERT INTO `categories` (`id`, `name`, `description`, `sort_order`) VALUES
  ('image_forensics',  'Image Forensics',  'Disk/memory image acquisition and file-image analysis tools', 0),
  ('disk_forensics',   'Disk Forensics',   'File-system analysis, recovery, and carving tools', 1),
  ('memory_forensics', 'Memory Forensics', 'Memory dump analysis tools', 2),
  ('email_forensics',  'Email Forensics',  'Email artifact and header analysis tools', 3),
  ('mobile_forensics', 'Mobile Forensics', 'Mobile device (Android/iOS) artifact extraction tools', 4),
  ('static_analysis',  'Static Analysis (Reverse Engineering)', 'Binary/malware reverse engineering tools', 5)
ON DUPLICATE KEY UPDATE `name` = VALUES(`name`);
