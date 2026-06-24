-- =====================================================================
-- One regenerable invite code per organization, so an existing member can
-- share it (as a typed code, or as a `/onboarding/join?code=...` link) with
-- someone who needs to join. No separate invites table - no per-invite
-- expiry/usage-limit tracking was asked for, so this keeps it to the
-- simplest thing that works: one active code per org, replace to revoke.
-- =====================================================================

ALTER TABLE `organizations`
  ADD COLUMN `invite_code` varchar(32) NULL AFTER `slug`,
  ADD UNIQUE KEY `org_invite_code_unique` (`invite_code`);

-- Backfill existing orgs with a code derived from their own (unique) id,
-- so this UPDATE can't collide with itself across rows.
UPDATE `organizations`
SET `invite_code` = UPPER(SUBSTRING(MD5(CONCAT(`id`, RAND())), 1, 10))
WHERE `invite_code` IS NULL;
