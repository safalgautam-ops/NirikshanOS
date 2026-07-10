-- Remove all builtin module definitions and their files.
-- After this, all modules must be created and managed via the admin IDE.
DELETE FROM module_files
WHERE module_id IN (
    SELECT id FROM analysis_module_defs WHERE source = 'builtin'
);

DELETE FROM analysis_module_defs WHERE source = 'builtin';
