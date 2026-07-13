-- =============================================================================
-- Data Mirroring Setup — Postgres Side
-- Run these connected to rkdb_mirror database on rkdbmirrortest instance
-- as snowflake_admin:
--   psql "service=rkdbmirrortest dbname=rkdb_mirror"
-- =============================================================================

-- Install CDC extension (also installs pg_lake as dependency)
CREATE EXTENSION IF NOT EXISTS snowflake_cdc CASCADE;

-- Verify extension is installed
SELECT extname, extversion FROM pg_extension WHERE extname IN ('snowflake_cdc', 'pg_lake');

-- Verify tables are present and have PKs
SELECT
    t.table_name,
    kcu.column_name AS pk_column
FROM information_schema.tables t
LEFT JOIN information_schema.table_constraints tc
    ON t.table_name = tc.table_name AND tc.constraint_type = 'PRIMARY KEY'
LEFT JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
WHERE t.table_schema = 'public'
  AND t.table_name IN ('labresult_neil_oltp','memberdiagnosis','membermedications','labresult_neil')
ORDER BY t.table_name, kcu.ordinal_position;

-- Check row counts
SELECT 'labresult_neil_oltp'  AS tbl, COUNT(*) FROM labresult_neil_oltp
UNION ALL
SELECT 'memberdiagnosis',             COUNT(*) FROM memberdiagnosis
UNION ALL
SELECT 'membermedications',           COUNT(*) FROM membermedications;
