-- Admin-registered container runtimes ("instances"). Replaces the env-var
-- ALLOWED_RUNTIME_IMAGES allowlist and the hardcoded per-isolation-level
-- resource caps in docker_runner.py — the DB is now the single source of
-- truth for which images may be scheduled and what resources they get.
-- No seed rows: admins register their own, nothing hardcoded.

CREATE TABLE `instances` (
  `id`                     varchar(64)   NOT NULL,
  `display_name`           varchar(128)  NOT NULL,
  `image_tag`              varchar(255)  NOT NULL,
  `cpu_limit`              varchar(10)   NOT NULL DEFAULT '1.0',
  `memory_limit`           varchar(10)   NOT NULL DEFAULT '512m',
  `pids_limit`             int           NOT NULL DEFAULT 128,
  `queue_name`             enum('fast_queue','standard_queue','heavy_queue','sandbox_queue') NOT NULL DEFAULT 'standard_queue',
  `default_timeout_seconds` int          NOT NULL DEFAULT 120,
  `image_status`           enum('unknown','ready','missing') NOT NULL DEFAULT 'unknown',
  `image_checked_at`       timestamp     NULL DEFAULT NULL,
  `is_active`               tinyint(1)   NOT NULL DEFAULT 1,
  `created_by`              varchar(191) NULL,
  `created_at`              timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`              timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_instances_image_tag` (`image_tag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Which registered instances a plan grants access to.
CREATE TABLE `plan_instances` (
  `plan_id`     varchar(100) NOT NULL,
  `instance_id` varchar(64)  NOT NULL,
  PRIMARY KEY (`plan_id`, `instance_id`),
  CONSTRAINT `fk_plan_instances_plan`
    FOREIGN KEY (`plan_id`) REFERENCES `plans` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_plan_instances_instance`
    FOREIGN KEY (`instance_id`) REFERENCES `instances` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
