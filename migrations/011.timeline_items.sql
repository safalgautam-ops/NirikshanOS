-- Manual investigation timeline: analyst-authored tasks/notes/milestones for
-- a case, distinct from `audit_logs` (which is an automatic, system-written
-- record of actions taken in the app). One table, not three, since the only
-- difference between a task/note/milestone is which of these optional
-- columns are filled in - title/description/timeline_time/created_by are
-- the only fields every type actually shares.
CREATE TABLE `timeline_items` (
  `id`                  char(36)     NOT NULL,
  `case_id`             char(36)     NOT NULL,
  `type`                enum('task','note','milestone') NOT NULL,
  `title`               varchar(255) NOT NULL,
  `description`         text,                                     -- task/milestone description, or the note's body
  `status`              enum('pending','in_progress','done','blocked','cancelled') NULL,
  `priority`            enum('low','medium','high') NULL,
  `assigned_to`         varchar(191) NULL,
  `due_date`            date         NULL,
  `linked_evidence_id`  char(36)     NULL,                        -- task only; real FK, evidence belongs to this app
  `linked_result_label` varchar(255) NULL,                        -- task only; free text - analysis results aren't persisted yet
  `visibility`          enum('private','case_shared') NULL,       -- note only
  `timeline_time`       timestamp    NOT NULL,
  `created_by`          varchar(191) NOT NULL,
  `created_at`          timestamp    NOT NULL DEFAULT (now()),
  `updated_at`          timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `tl_case_fk`     FOREIGN KEY (`case_id`)            REFERENCES `cases`(`id`)    ON DELETE CASCADE,
  CONSTRAINT `tl_assignee_fk` FOREIGN KEY (`assigned_to`)        REFERENCES `user`(`id`)     ON DELETE SET NULL,
  CONSTRAINT `tl_evidence_fk` FOREIGN KEY (`linked_evidence_id`) REFERENCES `evidence`(`id`) ON DELETE SET NULL,
  CONSTRAINT `tl_creator_fk`  FOREIGN KEY (`created_by`)         REFERENCES `user`(`id`)     ON DELETE RESTRICT,
  KEY `tl_case_idx` (`case_id`),
  KEY `tl_time_idx` (`case_id`,`timeline_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
