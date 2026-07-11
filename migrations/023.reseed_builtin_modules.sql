-- Re-seed the three built-in modules that were removed by migration 022.
-- Uses the CORRECT parser_name values that match the actual PARSER_NAME constants
-- in app/features/analysis/parsers/:
--   hashing_parser.py     → PARSER_NAME = "hash_calculation_parser"
--   file_info_parser.py   → PARSER_NAME = "file_identification_parser"
--   strings_parser.py     → PARSER_NAME = "strings_extraction_parser"
--
-- Migration 017 seeded wrong names (hashing_parser, file_info_parser, strings_parser).
-- Migration 022 then deleted them. This re-inserts them correctly.

INSERT INTO `analysis_module_defs`
  (`id`, `display_name`, `description`, `category`, `tier`, `runtime_image`,
   `queue_name`, `isolation_level`, `batchable`, `batch_group`, `timeout_seconds`,
   `parser_name`, `is_enabled`, `status`, `source`)
VALUES
  ('generic.hash_calculation',
   'Hash Calculation',
   'Computes MD5, SHA-1, and SHA-256 hashes of the evidence file.',
   'generic', 'basic_triage', 'nirikshan/base:1.0',
   'fast_queue', 'none', 0, NULL, 60,
   'hash_calculation_parser', 1, 'published', 'builtin'),

  ('generic.file_identification',
   'File Type Identification',
   'Detects the real file type from magic bytes, independent of the file extension.',
   'generic', 'basic_triage', 'nirikshan/base:1.0',
   'fast_queue', 'none', 0, NULL, 30,
   'file_identification_parser', 1, 'published', 'builtin'),

  ('generic.strings_extraction',
   'String Extraction',
   'Extracts printable ASCII and Unicode strings from binary evidence.',
   'generic', 'basic_triage', 'nirikshan/base:1.0',
   'fast_queue', 'none', 0, NULL, 60,
   'strings_extraction_parser', 1, 'published', 'builtin')

ON DUPLICATE KEY UPDATE
  `display_name`    = VALUES(`display_name`),
  `description`     = VALUES(`description`),
  `parser_name`     = VALUES(`parser_name`),
  `queue_name`      = VALUES(`queue_name`),
  `isolation_level` = VALUES(`isolation_level`),
  `timeout_seconds` = VALUES(`timeout_seconds`),
  `status`          = VALUES(`status`),
  `is_enabled`      = VALUES(`is_enabled`);

-- Restore options_schema for hash_calculation and strings_extraction.
UPDATE `analysis_module_defs`
SET `options_schema` = JSON_ARRAY(
  JSON_OBJECT(
    'key',         'algorithms',
    'label',       'Hash Algorithms',
    'type',        'checklist',
    'default',     JSON_ARRAY('md5','sha1','sha256'),
    'options',     JSON_ARRAY('md5','sha1','sha256','sha512'),
    'description', 'Which hash algorithms to compute'
  )
)
WHERE `id` = 'generic.hash_calculation';

UPDATE `analysis_module_defs`
SET `options_schema` = JSON_ARRAY(
  JSON_OBJECT(
    'key',         'min_length',
    'label',       'Minimum String Length',
    'type',        'number',
    'default',     4,
    'description', 'Ignore strings shorter than this'
  ),
  JSON_OBJECT(
    'key',         'include_unicode',
    'label',       'Include Unicode Strings',
    'type',        'checkbox',
    'default',     JSON_LITERAL('false'),
    'description', 'Also extract wide-char (UTF-16) strings'
  )
)
WHERE `id` = 'generic.strings_extraction';
