-- Analyst notes attached to a specific module result within a case.
-- Scoped to evidence + module (not to a task/job) so notes survive re-analysis.

CREATE TABLE IF NOT EXISTS `analysis_notes` (
  `id`          char(36)      NOT NULL,
  `case_id`     char(36)      NOT NULL,
  `evidence_id` char(36)      NOT NULL,
  `module_id`   varchar(100)  NOT NULL,
  `author_id`   char(36)      NOT NULL,
  `body`        text          NOT NULL,
  `created_at`  timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`  timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `an_scope_unique` (`evidence_id`, `module_id`, `author_id`),
  CONSTRAINT `an_case_fk`     FOREIGN KEY (`case_id`)     REFERENCES `cases`(`id`)     ON DELETE CASCADE,
  CONSTRAINT `an_evidence_fk` FOREIGN KEY (`evidence_id`) REFERENCES `evidence`(`id`)  ON DELETE CASCADE,
  KEY `an_case_idx` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
