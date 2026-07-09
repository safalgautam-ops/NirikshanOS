-- Admin-managed module definitions. Seeded from module_registry.py on startup.
-- When yaml_definition is non-null and source='custom', the worker embeds it as
-- execution_spec in job_config.json so the container runs the DB-defined YAML
-- instead of (or in addition to) its baked-in Python handler.

CREATE TABLE IF NOT EXISTS `analysis_module_defs` (
  `id`               varchar(100)  NOT NULL,
  `display_name`     varchar(128)  NOT NULL,
  `description`      text          NULL,
  `category`         varchar(50)   NOT NULL DEFAULT 'generic',
  `tier`             varchar(20)   NOT NULL DEFAULT 'free',
  `runtime_image`    varchar(128)  NOT NULL DEFAULT 'dfir/basic-tools:1.0',
  `is_enabled`       tinyint(1)    NOT NULL DEFAULT 1,
  `yaml_definition`  text          NULL,
  `source`           enum('builtin','custom') NOT NULL DEFAULT 'builtin',
  `created_by`       varchar(191)  NULL,
  `created_at`       timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`       timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
