-- Stores the parsed output of each analysis task.
-- One row per task (one module in one job). Created by the worker after
-- parse_module_output() runs. Cascades away when the parent task is deleted.

CREATE TABLE IF NOT EXISTS `analysis_results` (
  `id`              char(36)      NOT NULL,
  `job_id`          char(36)      NOT NULL,
  `task_id`         char(36)      NOT NULL,
  `case_id`         char(36)      NOT NULL,
  `evidence_id`     char(36)      NOT NULL,
  `module_id`       varchar(100)  NOT NULL,
  `summary_json`    json          NULL,    -- parser summary dict
  `normalized_json` json          NULL,    -- {"iocs": [...], "findings": [...], "artifacts": [...]}
  `stdout_path`     varchar(512)  NULL,    -- absolute host path to raw stdout file
  `stderr_path`     varchar(512)  NULL,    -- absolute host path to raw stderr file
  `artifact_path`   varchar(512)  NULL,    -- reserved for future artifact archiving
  `created_at`      timestamp     NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ar_task_unique` (`task_id`),
  CONSTRAINT `ar_task_fk` FOREIGN KEY (`task_id`) REFERENCES `analysis_tasks`(`id`) ON DELETE CASCADE,
  CONSTRAINT `ar_job_fk`  FOREIGN KEY (`job_id`)  REFERENCES `analysis_jobs`(`id`)  ON DELETE CASCADE,
  KEY `ar_evidence_idx` (`evidence_id`),
  KEY `ar_case_idx`     (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
