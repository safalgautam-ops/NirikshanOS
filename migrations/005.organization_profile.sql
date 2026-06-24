-- Professional org-registration fields, collected by the 3-step onboarding
-- wizard (app/features/onboarding) - all nullable since existing orgs (and
-- admin-created ones via /admin/organizations) predate this form.
ALTER TABLE `organizations`
  ADD COLUMN `logo_path`           varchar(255) NULL AFTER `description`,
  ADD COLUMN `org_type`            varchar(50)  NULL AFTER `logo_path`,
  ADD COLUMN `employee_count`      varchar(20)  NULL AFTER `org_type`,
  ADD COLUMN `address`             varchar(255) NULL AFTER `employee_count`,
  ADD COLUMN `country`             varchar(100) NULL AFTER `address`,
  ADD COLUMN `state`               varchar(100) NULL AFTER `country`,
  ADD COLUMN `city`                varchar(100) NULL AFTER `state`,
  ADD COLUMN `postal_code`         varchar(20)  NULL AFTER `city`,
  ADD COLUMN `registration_number` varchar(100) NULL AFTER `postal_code`,
  ADD COLUMN `pan_number`          varchar(100) NULL AFTER `registration_number`,
  ADD COLUMN `owner_name`          varchar(150) NULL AFTER `pan_number`;

-- Government documents (registration certificate, PAN card, owner ID, etc.)
-- uploaded during step 3 - stored outside app/static so nginx never serves
-- them directly (see app/core/storage.py); this table just tracks what was
-- uploaded and where, for the authenticated download route to look up.
CREATE TABLE `organization_documents` (
  `id`                char(36)     NOT NULL,
  `organization_id`   char(36)     NOT NULL,
  `file_path`          varchar(255) NOT NULL,
  `original_filename`  varchar(255) NOT NULL,
  `uploaded_at`        timestamp    NOT NULL DEFAULT (now()),
  PRIMARY KEY (`id`),
  CONSTRAINT `od_org_fk` FOREIGN KEY (`organization_id`) REFERENCES `organizations`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
