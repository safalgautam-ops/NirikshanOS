-- All file storage (avatars, org logos, org KYC documents, case evidence)
-- moved off local disk and onto MinIO (S3-compatible object storage) - see
-- app/core/object_storage.py. Avatars/logos/documents needed no schema
-- change (they already stored a path/key string); evidence's chunked-upload
-- bookkeeping does, because S3 multipart upload replaces it wholesale:
-- MinIO itself is the source of truth for "which parts have landed" via
-- ListParts(upload_id), so the evidence_chunks ledger this app kept
-- alongside it can only ever drift from reality - dropping it removes that
-- whole class of bug instead of guarding against it.

ALTER TABLE `evidence`
  CHANGE COLUMN `chunk_size`   `part_size`   int NULL,
  CHANGE COLUMN `total_chunks` `total_parts` int NULL,
  ADD COLUMN `s3_key`    varchar(512) NULL AFTER `id`,
  ADD COLUMN `upload_id` varchar(255) NULL AFTER `s3_key`;

DROP TABLE `evidence_chunks`;
