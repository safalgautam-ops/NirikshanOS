-- Analyst-authored findings and indicators of compromise, sourced from
-- analysis results. Both are case-scoped and survive re-analysis runs.

CREATE TABLE IF NOT EXISTS `case_findings` (
  `id`             char(36)      NOT NULL,
  `case_id`        char(36)      NOT NULL,
  `evidence_id`    char(36)      NULL,
  `module_id`      varchar(100)  NULL,
  `author_id`      char(36)      NOT NULL,
  `title`          varchar(255)  NOT NULL,
  `description`    text          NOT NULL,
  `severity`       varchar(20)   NOT NULL DEFAULT 'medium',
  `confidence`     varchar(20)   NOT NULL DEFAULT 'medium',
  `source_evidence` varchar(255) NULL,
  `source_module`  varchar(255)  NULL,
  `created_at`     timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `cf_case_fk`     FOREIGN KEY (`case_id`)     REFERENCES `cases`(`id`)    ON DELETE CASCADE,
  CONSTRAINT `cf_evidence_fk` FOREIGN KEY (`evidence_id`) REFERENCES `evidence`(`id`) ON DELETE SET NULL,
  KEY `cf_case_idx` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `case_indicators` (
  `id`             char(36)      NOT NULL,
  `case_id`        char(36)      NOT NULL,
  `evidence_id`    char(36)      NULL,
  `module_id`      varchar(100)  NULL,
  `author_id`      char(36)      NOT NULL,
  `ioc_type`       varchar(50)   NOT NULL,
  `value`          varchar(2048) NOT NULL,
  -- SHA2(case_id|ioc_type|value) pre-computed by the app layer so the UNIQUE
  -- key is a fixed-width column. MySQL prevents FK on columns read by a STORED
  -- GENERATED column, so the hash is written explicitly on every INSERT.
  `value_hash`     char(64)      NOT NULL,
  `severity`       varchar(20)   NOT NULL DEFAULT 'medium',
  `confidence`     varchar(20)   NOT NULL DEFAULT 'medium',
  `source_evidence` varchar(255) NULL,
  `source_module`  varchar(255)  NULL,
  `created_at`     timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ci_dedup` (`value_hash`),
  CONSTRAINT `ci_case_fk`     FOREIGN KEY (`case_id`)     REFERENCES `cases`(`id`)    ON DELETE CASCADE,
  CONSTRAINT `ci_evidence_fk` FOREIGN KEY (`evidence_id`) REFERENCES `evidence`(`id`) ON DELETE SET NULL,
  KEY `ci_case_idx` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
