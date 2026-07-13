-- =============================================================================
-- Data Mirroring Setup — Snowflake Side
-- Run these in Snowflake (using sfsenorthamerica-rkhandhadia_aws1 connection)
-- as ACCOUNTADMIN or a role with mirror admin privileges.
-- =============================================================================

-- Step 1: Grant mirror admin role to working role
GRANT APPLICATION ROLE snowflake.postgres_mirror_admin TO ROLE solution_architect;

-- Step 2: Grant Snowflake application access to the Postgres instance
GRANT USAGE ON POSTGRES INSTANCE "rkdbmirrortest" TO APPLICATION snowflake;

-- Step 3: After installing snowflake_cdc extension in Postgres (see 04b_pg_setup.sql),
--         create the mirror.
-- NOTE: target_database must NOT exist yet — mirror creates it.
-- NOTE: mirror_name must be lowercase.
CALL SNOWFLAKE.POSTGRES.CREATE_MIRROR(
    mirror_name       => 'rkdbmirrortest',
    postgres_instance => 'rkdbmirrortest',
    postgres_database => 'rkdb_mirror',
    target_database   => 'RKDBMIRRONGTEST',
    postgres_schemas  => ['public'],
    refresh_interval  => '30 seconds'
);

-- =============================================================================
-- Monitoring queries — run after mirror is created
-- =============================================================================

-- Check mirror status
CALL SNOWFLAKE.POSTGRES.DESCRIBE_MIRROR('rkdbmirrortest');

-- Check per-table replication state (SNAPSHOTTING → REPLICATING)
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('rkdbmirrortest');

-- List all mirrors on the instance
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORS('rkdbmirrortest');

-- Check apply task history (last 24h)
SELECT name, state, scheduled_time, completed_time,
       DATEDIFF('second', scheduled_time, completed_time) AS apply_secs
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 200
))
WHERE database_name = 'SNOWFLAKE'
  AND name LIKE 'APPLY_MIRROR_%'
ORDER BY scheduled_time DESC;

-- Row counts: target table vs $live view
SELECT COUNT(*) AS target_count FROM RKDBMIRRONGTEST.PUBLIC.LABRESULT_NEIL_OLTP;
SELECT COUNT(*) AS live_count   FROM RKDBMIRRONGTEST.PUBLIC."LABRESULT_NEIL_OLTP$live";

SELECT COUNT(*) AS target_count FROM RKDBMIRRONGTEST.PUBLIC.MEMBERDIAGNOSIS;
SELECT COUNT(*) AS live_count   FROM RKDBMIRRONGTEST.PUBLIC."MEMBERDIAGNOSIS$live";

SELECT COUNT(*) AS target_count FROM RKDBMIRRONGTEST.PUBLIC.MEMBERMEDICATIONS;
SELECT COUNT(*) AS live_count   FROM RKDBMIRRONGTEST.PUBLIC."MEMBERMEDICATIONS$live";

-- $changes distribution for labresult_neil_oltp
SELECT _change_type,
       COUNT(*)                     AS change_count,
       MIN(_commit_time)            AS earliest_commit,
       MAX(_commit_time)            AS latest_commit,
       DATEDIFF('second', MIN(_commit_time), MAX(_commit_time)) AS span_secs
FROM RKDBMIRRONGTEST.PUBLIC."LABRESULT_NEIL_OLTP$changes"
GROUP BY _change_type;

-- Admin log (errors only)
CALL SNOWFLAKE.POSTGRES.QUERY_ADMIN_LOG(
    mirror_name       => 'rkdbmirrortest',
    postgres_instance => 'rkdbmirrortest',
    level             => 'ERROR',
    since_ts          => NULL,
    max_rows          => 100
);

-- =============================================================================
-- Cleanup (only if needed)
-- =============================================================================
-- CALL SNOWFLAKE.POSTGRES.DROP_MIRROR('rkdbmirrortest');
-- GRANT OWNERSHIP ON DATABASE RKDBMIRRONGTEST TO ROLE ACCOUNTADMIN;
-- DROP DATABASE RKDBMIRRONGTEST;
