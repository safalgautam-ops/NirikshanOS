-- Phase 2: replace yaml_definition single blob with module_files multi-file tree.
-- Each module can have multiple files (Python scripts, YAML specs, helpers).
-- One file per module is designated as the entry point.

CREATE TABLE `module_files` (
  `id`             varchar(32)  NOT NULL,
  `module_id`      varchar(100) NOT NULL,
  `filename`       varchar(255) NOT NULL,
  `content`        mediumtext   NOT NULL,
  `is_entry_point` tinyint(1)   NOT NULL DEFAULT 0,
  `created_at`     datetime     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`     datetime     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_module_file` (`module_id`, `filename`),
  KEY `idx_module_files_module` (`module_id`),
  CONSTRAINT `fk_module_files_module`
    FOREIGN KEY (`module_id`) REFERENCES `analysis_module_defs` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Migrate any existing yaml_definition blobs → main.yaml entry point files.
INSERT INTO `module_files` (`id`, `module_id`, `filename`, `content`, `is_entry_point`)
SELECT
  LOWER(REPLACE(UUID(), '-', '')),
  `id`,
  'main.yaml',
  `yaml_definition`,
  1
FROM `analysis_module_defs`
WHERE `yaml_definition` IS NOT NULL AND TRIM(`yaml_definition`) != '';

-- Drop the now-redundant column.
ALTER TABLE `analysis_module_defs`
  DROP COLUMN `yaml_definition`;
