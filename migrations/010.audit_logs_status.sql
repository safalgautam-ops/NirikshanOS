-- audit_logs already exists (see 001.initial_schema.sql) but has no way to
-- record whether the logged action actually succeeded - every real action
-- this app will start logging (case/evidence/membership changes - see
-- app/features/audit/service.py) needs that, including the denied/failed
-- attempts, not just the happy path.
ALTER TABLE `audit_logs`
  ADD COLUMN `status` enum('success','failure') NOT NULL DEFAULT 'success' AFTER `entity_id`;
