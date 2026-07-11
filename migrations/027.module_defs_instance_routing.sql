-- Modules now point at a registered instance (container) instead of
-- carrying their own runtime_image/queue_name/isolation_level/batch config.
-- Container grouping moves to planner.py, keyed on instance_id alone —
-- these per-module columns existed only to feed the old 4-tuple grouping
-- and are dead weight once that's gone.

ALTER TABLE `analysis_module_defs`
  ADD COLUMN `instance_id` varchar(64) NULL AFTER `category_id`;

-- Nullable at the DB layer (existing rows have no instance yet — an admin
-- must assign one before enabling/publishing further); enforced NOT NULL
-- at the application layer in admin_modules routes going forward.
ALTER TABLE `analysis_module_defs`
  ADD CONSTRAINT `fk_module_defs_instance`
    FOREIGN KEY (`instance_id`) REFERENCES `instances` (`id`)
    ON DELETE SET NULL;

ALTER TABLE `analysis_module_defs`
  DROP COLUMN `runtime_image`,
  DROP COLUMN `queue_name`,
  DROP COLUMN `isolation_level`,
  DROP COLUMN `batchable`,
  DROP COLUMN `batch_group`;
