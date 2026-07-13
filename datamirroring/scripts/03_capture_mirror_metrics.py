#!/usr/bin/env python3
"""
Capture data mirroring metrics from Snowflake.
Queries:
  1. Mirror status and table states
  2. Task history for APPLY_MIRROR runs (last 24h)
  3. Row counts: target vs $live for each mirrored table
  4. $changes distribution

Saves results to results/mirror_metrics_<timestamp>.csv
"""
import csv
import json
import subprocess
import datetime
import os
import sys

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "../results")
MIRROR_NAME = "rkdbmirrortest"
TARGET_DB   = "RKDBMIRRONGTEST"
TABLES = ["LABRESULT_NEIL_OLTP", "MEMBERDIAGNOSIS", "MEMBERMEDICATIONS"]

TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def run_sf_sql(sql, connection="sfsenorthamerica-rkhandhadia_aws1"):
    """Run SQL via snow CLI and return JSON results."""
    result = subprocess.run(
        ["snow", "sql", "-q", sql, "--connection", connection, "--format", "json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print("=== Capturing mirror metrics ===\n")

    # 1. Mirror describe
    print("[1] DESCRIBE_MIRROR ...")
    rows = run_sf_sql(f"CALL SNOWFLAKE.POSTGRES.DESCRIBE_MIRROR('{MIRROR_NAME}');")
    with open(f"{RESULTS_DIR}/mirror_describe_{TS}.json", "w") as f:
        json.dump(rows, f, indent=2)
    print(f"    saved mirror_describe_{TS}.json")

    # 2. Mirrored table states
    print("[2] LIST_MIRRORED_TABLES ...")
    rows = run_sf_sql(f"CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('{MIRROR_NAME}');")
    with open(f"{RESULTS_DIR}/mirrored_tables_{TS}.json", "w") as f:
        json.dump(rows, f, indent=2)
    print(f"    saved mirrored_tables_{TS}.json")

    # 3. Apply task history (last 24h)
    print("[3] TASK_HISTORY for APPLY_MIRROR ... ")
    task_sql = f"""
SELECT name, state, scheduled_time, completed_time,
       DATEDIFF('second', scheduled_time, completed_time) AS apply_secs
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 200
))
WHERE database_name = 'SNOWFLAKE'
  AND name LIKE 'APPLY_MIRROR_%'
ORDER BY scheduled_time DESC;
"""
    task_rows = run_sf_sql(task_sql)
    task_csv = f"{RESULTS_DIR}/apply_task_history_{TS}.csv"
    if task_rows:
        with open(task_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=task_rows[0].keys())
            writer.writeheader()
            writer.writerows(task_rows)
        print(f"    saved apply_task_history_{TS}.csv  ({len(task_rows)} runs)")
    else:
        print("    no task history found yet")

    # 4. Row count: target vs $live
    print("[4] Row counts: target vs $live ...")
    count_rows = []
    for tbl in TABLES:
        target_sql = f"SELECT COUNT(*) AS cnt FROM {TARGET_DB}.PUBLIC.{tbl};"
        live_sql   = f'SELECT COUNT(*) AS cnt FROM {TARGET_DB}.PUBLIC."{tbl}$live";'
        t_res = run_sf_sql(target_sql)
        l_res = run_sf_sql(live_sql)
        t_cnt = t_res[0]["CNT"] if t_res else "ERROR"
        l_cnt = l_res[0]["CNT"] if l_res else "ERROR"
        lag   = (int(l_cnt) - int(t_cnt)) if isinstance(t_cnt, int) and isinstance(l_cnt, int) else "N/A"
        count_rows.append({"table": tbl, "target_count": t_cnt, "live_count": l_cnt, "pending_rows": lag})
        print(f"    {tbl}: target={t_cnt}  live={l_cnt}  pending={lag}")

    count_csv = f"{RESULTS_DIR}/row_counts_{TS}.csv"
    with open(count_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["table","target_count","live_count","pending_rows"])
        writer.writeheader()
        writer.writerows(count_rows)
    print(f"    saved row_counts_{TS}.csv")

    # 5. $changes distribution (labresult_neil_oltp as representative)
    print("[5] $changes distribution (labresult_neil_oltp) ...")
    changes_sql = f"""
SELECT _change_type,
       COUNT(*)                     AS change_count,
       MIN(_commit_time)            AS earliest_commit,
       MAX(_commit_time)            AS latest_commit,
       DATEDIFF('second', MIN(_commit_time), MAX(_commit_time)) AS span_secs
FROM {TARGET_DB}.PUBLIC."LABRESULT_NEIL_OLTP$changes"
GROUP BY _change_type;
"""
    chg_rows = run_sf_sql(changes_sql)
    if chg_rows:
        chg_csv = f"{RESULTS_DIR}/changes_distribution_{TS}.csv"
        with open(chg_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=chg_rows[0].keys())
            writer.writeheader()
            writer.writerows(chg_rows)
        print(f"    saved changes_distribution_{TS}.csv")
    else:
        print("    $changes table empty or not yet available")

    print(f"\n=== Metrics captured. Check {RESULTS_DIR}/ ===")

if __name__ == "__main__":
    main()
