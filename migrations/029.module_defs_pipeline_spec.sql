-- Structured multi-step chain definition for a module ("what runs when,
-- in what order, with what dependencies") — separate from a single entry
-- point file's raw content. NULL means "no chain — run the entry point
-- file as a single step," preserving today's simple-module behavior.

ALTER TABLE `analysis_module_defs`
  ADD COLUMN `pipeline_spec` JSON NULL AFTER `options_schema`;
