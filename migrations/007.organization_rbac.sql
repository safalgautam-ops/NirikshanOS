-- Org-scoped RBAC, parallel to the system roles/permissions tables (see
-- migrations/002.admin_management.sql) but tenant-isolated: every row here
-- is scoped to one organization, so an org's custom roles can never grant
-- visibility into another org's data or the platform's admin area.

CREATE TABLE `organization_permissions` (
  `id`          char(36)     NOT NULL,
  `resource`    varchar(64)  NOT NULL,
  `action`      varchar(64)  NOT NULL,
  `name`        varchar(129) GENERATED ALWAYS AS (concat(`resource`, '.', `action`)) STORED,
  `category`    varchar(64),
  `description` varchar(255),
  `created_at`  timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `org_permission_name_unique` (`name`),
  UNIQUE KEY `org_permission_resource_action_unique` (`resource`, `action`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `organization_roles` (
  `id`              char(36)     NOT NULL,
  `organization_id` char(36)     NOT NULL,
  `name`            varchar(64)  NOT NULL,
  `description`     varchar(255),
  `color`           varchar(7)   NOT NULL DEFAULT '#5865F2',
  `priority`        int          NOT NULL DEFAULT 0,
  -- "Org Admin" - granted every org permission at creation, can't be deleted.
  `is_system`       tinyint(1)   NOT NULL DEFAULT 0,
  -- "Member" - what join-by-code/invite-link joiners get automatically.
  `is_default`      tinyint(1)   NOT NULL DEFAULT 0,
  `is_assignable`   tinyint(1)   NOT NULL DEFAULT 1,
  `sidebar_keys`    json,
  `created_at`      timestamp    NOT NULL DEFAULT (now()),
  `updated_at`      timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `org_role_name_unique` (`organization_id`, `name`),
  CONSTRAINT `org_role_org_fk` FOREIGN KEY (`organization_id`) REFERENCES `organizations`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `organization_role_permissions` (
  `role_id`       char(36)  NOT NULL,
  `permission_id` char(36)  NOT NULL,
  `granted_at`    timestamp NOT NULL DEFAULT (now()),
  PRIMARY KEY (`role_id`, `permission_id`),
  CONSTRAINT `org_rp_role_fk` FOREIGN KEY (`role_id`) REFERENCES `organization_roles`(`id`) ON DELETE CASCADE,
  CONSTRAINT `org_rp_permission_fk` FOREIGN KEY (`permission_id`) REFERENCES `organization_permissions`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- One org-role per membership (v1 - simpler than the system's many-to-many
-- user_roles, since an org member having multiple roles within the same
-- org hasn't been asked for). NULL only transiently, between a member
-- being added and create_default_org_roles() assigning their role.
ALTER TABLE `organization_members`
  ADD COLUMN `role_id` char(36) NULL AFTER `user_id`,
  ADD CONSTRAINT `om_role_fk` FOREIGN KEY (`role_id`) REFERENCES `organization_roles`(`id`) ON DELETE SET NULL;
