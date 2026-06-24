-- Self-registered organizations (app/features/onboarding) need an admin to
-- review the submitted KYC details/documents before the org's members are
-- unlocked. Default 'approved' so existing rows and admin-created orgs
-- (app/features/organizations, which never collects KYC details) are
-- unaffected - only the onboarding wizard explicitly sets 'pending'.
ALTER TABLE `organizations`
  ADD COLUMN `verification_status` enum('pending','approved','rejected') NOT NULL DEFAULT 'approved' AFTER `status`,
  ADD COLUMN `rejection_reason`    varchar(255) NULL AFTER `verification_status`,
  ADD COLUMN `reviewed_by`         varchar(191) NULL AFTER `rejection_reason`,
  ADD COLUMN `reviewed_at`         timestamp NULL AFTER `reviewed_by`,
  ADD CONSTRAINT `org_reviewer_fk` FOREIGN KEY (`reviewed_by`) REFERENCES `user`(`id`) ON DELETE SET NULL;
