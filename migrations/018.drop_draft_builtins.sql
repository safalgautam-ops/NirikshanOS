-- Remove the 101 hardcoded placeholder module rows that have no container
-- implementation. Only the 3 published builtins (seeded in 017) are real.
-- Custom modules created by admins (source='custom') are preserved.
DELETE FROM `analysis_module_defs`
WHERE `status` = 'draft'
  AND `source` = 'builtin';
