-- Ad-hoc in-IDE test runs — completely separate from the case/evidence
-- data model (analysis_jobs/analysis_tasks), since a test run has no case
-- and no real evidence row, just an optional uploaded sample file.

CREATE TABLE `module_test_runs` (
  `id`             varchar(32)  NOT NULL,
  `module_id`      varchar(100) NOT NULL,
  `instance_id`    varchar(64)  NOT NULL,
  `s3_key`         varchar(512) NULL,
  `status`         enum('queued','running','completed','failed') NOT NULL DEFAULT 'queued',
  `error_message`  text         NULL,
  `result_json`    json         NULL,
  `created_by`     varchar(191) NOT NULL,
  `created_at`     timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `finished_at`    timestamp    NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_module_test_runs_module` (`module_id`),
  CONSTRAINT `fk_module_test_runs_module`
    FOREIGN KEY (`module_id`) REFERENCES `analysis_module_defs` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_module_test_runs_instance`
    FOREIGN KEY (`instance_id`) REFERENCES `instances` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
