-- Cases were scaffolded in migrations/001.initial_schema.sql before the
-- organizations feature existed (migrations/002+), so `cases` has no tenant
-- boundary yet. This wires it into the org model the same way every other
-- feature is scoped, and extends `evidence` for resumable chunked uploads -
-- the original table assumed a row is only ever inserted once a file is
-- already whole on disk (sha256/md5/stored_path all NOT NULL), which can't
-- hold for a 30-100GB upload that needs to survive a network blip.
--
-- Deliberately NOT touched: case_roles / case_permissions /
-- case_role_permissions / case_member_roles. Per-case visibility for now is
-- just membership (case_members) + the case's creator + the org's owner -
-- the existing per-case dynamic-role system stays unused until that's
-- actually wanted.

ALTER TABLE `cases`
  ADD COLUMN `organization_id` char(36)    NOT NULL AFTER `id`,
  ADD COLUMN `classification`  varchar(64) NULL AFTER `severity`,
  ADD COLUMN `forensic_status` enum(
                                  'not_started','queued','hash_verified','hash_matching',
                                  'review_in_progress','report_generation','completed',
                                  'failed','paused','cancelled'
                                ) NOT NULL DEFAULT 'not_started' AFTER `classification`,
  ADD CONSTRAINT `cases_org_fk` FOREIGN KEY (`organization_id`) REFERENCES `organizations`(`id`) ON DELETE CASCADE,
  ADD KEY `cases_org_idx` (`organization_id`);

-- Resumable upload support. sha256/md5/stored_path can only be known once
-- every chunk has arrived and been reassembled, so they have to allow NULL
-- for the (now real, not just instantaneous) "still uploading" window.
ALTER TABLE `evidence`
  MODIFY COLUMN `stored_path` varchar(512) NULL,
  MODIFY COLUMN `sha256`      char(64)     NULL,
  ADD COLUMN `status` enum('uploading','paused','completed','failed','cancelled')
             NOT NULL DEFAULT 'completed' AFTER `size_bytes`,
  ADD COLUMN `received_bytes` bigint unsigned NOT NULL DEFAULT 0 AFTER `status`,
  ADD COLUMN `chunk_size`     int            NULL AFTER `received_bytes`,
  ADD COLUMN `total_chunks`   int            NULL AFTER `chunk_size`;

-- Which chunks have actually landed on disk for a given evidence file - the
-- resumability backbone. On resume, the client asks "which chunk indexes do
-- you already have?" and only (re-)sends what's missing. Re-uploading the
-- same index is idempotent: the PK just overwrites that one row/chunk file,
-- so a retried or duplicated chunk request can never corrupt the others.
CREATE TABLE `evidence_chunks` (
  `evidence_id`  char(36)  NOT NULL,
  `chunk_index`  int       NOT NULL,
  `size_bytes`   int       NOT NULL,
  `received_at`  timestamp NOT NULL DEFAULT (now()),
  PRIMARY KEY (`evidence_id`, `chunk_index`),
  CONSTRAINT `evidence_chunk_fk` FOREIGN KEY (`evidence_id`) REFERENCES `evidence`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
