-- The 4-tier rename (031) introduced "specialized_forensics" (21 chars),
-- which no longer fits analysis_module_defs.tier's original varchar(20).
ALTER TABLE analysis_module_defs MODIFY tier VARCHAR(32) NOT NULL DEFAULT 'basic';
