-- Analysis job tracking: one job row per container invocation (one batch of
-- compatible modules, or one non-batchable module running alone), with one
-- task row per module inside that job.
--
-- Drop order matters: analysis_tasks must go before analysis_jobs because of
-- the at_job_fk foreign key. The other drops remove earlier design attempts
-- that are no longer needed (all were empty when dropped).
DROP TABLE IF EXISTS `analysis_tasks`;
DROP TABLE IF EXISTS `analysis_tasks`;
DROP TABLE IF EXISTS `analysis_results`;
DROP TABLE IF EXISTS `job_assignees`;
DROP TABLE IF EXISTS `analysis_jobs`;

CREATE TABLE `analysis_jobs` (
  `id`              char(36)     NOT NULL,
  `case_id`         char(36)     NOT NULL,
  `evidence_id`     char(36)     NOT NULL,
  `org_id`          char(36)     NOT NULL,    -- denormalized from case.organization_id for fast org-scoped queries
  `created_by`      char(36)     NOT NULL,
  `job_type`        varchar(100) NOT NULL,    -- e.g. "basic_triage", "generic.yara_scan", "binary.ghidra_decompile"
  `queue_name`      enum('fast_queue','standard_queue','heavy_queue','sandbox_queue') NOT NULL,
  `runtime_image`   varchar(255) NOT NULL,
  `isolation_level` enum('none','sandboxed','network_restricted','vm') NOT NULL,
  `batch_group`     varchar(100) NULL,        -- non-null only for batchable jobs
  `batchable`       tinyint(1)   NOT NULL DEFAULT 0,
  `status`          enum('queued','running','completed','failed','cancelled') NOT NULL DEFAULT 'queued',
  `error_message`   text         NULL,        -- set by workers on failure; null when queued/running/completed
  `created_at`      timestamp    NOT NULL DEFAULT (now()),
  `updated_at`      timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  `started_at`      timestamp    NULL,
  `finished_at`     timestamp    NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `aj_case_fk`     FOREIGN KEY (`case_id`)     REFERENCES `cases`(`id`)         ON DELETE CASCADE,
  CONSTRAINT `aj_evidence_fk` FOREIGN KEY (`evidence_id`) REFERENCES `evidence`(`id`)      ON DELETE CASCADE,
  CONSTRAINT `aj_org_fk`      FOREIGN KEY (`org_id`)      REFERENCES `organizations`(`id`) ON DELETE CASCADE,
  CONSTRAINT `aj_creator_fk`  FOREIGN KEY (`created_by`)  REFERENCES `user`(`id`)          ON DELETE RESTRICT,
  KEY `aj_evidence_idx` (`evidence_id`),
  KEY `aj_case_idx`     (`case_id`),
  KEY `aj_org_idx`      (`org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `analysis_tasks` (
  `id`           char(36)     NOT NULL,
  `job_id`       char(36)     NOT NULL,
  `module_id`    varchar(100) NOT NULL,   -- e.g. "generic.yara_scan"
  `module_name`  varchar(255) NOT NULL,   -- human label, e.g. "YARA Rule Scan"
  `options_json` json         NULL,       -- per-task module options, e.g. {"min_length": 6, "ruleset": "default"}
  `status`       enum('queued','running','completed','failed','cancelled') NOT NULL DEFAULT 'queued',
  `error_message` text        NULL,
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  `updated_at`   timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  `started_at`   timestamp    NULL,
  `finished_at`  timestamp    NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `at_job_fk` FOREIGN KEY (`job_id`) REFERENCES `analysis_jobs`(`id`) ON DELETE CASCADE,
  KEY `at_job_idx` (`job_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
