-- Migration 031 renamed queue values (fast/standard/heavy/sandbox ->
-- light/medium/heavy/full) on instances.queue_name but missed the
-- analysis_jobs.queue_name column, which still had the old enum — any real
-- job insert failed with "Data truncated for column 'queue_name'" since the
-- worker/planner now write the new names. analysis_jobs was empty at the
-- time this was found, so no data remap is needed, just the enum widen.
ALTER TABLE analysis_jobs
    MODIFY queue_name enum('light_queue','medium_queue','heavy_queue','full_queue') NOT NULL;
