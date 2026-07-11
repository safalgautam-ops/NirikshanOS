-- Replace analysis_module_defs.category free-text with a real managed list.

CREATE TABLE `categories` (
  `id`          varchar(64)  NOT NULL,
  `name`        varchar(100) NOT NULL,
  `description` text         NULL,
  `sort_order`  int          NOT NULL DEFAULT 0,
  `created_at`  timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`  timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_categories_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Backfill: one category row per distinct existing free-text value, slugified
-- into an id the same way admin_modules/routes.py slugifies module ids.
INSERT INTO `categories` (`id`, `name`)
SELECT DISTINCT
  LOWER(REPLACE(REPLACE(TRIM(`category`), ' ', '_'), '-', '_')),
  TRIM(`category`)
FROM `analysis_module_defs`
WHERE `category` IS NOT NULL AND TRIM(`category`) != '';

ALTER TABLE `analysis_module_defs`
  ADD COLUMN `category_id` varchar(64) NULL AFTER `category`;

UPDATE `analysis_module_defs` d
JOIN `categories` c
  ON c.`id` = LOWER(REPLACE(REPLACE(TRIM(d.`category`), ' ', '_'), '-', '_'))
SET d.`category_id` = c.`id`;

ALTER TABLE `analysis_module_defs`
  ADD CONSTRAINT `fk_module_defs_category`
    FOREIGN KEY (`category_id`) REFERENCES `categories` (`id`)
    ON DELETE SET NULL;

ALTER TABLE `analysis_module_defs`
  DROP COLUMN `category`;
