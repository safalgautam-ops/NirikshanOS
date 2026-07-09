-- Plans: admin-defined subscription tiers with resource allocation and module access.
-- org_subscriptions: tracks which org is on which plan, with a full plan snapshot
-- so that plan changes or deletions never silently alter existing subscribers' access.

CREATE TABLE IF NOT EXISTS `plans` (
  `id`             varchar(100)   NOT NULL,
  `display_name`   varchar(128)   NOT NULL,
  `description`    text           NULL,
  `price_monthly`  decimal(10,2)  NOT NULL DEFAULT 0.00,
  `price_annual`   decimal(10,2)  NOT NULL DEFAULT 0.00,
  `resources`      json           NOT NULL,
  `allowed_tiers`  json           NOT NULL,
  `is_active`      tinyint(1)     NOT NULL DEFAULT 1,
  `sort_order`     int            NOT NULL DEFAULT 0,
  `created_at`     timestamp      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`     timestamp      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `org_subscriptions` (
  `id`             varchar(191)   NOT NULL,
  `org_id`         varchar(191)   NOT NULL,
  `plan_id`        varchar(100)   NOT NULL,
  `plan_snapshot`  json           NOT NULL,
  `status`         enum('active','expired','cancelled','grandfathered') NOT NULL DEFAULT 'active',
  `billing_period` enum('monthly','annual','lifetime')                  NOT NULL DEFAULT 'monthly',
  `starts_at`      timestamp      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `ends_at`        timestamp      NULL,
  `notes`          text           NULL,
  `created_by`     varchar(191)   NULL,
  `created_at`     timestamp      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`     timestamp      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_sub_org`  (`org_id`),
  KEY `idx_sub_plan` (`plan_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `plans`
  (`id`, `display_name`, `description`, `price_monthly`, `price_annual`,
   `resources`, `allowed_tiers`, `is_active`, `sort_order`)
VALUES
  ('free',
   'Free',
   'Basic forensic triage for individuals and evaluation.',
   0.00, 0.00,
   '{"ram_gb": 2, "vcpu": 2, "storage_gb": 20}',
   '["free", "basic_triage"]',
   1, 0),

  ('basic',
   'Basic',
   'Essential forensic tools for small teams.',
   49.00, 490.00,
   '{"ram_gb": 8, "vcpu": 4, "storage_gb": 100}',
   '["free", "basic_triage", "standard"]',
   1, 1),

  ('pro',
   'Pro',
   'Full forensic suite for professional investigators.',
   149.00, 1490.00,
   '{"ram_gb": 32, "vcpu": 8, "storage_gb": 500}',
   '["free", "basic_triage", "standard", "advanced"]',
   1, 2),

  ('enterprise',
   'Enterprise',
   'Unlimited access with dedicated resources for large teams.',
   0.00, 0.00,
   '{"ram_gb": 128, "vcpu": 32, "storage_gb": 2000}',
   '["free", "basic_triage", "standard", "advanced", "enterprise"]',
   1, 3)

ON DUPLICATE KEY UPDATE
  `display_name`  = VALUES(`display_name`),
  `description`   = VALUES(`description`),
  `resources`     = VALUES(`resources`),
  `allowed_tiers` = VALUES(`allowed_tiers`);
