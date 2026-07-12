-- Real payment gateway (eSewa) + finance ledger. payment_transactions is
-- the source of truth for money movement, independent of org_subscriptions
-- (a transaction exists from the moment the signed form is built, before
-- the org even reaches eSewa, so an abandoned/failed payment is never
-- silently invisible). Two separate discount mechanisms per product
-- decision: coupons (code-based, redeemable by any eligible org) and
-- org_discounts (standing, no-code, admin-granted to one specific org).

CREATE TABLE `coupons` (
  `id`               varchar(32)   NOT NULL,
  `code`             varchar(64)   NOT NULL,
  `discount_type`    enum('percent','flat') NOT NULL,
  `discount_value`   decimal(10,2) NOT NULL,
  `max_redemptions`  int           NULL,
  `times_redeemed`   int           NOT NULL DEFAULT 0,
  `valid_from`       timestamp     NULL DEFAULT NULL,
  `valid_until`      timestamp     NULL DEFAULT NULL,
  `is_active`        tinyint(1)    NOT NULL DEFAULT 1,
  `created_by`       varchar(191)  NULL,
  `created_at`       timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`       timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_coupons_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `org_discounts` (
  `id`             varchar(32)   NOT NULL,
  `org_id`         char(36)      NOT NULL,
  `discount_type`  enum('percent','flat') NOT NULL,
  `discount_value` decimal(10,2) NOT NULL,
  `reason`         varchar(255)  NULL,
  `valid_until`    timestamp     NULL DEFAULT NULL,
  `is_active`      tinyint(1)    NOT NULL DEFAULT 1,
  `created_by`     varchar(191)  NULL,
  `created_at`     timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`     timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_org_discounts_org` (`org_id`),
  CONSTRAINT `fk_org_discounts_org`
    FOREIGN KEY (`org_id`) REFERENCES `organizations` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `payment_transactions` (
  `id`                     varchar(32)   NOT NULL,
  `org_id`                 char(36)      NOT NULL,
  `plan_id`                varchar(100)  NOT NULL,
  `billing_period`         enum('monthly','annual') NOT NULL,
  `base_amount`            decimal(10,2) NOT NULL,
  `discount_amount`        decimal(10,2) NOT NULL DEFAULT 0.00,
  `total_amount`           decimal(10,2) NOT NULL,
  `transaction_uuid`       varchar(64)   NOT NULL,
  `esewa_transaction_code` varchar(64)   NULL,
  `coupon_id`              varchar(32)   NULL,
  `org_discount_id`        varchar(32)   NULL,
  `status`                 enum('initiated','completed','failed','refunded') NOT NULL DEFAULT 'initiated',
  `failure_reason`         varchar(255)  NULL,
  `verified_at`            timestamp     NULL DEFAULT NULL,
  `created_by`             varchar(191)  NOT NULL,
  `created_at`             timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`             timestamp     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_payment_transactions_uuid` (`transaction_uuid`),
  KEY `idx_payment_transactions_org` (`org_id`),
  KEY `idx_payment_transactions_status` (`status`),
  CONSTRAINT `fk_payment_transactions_org`
    FOREIGN KEY (`org_id`) REFERENCES `organizations` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_payment_transactions_plan`
    FOREIGN KEY (`plan_id`) REFERENCES `plans` (`id`),
  CONSTRAINT `fk_payment_transactions_coupon`
    FOREIGN KEY (`coupon_id`) REFERENCES `coupons` (`id`)
    ON DELETE SET NULL,
  CONSTRAINT `fk_payment_transactions_org_discount`
    FOREIGN KEY (`org_discount_id`) REFERENCES `org_discounts` (`id`)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Which org has redeemed which coupon — one row per redemption, lets a
-- max_redemptions=1 coupon be enforced (and gives a per-org audit trail
-- even for multi-use coupons).
CREATE TABLE `coupon_redemptions` (
  `id`             varchar(32)  NOT NULL,
  `coupon_id`      varchar(32)  NOT NULL,
  `org_id`         char(36)     NOT NULL,
  `transaction_id` varchar(32)  NOT NULL,
  `redeemed_at`    timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_coupon_redemptions_coupon` (`coupon_id`),
  CONSTRAINT `fk_coupon_redemptions_coupon`
    FOREIGN KEY (`coupon_id`) REFERENCES `coupons` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_coupon_redemptions_org`
    FOREIGN KEY (`org_id`) REFERENCES `organizations` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_coupon_redemptions_transaction`
    FOREIGN KEY (`transaction_id`) REFERENCES `payment_transactions` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
