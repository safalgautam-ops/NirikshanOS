-- =====================================================================
-- NirikshanOS — Database Schema (MySQL 8.0+)
-- =====================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- =====================================================================
-- 1 + 2.  BETTERAUTH  (identity & authentication — BetterAuth writes these)
-- =====================================================================
-- handled entirely by the custom RBAC tables (global) and per-case RBAC tables.

CREATE TABLE `user` (
  `id`               varchar(191) NOT NULL,
  `name`             varchar(191) NOT NULL,
  `email`            varchar(191) NOT NULL,
  `username`         varchar(191),
  `emailVerified`    boolean      NOT NULL DEFAULT false,
  `image`            text,
  `bio`              text,
  `phone`            varchar(32),
  `timezone`         varchar(64)  NOT NULL DEFAULT 'UTC',
  `isActive`         boolean      NOT NULL DEFAULT true,
  `twoFactorEnabled` boolean      NOT NULL DEFAULT false,
  `createdAt`        timestamp    NOT NULL DEFAULT (now()),
  `updatedAt`        timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `user_id` PRIMARY KEY (`id`),
  CONSTRAINT `user_email_unique`    UNIQUE (`email`),
  CONSTRAINT `user_username_unique` UNIQUE (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `session` (
  `id`         varchar(191) NOT NULL,
  `expiresAt`  timestamp    NOT NULL,
  `token`      varchar(255) NOT NULL,
  `createdAt`  timestamp    NOT NULL DEFAULT (now()),
  `updatedAt`  timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  `ipAddress`  varchar(255),
  `userAgent`  text,
  `userId`     varchar(191) NOT NULL,
  CONSTRAINT `session_id` PRIMARY KEY (`id`),
  CONSTRAINT `session_token_unique` UNIQUE (`token`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `account` (
  `id`                     varchar(191) NOT NULL,
  `accountId`              varchar(255) NOT NULL,
  `providerId`             varchar(255) NOT NULL,
  `userId`                 varchar(191) NOT NULL,
  `accessToken`            longtext,
  `refreshToken`           longtext,
  `idToken`                longtext,
  `accessTokenExpiresAt`   timestamp,
  `refreshTokenExpiresAt`  timestamp,
  `scope`                  text,
  `password`               text,
  `createdAt`              timestamp    NOT NULL DEFAULT (now()),
  `updatedAt`              timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `account_id` PRIMARY KEY (`id`),
  CONSTRAINT `account_provider_account_unique` UNIQUE (`providerId`,`accountId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `verification` (
  `id`          varchar(191) NOT NULL,
  `identifier`  varchar(191) NOT NULL,
  `value`       text         NOT NULL,
  `expiresAt`   timestamp    NOT NULL,
  `createdAt`   timestamp    NOT NULL DEFAULT (now()),
  `updatedAt`   timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `verification_id` PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `passkey` (
  `id`            varchar(191) NOT NULL,
  `name`          varchar(191),
  `publicKey`     longtext     NOT NULL,
  `userId`        varchar(191) NOT NULL,
  `credentialID`  varchar(512) NOT NULL,
  `counter`       int          NOT NULL DEFAULT 0,
  `deviceType`    varchar(64)  NOT NULL,
  `backedUp`      boolean      NOT NULL DEFAULT false,
  `transports`    varchar(255),
  `createdAt`     timestamp    NOT NULL DEFAULT (now()),
  `updatedAt`     timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  `aaguid`        varchar(191),
  CONSTRAINT `passkey_id` PRIMARY KEY (`id`),
  CONSTRAINT `passkey_credential_unique` UNIQUE (`credentialID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `twoFactor` (
  `id`           varchar(191) NOT NULL,
  `secret`       varchar(512) NOT NULL,
  `backupCodes`  text         NOT NULL,
  `userId`       varchar(191) NOT NULL,
  `createdAt`    timestamp    NOT NULL DEFAULT (now()),
  `updatedAt`    timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `twoFactor_id` PRIMARY KEY (`id`),
  CONSTRAINT `two_factor_user_unique` UNIQUE (`userId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- NOTE on providers: BetterAuth has NO provider table. A "provider" (google,
-- github, credential, passkey, ...) is configuration declared in code
-- (socialProviders: {...}), not a database row. The user<->provider link is the
-- `account` table itself: each account row = one user's connection to one
-- provider, with account.providerId holding the provider's string key and the
-- OAuth tokens stored in the same row. No FK to a provider table exists or
-- should exist (providerId='credential' for password logins isn't an OAuth
-- provider you'd register). A providers table would only make sense as a custom
-- admin feature for runtime-toggleable providers with DB-stored secrets — not
-- needed here, since plan.md keeps secrets in .env.

-- BetterAuth FKs + indexes
ALTER TABLE `account`   ADD CONSTRAINT `account_userId_user_id_fk`   FOREIGN KEY (`userId`) REFERENCES `user`(`id`) ON DELETE cascade ON UPDATE cascade;
ALTER TABLE `passkey`   ADD CONSTRAINT `passkey_userId_user_id_fk`   FOREIGN KEY (`userId`) REFERENCES `user`(`id`) ON DELETE cascade ON UPDATE cascade;
ALTER TABLE `session`   ADD CONSTRAINT `session_userId_user_id_fk`   FOREIGN KEY (`userId`) REFERENCES `user`(`id`) ON DELETE cascade ON UPDATE cascade;
ALTER TABLE `twoFactor` ADD CONSTRAINT `twoFactor_userId_user_id_fk` FOREIGN KEY (`userId`) REFERENCES `user`(`id`) ON DELETE cascade ON UPDATE cascade;

CREATE INDEX `user_username_unique`        ON `user`         (`username`);
CREATE INDEX `account_user_idx`            ON `account`      (`userId`);
CREATE INDEX `passkey_user_idx`            ON `passkey`      (`userId`);
CREATE INDEX `session_user_idx`            ON `session`      (`userId`);
CREATE INDEX `session_expires_idx`         ON `session`      (`expiresAt`);
CREATE INDEX `two_factor_user_idx`         ON `twoFactor`    (`userId`);
CREATE INDEX `verification_identifier_idx` ON `verification` (`identifier`);

-- =====================================================================
-- 3.  GLOBAL RBAC  (instance-wide authorization)
-- =====================================================================
--   * roles: added `priority` (tie-breaking / hierarchy) and `is_default`
--     (auto-assigned to new users), plus audit columns.
--   * permissions: split into `resource` + `action` columns (with a generated
--     `name` = resource.action) so permissions are queryable by resource and
--     enforced consistently; added `category` for grouping in the UI.
--   * role_permissions: added `granted_at` for auditability.
--   * user_roles: added `expires_at` (temporary elevation) alongside the
--     existing `assigned_by` / `assigned_at`.

CREATE TABLE `roles` (
  `id`           char(36)     NOT NULL,
  `name`         varchar(64)  NOT NULL,
  `description`  varchar(255),
  `priority`     int          NOT NULL DEFAULT 0,       -- higher wins on conflict
  `is_system`    boolean      NOT NULL DEFAULT false,   -- built-in, undeletable
  `is_default`   boolean      NOT NULL DEFAULT false,   -- auto-granted to new users
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  `updated_at`   timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `roles_name_unique` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `permissions` (
  `id`           char(36)     NOT NULL,
  `resource`     varchar(64)  NOT NULL,                 -- e.g. 'case', 'evidence'
  `action`       varchar(64)  NOT NULL,                 -- e.g. 'view', 'create'
  `name`         varchar(129) GENERATED ALWAYS AS (CONCAT(`resource`, '.', `action`)) STORED,
  `category`     varchar(64),                           -- UI grouping
  `description`  varchar(255),
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `permissions_name_unique`     (`name`),
  UNIQUE KEY `permissions_resource_action` (`resource`,`action`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `role_permissions` (
  `role_id`        char(36)     NOT NULL,
  `permission_id`  char(36)     NOT NULL,
  `granted_at`     timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`role_id`,`permission_id`),
  CONSTRAINT `rp_role_fk` FOREIGN KEY (`role_id`)       REFERENCES `roles`(`id`)       ON DELETE CASCADE,
  CONSTRAINT `rp_perm_fk` FOREIGN KEY (`permission_id`) REFERENCES `permissions`(`id`) ON DELETE CASCADE,
  KEY `rp_perm_idx` (`permission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `user_roles` (
  `user_id`      varchar(191) NOT NULL,
  `role_id`      char(36)     NOT NULL,
  `assigned_by`  varchar(191),                          -- nullable: system/seed
  `assigned_at`  timestamp    NOT NULL DEFAULT (now()),
  `expires_at`   timestamp    NULL,                      -- NULL = permanent
  PRIMARY KEY (`user_id`,`role_id`),
  CONSTRAINT `ur_user_fk`     FOREIGN KEY (`user_id`)     REFERENCES `user`(`id`)  ON DELETE CASCADE,
  CONSTRAINT `ur_role_fk`     FOREIGN KEY (`role_id`)     REFERENCES `roles`(`id`) ON DELETE CASCADE,
  CONSTRAINT `ur_assigner_fk` FOREIGN KEY (`assigned_by`) REFERENCES `user`(`id`)  ON DELETE SET NULL,
  KEY `ur_role_idx`    (`role_id`),
  KEY `ur_expires_idx` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- 4.  DFIR DOMAIN — Cases & Evidence
-- =====================================================================

CREATE TABLE `cases` (
  `id`           char(36)     NOT NULL,
  `case_number`  varchar(64)  NOT NULL,
  `title`        varchar(255) NOT NULL,
  `description`  text,
  `status`       enum('open','active','closed','archived') NOT NULL DEFAULT 'open',
  `severity`     enum('low','medium','high','critical')    NOT NULL DEFAULT 'medium',
  `created_by`   varchar(191) NOT NULL,                  -- the case author
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  `updated_at`   timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  `closed_at`    timestamp    NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `cases_number_unique` (`case_number`),
  CONSTRAINT `cases_creator_fk` FOREIGN KEY (`created_by`) REFERENCES `user`(`id`) ON DELETE RESTRICT,
  KEY `cases_status_idx`  (`status`),
  KEY `cases_creator_idx` (`created_by`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- created_by RESTRICT: a departing author must not silently delete the case.

CREATE TABLE `evidence` (
  `id`            char(36)     NOT NULL,
  `case_id`       char(36)     NOT NULL,
  `filename`      varchar(255) NOT NULL,
  `stored_path`   varchar(512) NOT NULL,
  `mime_type`     varchar(128),
  `size_bytes`    bigint unsigned NOT NULL,
  `sha256`        char(64)     NOT NULL,
  `md5`           char(32),
  `uploaded_by`   varchar(191) NOT NULL,
  `uploaded_at`   timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  CONSTRAINT `ev_case_fk`     FOREIGN KEY (`case_id`)     REFERENCES `cases`(`id`) ON DELETE CASCADE,
  CONSTRAINT `ev_uploader_fk` FOREIGN KEY (`uploaded_by`) REFERENCES `user`(`id`)  ON DELETE RESTRICT,
  KEY `ev_case_idx`   (`case_id`),
  KEY `ev_sha256_idx` (`sha256`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- 5.  PER-CASE MEMBERSHIP + DYNAMIC PER-CASE RBAC
-- =====================================================================
-- case roles are no longer a static enum. The case author can
-- create arbitrary roles scoped to a case, attach case-permissions to them
-- (viewer, lead, and per-analyzer "run" permissions), and assign one or more
-- of those roles to each case member.
--
-- Tables:
--   case_members           — who is on the case (membership only; no role here)
--   case_roles             — author-defined roles, scoped to one case
--   case_permissions       — catalogue of assignable case-level permissions
--   case_role_permissions  — which permissions a case_role grants
--   case_member_roles      — which case_roles a member holds (member <-> role, M:N)

CREATE TABLE `case_members` (
  `id`         char(36)     NOT NULL,                    -- surface PK so other tables can FK a membership
  `case_id`    char(36)     NOT NULL,
  `user_id`    varchar(191) NOT NULL,
  `added_by`   varchar(191),
  `added_at`   timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `cm_case_user_unique` (`case_id`,`user_id`),
  CONSTRAINT `cm_case_fk`  FOREIGN KEY (`case_id`)  REFERENCES `cases`(`id`) ON DELETE CASCADE,
  CONSTRAINT `cm_user_fk`  FOREIGN KEY (`user_id`)  REFERENCES `user`(`id`)  ON DELETE CASCADE,
  CONSTRAINT `cm_adder_fk` FOREIGN KEY (`added_by`) REFERENCES `user`(`id`)  ON DELETE SET NULL,
  KEY `cm_user_idx` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `case_roles` (
  `id`           char(36)     NOT NULL,
  `case_id`      char(36)     NOT NULL,                  -- role belongs to one case
  `name`         varchar(64)  NOT NULL,                  -- e.g. 'Lead', 'Viewer', 'Malware Analyst'
  `description`  varchar(255),
  `created_by`   varchar(191),                           -- author who defined it
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  `updated_at`   timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `cr_case_name_unique` (`case_id`,`name`),   -- role names unique within a case
  CONSTRAINT `cr_case_fk`    FOREIGN KEY (`case_id`)    REFERENCES `cases`(`id`) ON DELETE CASCADE,
  CONSTRAINT `cr_creator_fk` FOREIGN KEY (`created_by`) REFERENCES `user`(`id`)  ON DELETE SET NULL,
  KEY `cr_case_idx` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `case_permissions` (
  `id`           char(36)     NOT NULL,
  `name`         varchar(128) NOT NULL,                  -- 'case.view','case.lead','analysis.run.strings', ...
  `category`     varchar(64),                            -- 'access' | 'analysis' | ...
  `description`  varchar(255),
  `analyzer_key` varchar(64),                            -- FK -> analyzers.key when this perm gates an analyzer
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `cp_name_unique` (`name`),
  CONSTRAINT `cp_analyzer_fk` FOREIGN KEY (`analyzer_key`) REFERENCES `analyzers`(`key`) ON DELETE SET NULL,
  KEY `cp_analyzer_idx` (`analyzer_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- analyzer_key links a permission to an analyzer in `analyzers`, so
-- "permissions according to the analytical jobs that can be run" are first-class
-- AND referentially enforced.

CREATE TABLE `case_role_permissions` (
  `case_role_id`        char(36)  NOT NULL,
  `case_permission_id`  char(36)  NOT NULL,
  `granted_at`          timestamp NOT NULL DEFAULT (now()),
  PRIMARY KEY (`case_role_id`,`case_permission_id`),
  CONSTRAINT `crp_role_fk` FOREIGN KEY (`case_role_id`)       REFERENCES `case_roles`(`id`)       ON DELETE CASCADE,
  CONSTRAINT `crp_perm_fk` FOREIGN KEY (`case_permission_id`) REFERENCES `case_permissions`(`id`) ON DELETE CASCADE,
  KEY `crp_perm_idx` (`case_permission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `case_member_roles` (
  `case_member_id`  char(36)     NOT NULL,
  `case_role_id`    char(36)     NOT NULL,
  `assigned_by`     varchar(191),
  `assigned_at`     timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`case_member_id`,`case_role_id`),
  CONSTRAINT `cmr_member_fk`   FOREIGN KEY (`case_member_id`) REFERENCES `case_members`(`id`) ON DELETE CASCADE,
  CONSTRAINT `cmr_role_fk`     FOREIGN KEY (`case_role_id`)   REFERENCES `case_roles`(`id`)   ON DELETE CASCADE,
  CONSTRAINT `cmr_assigner_fk` FOREIGN KEY (`assigned_by`)    REFERENCES `user`(`id`)         ON DELETE SET NULL,
  KEY `cmr_role_idx` (`case_role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- 6.  ANALYZERS + ANALYSIS JOBS + MANY-TO-MANY ASSIGNMENT TO MEMBERS
-- =====================================================================
-- 3NF: the set of approved analyzers (formerly only `templates_registry.py` in
-- code, referenced by loose `analyzer_key` strings) is promoted to a real table.
-- Both `analysis_jobs.analyzer_key` and `case_permissions.analyzer_key` are now
-- foreign keys into `analyzers`, removing the transitive dependency on an
-- out-of-schema value and making typos / unregistered keys impossible at the DB.
-- The application registry still describes HOW to run each analyzer; this table
-- is the authoritative list of WHICH analyzers exist.

CREATE TABLE `analyzers` (
  `key`           varchar(64)  NOT NULL,                 -- stable id, e.g. 'strings', 'hash', 'exiftool'
  `display_name`  varchar(128) NOT NULL,
  `description`   varchar(255),
  `is_enabled`    boolean      NOT NULL DEFAULT true,    -- toggle availability without deleting
  `created_at`    timestamp    NOT NULL DEFAULT (now()),
  `updated_at`    timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- analysis_jobs no longer carries a single assignee. A join table
-- (job_assignees) links jobs to case_members so multiple members can be on one
-- job and one member can be on many jobs.

CREATE TABLE `analysis_jobs` (
  `id`             char(36)     NOT NULL,
  `case_id`        char(36)     NOT NULL,
  `evidence_id`    char(36)     NOT NULL,
  `analyzer_key`   varchar(64)  NOT NULL,                -- matches templates_registry
  `params`         json,
  `status`         enum('queued','running','completed','failed','timeout','cancelled') NOT NULL DEFAULT 'queued',
  `created_by`     varchar(191) NOT NULL,                -- who requested the job
  `queued_at`      timestamp    NOT NULL DEFAULT (now()),
  `started_at`     timestamp    NULL,
  `finished_at`    timestamp    NULL,
  `error_message`  text,
  PRIMARY KEY (`id`),
  CONSTRAINT `aj_case_fk`     FOREIGN KEY (`case_id`)     REFERENCES `cases`(`id`)    ON DELETE CASCADE,
  CONSTRAINT `aj_evidence_fk` FOREIGN KEY (`evidence_id`) REFERENCES `evidence`(`id`) ON DELETE CASCADE,
  CONSTRAINT `aj_analyzer_fk` FOREIGN KEY (`analyzer_key`) REFERENCES `analyzers`(`key`) ON DELETE RESTRICT,
  CONSTRAINT `aj_creator_fk`  FOREIGN KEY (`created_by`)  REFERENCES `user`(`id`)     ON DELETE RESTRICT,
  KEY `aj_case_idx`     (`case_id`),
  KEY `aj_status_idx`   (`status`),
  KEY `aj_evidence_idx` (`evidence_id`),
  KEY `aj_analyzer_idx` (`analyzer_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `job_assignees` (
  `job_id`          char(36)     NOT NULL,
  `case_member_id`  char(36)     NOT NULL,               -- assignment targets a case membership
  `assigned_by`     varchar(191),
  `assigned_at`     timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`job_id`,`case_member_id`),
  CONSTRAINT `ja_job_fk`      FOREIGN KEY (`job_id`)         REFERENCES `analysis_jobs`(`id`) ON DELETE CASCADE,
  CONSTRAINT `ja_member_fk`   FOREIGN KEY (`case_member_id`) REFERENCES `case_members`(`id`)  ON DELETE CASCADE,
  CONSTRAINT `ja_assigner_fk` FOREIGN KEY (`assigned_by`)    REFERENCES `user`(`id`)          ON DELETE SET NULL,
  KEY `ja_member_idx` (`case_member_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `analysis_results` (
  `id`            char(36)     NOT NULL,
  `job_id`        char(36)     NOT NULL,
  `result_type`   varchar(64)  NOT NULL,
  `summary`       text,
  `data`          json,
  `output_path`   varchar(512),
  `created_at`    timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  CONSTRAINT `ar_job_fk` FOREIGN KEY (`job_id`) REFERENCES `analysis_jobs`(`id`) ON DELETE CASCADE,
  KEY `ar_job_idx` (`job_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- 4b.  CASE NOTE  (the single final report note — one-to-one with a case)
-- =====================================================================
-- notes are no longer a list of rows with their own id. There is
-- exactly ONE note per case (the final report note), so the table is keyed by
-- case_id (PK = case_id => strict 1:1). Edit attribution ("by whom and when")
-- is tracked by FKing the last editor to a case_members row, not to user
-- directly, so an edit is always tied to a known member of that case.

CREATE TABLE `case_note` (
  `case_id`               char(36)     NOT NULL,         -- PK = 1:1 with cases
  `content`               longtext     NOT NULL,
  `last_edited_by_member` char(36),                      -- which case membership last edited
  `created_at`            timestamp    NOT NULL DEFAULT (now()),
  `updated_at`            timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`case_id`),
  CONSTRAINT `note_case_fk`   FOREIGN KEY (`case_id`)               REFERENCES `cases`(`id`)        ON DELETE CASCADE,
  CONSTRAINT `note_editor_fk` FOREIGN KEY (`last_edited_by_member`) REFERENCES `case_members`(`id`) ON DELETE SET NULL,
  KEY `note_editor_idx` (`last_edited_by_member`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Optional history of note edits (who changed it, when) for the audit trail.
CREATE TABLE `case_note_revisions` (
  `id`              char(36)     NOT NULL,
  `case_id`         char(36)     NOT NULL,
  `edited_by_member` char(36),
  `content`         longtext     NOT NULL,
  `created_at`      timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  CONSTRAINT `nr_case_fk`   FOREIGN KEY (`case_id`)          REFERENCES `case_note`(`case_id`) ON DELETE CASCADE,
  CONSTRAINT `nr_editor_fk` FOREIGN KEY (`edited_by_member`) REFERENCES `case_members`(`id`)   ON DELETE SET NULL,
  KEY `nr_case_idx` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- 4c.  REPORTS  (formal reports, separate from the single case_note)
-- =====================================================================
CREATE TABLE `reports` (
  `id`            char(36)     NOT NULL,
  `case_id`       char(36)     NOT NULL,
  `title`         varchar(255) NOT NULL,
  `status`        enum('draft','final') NOT NULL DEFAULT 'draft',
  `created_by`    varchar(191) NOT NULL,
  `created_at`    timestamp    NOT NULL DEFAULT (now()),
  `updated_at`    timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `rep_case_fk`    FOREIGN KEY (`case_id`)    REFERENCES `cases`(`id`) ON DELETE CASCADE,
  CONSTRAINT `rep_creator_fk` FOREIGN KEY (`created_by`) REFERENCES `user`(`id`)  ON DELETE RESTRICT,
  KEY `rep_case_idx` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `report_versions` (
  `id`           char(36)     NOT NULL,
  `report_id`    char(36)     NOT NULL,
  `version`      int unsigned NOT NULL,
  `content`      longtext     NOT NULL,
  `created_by`   varchar(191) NOT NULL,
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `rv_report_version_unique` (`report_id`,`version`),
  CONSTRAINT `rv_report_fk`  FOREIGN KEY (`report_id`)  REFERENCES `reports`(`id`) ON DELETE CASCADE,
  CONSTRAINT `rv_creator_fk` FOREIGN KEY (`created_by`) REFERENCES `user`(`id`)    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- 7.  CHAT  (author <-> members, and members <-> members per job)
-- =====================================================================
-- two thread scopes —
--   * scope='case' : a case-wide thread (author + members).
--   * scope='job'  : a thread bound to one analysis_job (its assignees + author).
-- A message's sender is a case_member, so chat is always within case context.

CREATE TABLE `chat_threads` (
  `id`         char(36)     NOT NULL,
  `case_id`    char(36)     NOT NULL,
  `scope`      enum('case','job') NOT NULL,
  `job_id`     char(36)     NULL,                        -- required when scope='job', else NULL
  `title`      varchar(191),
  `created_by` varchar(191),
  `created_at` timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `ct_job_unique` (`job_id`),                 -- at most one thread per job
  CONSTRAINT `ct_case_fk`    FOREIGN KEY (`case_id`)    REFERENCES `cases`(`id`)         ON DELETE CASCADE,
  CONSTRAINT `ct_job_fk`     FOREIGN KEY (`job_id`)     REFERENCES `analysis_jobs`(`id`) ON DELETE CASCADE,
  CONSTRAINT `ct_creator_fk` FOREIGN KEY (`created_by`) REFERENCES `user`(`id`)          ON DELETE SET NULL,
  KEY `ct_case_idx` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `chat_messages` (
  `id`               char(36)     NOT NULL,
  `thread_id`        char(36)     NOT NULL,
  `sender_member_id` char(36),                           -- the case_member who sent it
  `body`             text         NOT NULL,
  `created_at`       timestamp    NOT NULL DEFAULT (now()),
  `edited_at`        timestamp    NULL,
  PRIMARY KEY (`id`),
  CONSTRAINT `msg_thread_fk` FOREIGN KEY (`thread_id`)        REFERENCES `chat_threads`(`id`) ON DELETE CASCADE,
  CONSTRAINT `msg_sender_fk` FOREIGN KEY (`sender_member_id`) REFERENCES `case_members`(`id`) ON DELETE SET NULL,
  KEY `msg_thread_idx` (`thread_id`,`created_at`),
  KEY `msg_sender_idx` (`sender_member_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- 8.  AUDIT LOG
-- =====================================================================
CREATE TABLE `audit_logs` (
  `id`           char(36)     NOT NULL,
  `actor_id`     varchar(191),                           -- nullable: system events
  `action`       varchar(64)  NOT NULL,
  `entity_type`  varchar(64),
  `entity_id`    varchar(191),
  `ip_address`   varchar(45),
  `user_agent`   text,
  `metadata`     json,
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  CONSTRAINT `audit_actor_fk` FOREIGN KEY (`actor_id`) REFERENCES `user`(`id`) ON DELETE SET NULL,
  KEY `audit_actor_idx`  (`actor_id`),
  KEY `audit_action_idx` (`action`),
  KEY `audit_entity_idx` (`entity_type`,`entity_id`),
  KEY `audit_time_idx`   (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;
