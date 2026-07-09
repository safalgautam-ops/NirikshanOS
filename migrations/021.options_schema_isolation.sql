-- Phase 3: flip batchable to 0 (one container per module, true isolation).
-- Phase 4: add options_schema column for typed per-module option definitions.

UPDATE `analysis_module_defs` SET `batchable` = 0, `batch_group` = NULL;

ALTER TABLE `analysis_module_defs`
  ADD COLUMN `options_schema` JSON NULL AFTER `timeout_seconds`;

-- Seed real options_schema for the three published built-in modules.
UPDATE `analysis_module_defs`
SET `options_schema` = JSON_ARRAY(
  JSON_OBJECT(
    'key',     'algorithms',
    'label',   'Hash Algorithms',
    'type',    'checklist',
    'default', JSON_ARRAY('md5','sha1','sha256'),
    'options', JSON_ARRAY('md5','sha1','sha256','sha512','sha3_256'),
    'description', 'Which hash algorithms to compute'
  )
)
WHERE `id` = 'generic.hash_calculation';

UPDATE `analysis_module_defs`
SET `options_schema` = JSON_ARRAY(
  JSON_OBJECT(
    'key',     'min_length',
    'label',   'Minimum String Length',
    'type',    'number',
    'default', 4,
    'description', 'Ignore strings shorter than this'
  ),
  JSON_OBJECT(
    'key',     'include_unicode',
    'label',   'Include Unicode Strings',
    'type',    'checkbox',
    'default', JSON_LITERAL('false'),
    'description', 'Also extract wide-char (UTF-16) strings'
  )
)
WHERE `id` = 'generic.strings_extraction';
