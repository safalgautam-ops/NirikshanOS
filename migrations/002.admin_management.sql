-- =====================================================================
-- NirikshanOS — Admin Management (Users / Organizations / RBAC)
-- =====================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- user: track last login for the admin users table ("Last login" column).
-- Set explicitly by create_session() — not derived from `session` rows,
-- since sessions get deleted on logout/expiry and would lose the history.
ALTER TABLE `user` ADD COLUMN `lastLoginAt` timestamp NULL AFTER `twoFactorEnabled`;

-- roles: Discord-style additions.
--   color         - hex color shown next to the role name
--   is_assignable - false = "blocked": role still exists but can't be granted
--                   to new members (the "Block assignment" menu action)
--   sidebar_keys  - JSON array of dashboard nav keys this role may see;
--                   NULL/empty = no restriction (sees everything)
ALTER TABLE `roles`
  ADD COLUMN `color`         varchar(7)  NOT NULL DEFAULT '#5865F2' AFTER `description`,
  ADD COLUMN `is_assignable` boolean     NOT NULL DEFAULT true      AFTER `is_default`,
  ADD COLUMN `sidebar_keys`  json        NULL                       AFTER `is_assignable`;

-- =====================================================================
-- Organizations
-- =====================================================================

CREATE TABLE `organizations` (
  `id`           char(36)     NOT NULL,
  `name`         varchar(191) NOT NULL,
  `slug`         varchar(191) NOT NULL,
  `status`       enum('active','inactive') NOT NULL DEFAULT 'active',
  `description`  varchar(255),
  `created_by`   varchar(191),
  `created_at`   timestamp    NOT NULL DEFAULT (now()),
  `updated_at`   timestamp    NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `org_slug_unique` (`slug`),
  CONSTRAINT `org_creator_fk` FOREIGN KEY (`created_by`) REFERENCES `user`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `organization_members` (
  `id`               char(36)     NOT NULL,
  `organization_id`  char(36)     NOT NULL,
  `user_id`          varchar(191) NOT NULL,
  `joined_at`        timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `om_org_user_unique` (`organization_id`,`user_id`),
  CONSTRAINT `om_org_fk`  FOREIGN KEY (`organization_id`) REFERENCES `organizations`(`id`) ON DELETE CASCADE,
  CONSTRAINT `om_user_fk` FOREIGN KEY (`user_id`)         REFERENCES `user`(`id`)          ON DELETE CASCADE,
  KEY `om_user_idx` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- Seed: default roles + a starter permission catalogue
-- =====================================================================

INSERT INTO `roles` (`id`, `name`, `description`, `priority`, `is_system`, `is_default`, `color`) VALUES
  (UUID(), 'System Admin',       'Full platform access — built in, cannot be deleted', 1000, true,  false, '#ef4444'),
  (UUID(), 'Application Staff',  'Internal staff access',                              100,  false, false, '#3b82f6'),
  (UUID(), 'Member',             'Default role granted to new users',                  0,    false, true,  '#22c55e');

-- Only seeds permissions for features that actually exist and enforce them
-- (see app/core/security/permission_registry.py) - every other feature's
-- permissions self-register from its own permissions.py at app startup, and
-- sync_to_db() removes any DB row that isn't backed by a real registration.
-- (case/evidence/analysis/report/audit permissions used to be seeded here
-- too, for features that were never built - nothing in code ever enforced
-- them, so System Admin's permission list showed capabilities that didn't
-- exist. Removed rather than left as dead rows for a feature to "claim"
-- later - whoever builds that feature should declare its own permissions.)
INSERT INTO `permissions` (`id`, `resource`, `action`, `category`, `description`) VALUES
  (UUID(), 'user',         'view',   'User Management',         'View users'),
  (UUID(), 'user',         'edit',   'User Management',         'Edit users'),
  (UUID(), 'user',         'delete', 'User Management',         'Delete users'),
  (UUID(), 'organization', 'view',   'Organization Management', 'View organizations'),
  (UUID(), 'organization', 'create', 'Organization Management', 'Create organizations'),
  (UUID(), 'organization', 'edit',   'Organization Management', 'Edit organizations'),
  (UUID(), 'organization', 'delete', 'Organization Management', 'Delete organizations'),
  (UUID(), 'role',         'view',   'Roles & Permissions',     'View roles'),
  (UUID(), 'role',         'create', 'Roles & Permissions',     'Create roles'),
  (UUID(), 'role',         'edit',   'Roles & Permissions',     'Edit roles'),
  (UUID(), 'role',         'delete', 'Roles & Permissions',     'Delete roles');

-- System Admin gets every permission.
INSERT INTO `role_permissions` (`role_id`, `permission_id`)
SELECT r.id, p.id FROM `roles` r CROSS JOIN `permissions` p WHERE r.name = 'System Admin';

-- Every existing user becomes a System Admin (there's only ever a handful
-- of users at this point in the project — this just seeds the first admin).
INSERT INTO `user_roles` (`user_id`, `role_id`)
SELECT u.id, r.id FROM `user` u CROSS JOIN `roles` r WHERE r.name = 'System Admin';

SET FOREIGN_KEY_CHECKS = 1;
