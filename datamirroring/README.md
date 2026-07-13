# Snowflake Postgres Data Mirroring — Performance Testing

**Test Date:** June 28–29, 2026  
**Feature:** [Data Mirroring (Private Preview)](https://docs.snowflake.com/en/LIMITEDACCESS/postgres-mirroring) — zero-ETL CDC replication from Snowflake Postgres to Snowflake Analytics  
**Account:** `sfsenorthamerica-rkhandhadia_aws1` (US East 1)  
**Snowflake Postgres Instance:** `rkdbmirrortest` — STANDARD_XL (4 cores, 16 GB RAM, 50 GB), PostgreSQL 18.4  
**Refresh interval:** 30 seconds (all mirrors)

---

## What Was Tested

Three end-to-end mirror scenarios covering different data types:

| # | Test Case | Source DB | Mirror Name | Target Snowflake DB | Data Type |
|---|-----------|-----------|-------------|---------------------|-----------|
| 1 | Healthcare OLTP | `rkdb_mirror` | `rkdbmirrortest` | `RKDBMIRRONGTEST` | Relational (21.5M rows) |
| 2 | BCBS Arkansas FHIR R4 | `bcbs_arkansas_fhir` | `bcbsarkansas` | `BCBSARKANSASFHIR` | JSONB (FHIR resources) |
| 3 | PVS GIS Shapefiles | `pvs_gis` | `pvsgis` | `PVSGIS` | Native PostGIS GEOMETRY (133 tables) |

---

## Key Results

| Metric | Value |
|--------|-------|
| Total rows mirrored (Test 1) | 21.5M rows |
| Bulk load throughput | ~1.1M rows/min |
| Max lag during bulk load | 850K rows (~30 seconds of data) |
| Post-load full sync time | **37 seconds** |
| Apply run duration (avg) | 4.6–18 seconds per cycle |
| JMeter peak throughput | **601 req/s** (INSERT + UPDATE combined) |
| JMeter error rate | **0.00%** |
| GIS shapefiles loaded | 133 (452,521 features, 826 seconds via ogr2ogr) |
| Initial snapshot — 4 tables | 2.7 seconds |
| Initial snapshot — 12 FHIR tables | 90.8 seconds |

---

## Repository Structure

```
datamirroring/
├── sql/
│   ├── 01_create_database_and_tables.sql   # DDL for all 4 healthcare tables with PKs
│   ├── 04a_snowflake_mirror_setup.sql      # Snowflake-side: GRANT + CREATE_MIRROR + monitoring
│   └── 04b_pg_setup.sql                    # Postgres-side: install snowflake_cdc extension
├── scripts/
│   ├── 02_bulk_load_20m.py                 # Python bulk loader (15M + 3M + 2M rows)
│   └── 03_capture_mirror_metrics.py        # Captures apply task history, lag, $changes
├── jmeter/
│   └── data_mirroring_perf_test.jmx        # JMeter plan: Warm-up → INSERT (50t×120s) → UPDATE (50t×120s)
└── results/
    ├── data_mirroring_perf_report.md        # Full narrative report
    ├── DataMirroring_PerfTest_Report.pptx   # Slide deck
    ├── bulk_load_metrics.csv                # Per-table rows/sec during load
    ├── mirror_lag_during_load.csv           # Target vs $live row count snapshots
    ├── mirror_snapshot_timing.csv           # Snapshot duration per mirror
    ├── apply_task_history.csv               # APPLY_MIRROR task run durations
    ├── jmeter_insert_phase.csv              # JMeter INSERT benchmark output
    ├── jmeter_update_phase.csv              # JMeter UPDATE benchmark output
    ├── jmeter_all_phases.csv                # Combined all phases
    ├── jmeter_run.log / jmeter_run2.log     # JMeter console logs
    ├── final_row_counts.csv                 # End-state row counts per table
    ├── pvs_gis_summary.csv                  # PostGIS shapefile load summary
    └── bulk_load_completion.txt             # Completion timestamp + row totals
```

---

## Prerequisites

### Software
- Snowflake CLI (`snow`) — authenticated to `sfsenorthamerica-rkhandhadia_aws1`
- `psql` / `pg_service.conf` — configured for the SPG instance
- Python 3.9+ with `psycopg2-binary`: `pip install psycopg2-binary`
- Apache JMeter 5.6+ with PostgreSQL JDBC driver in `lib/` directory
- (For GIS test only) `ogr2ogr` / GDAL 3.x

### Snowflake account requirements
- Data Mirroring must be enabled on the account (private preview — contact your account team to allowlist)
- Role with `postgres_mirror_admin` application role or ACCOUNTADMIN
- Snowflake Postgres instance on STANDARD or HIGH_MEMORY tier (BURSTABLE does **not** support mirroring)

---

## Step-by-Step Execution — Test Case 1 (Healthcare OLTP)

### Step 1 — Create the database and tables in Postgres

```bash
# Create the database
psql service=rkdbmirrortest -c "CREATE DATABASE rkdb_mirror;" postgres

# Create all four tables with primary keys
psql "service=rkdbmirrortest dbname=rkdb_mirror" -f sql/01_create_database_and_tables.sql
```

All tables are created with explicit primary keys — this is **required** for UPDATE/DELETE support in mirroring.

### Step 2 — Install the CDC extension in Postgres

```bash
psql "service=rkdbmirrortest dbname=rkdb_mirror" -f sql/04b_pg_setup.sql
```

This installs `snowflake_cdc` (which brings in `pg_lake` as a dependency).

### Step 3 — Set up the mirror in Snowflake

Open `sql/04a_snowflake_mirror_setup.sql` in Snowflake and run the setup section:

```sql
-- Grant mirror admin role
GRANT APPLICATION ROLE snowflake.postgres_mirror_admin TO ROLE solution_architect;
GRANT USAGE ON POSTGRES INSTANCE "rkdbmirrortest" TO APPLICATION snowflake;

-- Create the mirror (target DB must NOT exist yet)
CALL SNOWFLAKE.POSTGRES.CREATE_MIRROR(
    mirror_name       => 'rkdbmirrortest',
    postgres_instance => 'rkdbmirrortest',
    postgres_database => 'rkdb_mirror',
    target_database   => 'RKDBMIRRONGTEST',
    postgres_schemas  => ['public'],
    refresh_interval  => '30 seconds'
);
```

Wait for tables to transition from `SNAPSHOTTING` → `REPLICATING`:

```sql
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('rkdbmirrortest');
```

### Step 4 — Bulk load 21.5 million rows

```bash
python scripts/02_bulk_load_20m.py
```

The script reads connection details from `~/.pg_service.conf` and `~/.pgpass` — no credentials in code. It loads:
- `labresult_neil_oltp`: 15M rows (50K-row batches)
- `memberdiagnosis`: 3M rows
- `membermedications`: 2M rows

Progress is printed to stdout. Metrics are saved to `results/bulk_load_metrics.csv`.

### Step 5 — Capture mirror metrics

```bash
python scripts/03_capture_mirror_metrics.py
```

Queries Snowflake via `snow sql` and saves timestamped output to `results/`:
- Mirror describe + table states (JSON)
- Apply task history CSV (last 24 hours)
- Row counts: target table vs `$live` view vs lag
- `$changes` distribution (INSERT/UPDATE/DELETE counts)

### Step 6 — Run JMeter INSERT + UPDATE benchmark

> **Before running:** update the JDBC URL and credentials in the JMX file.  
> Search for `YOUR_SPG_HOST` and `REPLACE_WITH_SPG_PASSWORD` and substitute your instance values.

```bash
jmeter -n \
  -t jmeter/data_mirroring_perf_test.jmx \
  -l results/jmeter_all_phases.csv \
  -e -o results/jmeter_report/
```

The test plan runs three phases in sequence:
1. **Warm-up** — 1 thread × 10 loops (validates connectivity)
2. **INSERT benchmark** — 50 concurrent threads × 120 seconds
3. **UPDATE benchmark** — 50 concurrent threads × 120 seconds (UPDATEs by primary key)

---

## Monitoring Queries

Run these in Snowflake at any time during or after the test:

```sql
-- Live mirror status
CALL SNOWFLAKE.POSTGRES.DESCRIBE_MIRROR('rkdbmirrortest');

-- Per-table replication state
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('rkdbmirrortest');

-- Apply task run history (last 24h)
SELECT name, state, scheduled_time, completed_time,
       DATEDIFF('second', scheduled_time, completed_time) AS apply_secs
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 200
))
WHERE database_name = 'SNOWFLAKE'
  AND name LIKE 'APPLY_MIRROR_%'
ORDER BY scheduled_time DESC;

-- Lag check: target (materialized) vs $live (near-real-time)
SELECT COUNT(*) FROM RKDBMIRRONGTEST.PUBLIC.LABRESULT_NEIL_OLTP;
SELECT COUNT(*) FROM RKDBMIRRONGTEST.PUBLIC."LABRESULT_NEIL_OLTP$live";

-- Change type distribution
SELECT _change_type, COUNT(*), MIN(_commit_time), MAX(_commit_time)
FROM RKDBMIRRONGTEST.PUBLIC."LABRESULT_NEIL_OLTP$changes"
GROUP BY _change_type;
```

---

## Test Case 3 — PostGIS GEOMETRY Mirroring

Requires `pg_lake_spatial` extension. Key difference from the relational test:

```sql
-- Must use CASCADE — omitting it fails with a misleading "extension not found" error
CREATE EXTENSION IF NOT EXISTS pg_lake_spatial CASCADE;
```

This auto-installs 8 dependencies including `pg_lake`, `pg_lake_engine`, `pg_lake_spatial`. Load shapefiles with `ogr2ogr` after extension is installed — geometry columns (`EPSG:4326`) mirror natively to Snowflake without WKT conversion.

Query geometry in Snowflake:

```sql
-- Area in sq km
SELECT namelsad,
       ROUND(ST_AREA(TO_GEOGRAPHY(geom)) / 1e6, 1) AS area_km2
FROM PVSGIS.GIS_RAW.PVS_25_V2_COUNTY_26
ORDER BY area_km2 DESC;
```

---

## Known Gotchas

| Issue | Fix |
|-------|-----|
| `CREATE MIRROR` fails with "feature not enabled" | Account must be allowlisted for Data Mirroring private preview |
| `CREATE MIRROR` fails with role name dashes | Active role must use underscores — `solution_architect` is fine |
| BURSTABLE instance tier | Not supported for mirroring — use STANDARD or higher |
| Target DB already exists | Mirror will fail; drop the DB first or use a new name |
| `CREATE EXTENSION pg_lake_spatial` fails | Add `CASCADE` — it has 8 required dependencies |
| `$live` views not visible yet | Wait for `SNAPSHOTTING` → `REPLICATING` transition |
| JMeter JDBC auth failure | Update hostname and password placeholders in the JMX file |

---

## Connection Setup

The Python scripts and SQL files use the `rkdbmirrortest` service name. Configure once:

**`~/.pg_service.conf`:**
```ini
[rkdbmirrortest]
host=YOUR_SPG_HOST.snowflake.app
port=5432
user=snowflake_admin
sslmode=require
```

**`~/.pgpass`** (chmod 600):
```
YOUR_SPG_HOST.snowflake.app:5432:*:snowflake_admin:YOUR_PASSWORD
```

---

## Full Results

See [`results/data_mirroring_perf_report.md`](results/data_mirroring_perf_report.md) for the complete narrative report with all three test cases and cross-test comparison table. The PowerPoint deck is at [`results/DataMirroring_PerfTest_Report.pptx`](results/DataMirroring_PerfTest_Report.pptx).
