-- =====================================================================
-- Forces a password change on first login for accounts created with an
-- auto-generated temporary password (e.g. admin-created staff members).
-- =====================================================================

ALTER TABLE `user`
  ADD COLUMN `must_change_password` boolean NOT NULL DEFAULT false AFTER `isActive`;
