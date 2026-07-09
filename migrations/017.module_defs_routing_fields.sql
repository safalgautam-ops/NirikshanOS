-- Extend analysis_module_defs with routing/scheduling metadata and status gate.
-- Also seeds the 3 real built-in modules that actually have container implementations.

ALTER TABLE `analysis_module_defs`
  ADD COLUMN `supported_types` text          NULL          AFTER `description`,
  ADD COLUMN `parser_name`     varchar(100)  NULL          AFTER `supported_types`,
  ADD COLUMN `queue_name`      varchar(50)   NOT NULL DEFAULT 'standard_queue' AFTER `runtime_image`,
  ADD COLUMN `isolation_level` varchar(30)   NOT NULL DEFAULT 'sandboxed'      AFTER `queue_name`,
  ADD COLUMN `batchable`       tinyint(1)    NOT NULL DEFAULT 0                AFTER `isolation_level`,
  ADD COLUMN `batch_group`     varchar(100)  NULL                              AFTER `batchable`,
  ADD COLUMN `timeout_seconds` int           NOT NULL DEFAULT 120              AFTER `batch_group`,
  ADD COLUMN `status`          enum('draft','published') NOT NULL DEFAULT 'draft' AFTER `is_enabled`;

-- The only 3 modules that have real container implementations.
-- supported_types NULL = compatible with all evidence types.
INSERT INTO `analysis_module_defs`
  (`id`, `display_name`, `description`, `category`, `tier`, `runtime_image`,
   `queue_name`, `isolation_level`, `batchable`, `batch_group`, `timeout_seconds`,
   `parser_name`, `is_enabled`, `status`, `source`)
VALUES
  ('generic.hash_calculation',
   'Hash Calculation',
   'Computes MD5, SHA-1, and SHA-256 hashes of the evidence file.',
   'generic', 'basic_triage', 'dfir/basic-tools:1.0',
   'fast_queue', 'none', 1, 'basic_triage', 60,
   'hashing_parser', 1, 'published', 'builtin'),

  ('generic.file_identification',
   'File Type Identification',
   'Detects the real file type from magic bytes, independent of the file extension.',
   'generic', 'basic_triage', 'dfir/basic-tools:1.0',
   'fast_queue', 'none', 1, 'basic_triage', 30,
   'file_info_parser', 1, 'published', 'builtin'),

  ('generic.strings_extraction',
   'String Extraction',
   'Extracts printable ASCII and Unicode strings from binary evidence.',
   'generic', 'basic_triage', 'dfir/basic-tools:1.0',
   'fast_queue', 'none', 1, 'basic_triage', 60,
   'strings_parser', 1, 'published', 'builtin')

ON DUPLICATE KEY UPDATE
  `display_name`  = VALUES(`display_name`),
  `description`   = VALUES(`description`),
  `parser_name`   = VALUES(`parser_name`),
  `queue_name`    = VALUES(`queue_name`),
  `isolation_level` = VALUES(`isolation_level`),
  `batchable`     = VALUES(`batchable`),
  `batch_group`   = VALUES(`batch_group`),
  `timeout_seconds` = VALUES(`timeout_seconds`),
  `status`        = VALUES(`status`);
