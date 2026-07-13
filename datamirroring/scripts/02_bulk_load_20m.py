#!/usr/bin/env python3
"""
Bulk load 20M rows into rkdb_mirror Postgres database.
Target tables:
  - labresult_neil_oltp  (primary load target, 15M rows)
  - memberdiagnosis      (3M rows)
  - membermedications    (2M rows)

Records wall-clock time at each phase boundary and writes a CSV metrics file.
Usage:
  pip install psycopg2-binary
  psql service=rkdbmirrortest -c "CREATE DATABASE rkdb_mirror;" postgres
  psql "service=rkdbmirrortest dbname=rkdb_mirror" -f sql/01_create_database_and_tables.sql
  python scripts/02_bulk_load_20m.py
"""
import os
import csv
import time
import random
import string
import datetime
import psycopg2
from psycopg2.extras import execute_values

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "../results")
METRICS_CSV = os.path.join(RESULTS_DIR, "bulk_load_metrics.csv")

# Read connection details from pg_service.conf + pgpass
import configparser
_svc = configparser.ConfigParser()
_svc.read(os.path.expanduser("~/.pg_service.conf"))
_s = _svc["rkdbmirrortest"]
_HOST = _s["host"]
_PORT = int(_s.get("port", "5432"))
_USER = _s["user"]
_SSL  = _s.get("sslmode", "require")
_PASS = ""
with open(os.path.expanduser("~/.pgpass")) as _f:
    for _line in _f:
        _p = _line.strip().split(":")
        if len(_p) >= 5 and (_p[0] == _HOST or _p[0] == "*"):
            _PASS = _p[4]
            break

def get_conn():
    return psycopg2.connect(
        host=_HOST, port=_PORT, dbname="rkdb_mirror",
        user=_USER, password=_PASS, sslmode=_SSL
    )

BATCH_SIZE = 50_000  # rows per INSERT batch

# Total rows per table
LABRESULT_OLTP_ROWS = 15_000_000
MEMBERDIAG_ROWS     =  3_000_000
MEMBERMEDS_ROWS     =  2_000_000

LOINCS   = ["2951-2","2823-3","2075-0","17861-6","1742-6","4544-3","718-7","785-6"]
NDCS     = ["00006-0749","00071-0155","00310-0952","00169-1830","00006-4099"]
DXCODES  = ["E11.9","I10","J06.9","Z00.00","M54.5","K21.0","F41.1"]

def rnd_str(n=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

def rnd_date(start=datetime.date(2018,1,1), end=datetime.date(2024,12,31)):
    delta = (end - start).days
    return start + datetime.timedelta(days=random.randint(0, delta))

def load_labresult_oltp(conn, total_rows):
    print(f"\n[labresult_neil_oltp] Loading {total_rows:,} rows in batches of {BATCH_SIZE:,}...")
    t0 = time.time()
    cur = conn.cursor()
    inserted = 0
    while inserted < total_rows:
        batch_n = min(BATCH_SIZE, total_rows - inserted)
        rows = []
        for i in range(batch_n):
            client_id     = f"CLIENT{random.randint(1,10000):05d}"
            file_import   = rnd_str(36)
            member_id     = f"MBR{random.randint(1,500000):07d}"
            loinc         = random.choice(LOINCS)
            ordered_date  = rnd_date()
            result_date   = ordered_date + datetime.timedelta(days=random.randint(1,30))
            lab_val       = f"{random.uniform(0.1, 500):.2f}"
            lab_name      = f"Lab{random.randint(1,200)}"
            rows.append((client_id, file_import, member_id, loinc, lab_val, lab_name,
                         ordered_date, result_date))
        execute_values(cur,
            """INSERT INTO labresult_neil_oltp
               (client_id,file_import_id,member_id,loinc,lab_result_value,lab_name,ordered_date,result_report_date)
               VALUES %s
               ON CONFLICT DO NOTHING""",
            rows, page_size=BATCH_SIZE)
        conn.commit()
        inserted += batch_n
        elapsed = time.time() - t0
        rps = inserted / elapsed
        print(f"  {inserted:>12,} / {total_rows:,}  ({rps:,.0f} rows/s)  elapsed={elapsed:.1f}s")
    total_time = time.time() - t0
    cur.close()
    return total_time

def load_memberdiagnosis(conn, total_rows):
    print(f"\n[memberdiagnosis] Loading {total_rows:,} rows in batches of {BATCH_SIZE:,}...")
    t0 = time.time()
    cur = conn.cursor()
    inserted = 0
    while inserted < total_rows:
        batch_n = min(BATCH_SIZE, total_rows - inserted)
        rows = []
        for i in range(batch_n):
            clientid   = random.randint(1, 10000)
            signifyid  = f"{random.randint(1,100):010d}"
            hashkey    = rnd_str(50)
            dx_code    = random.choice(DXCODES)
            desc       = f"Condition {dx_code}"
            last_occ   = datetime.datetime.combine(rnd_date(), datetime.time(random.randint(0,23), 0))
            rows.append((clientid, signifyid, hashkey, "ICD-10", dx_code, last_occ,
                         desc, "Chronic", rnd_str(32)))
        execute_values(cur,
            """INSERT INTO memberdiagnosis
               (clientid,signifyid,dimdiagnosishashkey,diagnosisversiondescription,
                diagnosiscode,lastoccurrence,description,diagnosissummarygroupname,dimmemberhashkey)
               VALUES %s
               ON CONFLICT DO NOTHING""",
            rows, page_size=BATCH_SIZE)
        conn.commit()
        inserted += batch_n
    total_time = time.time() - t0
    cur.close()
    return total_time

def load_membermedications(conn, total_rows):
    print(f"\n[membermedications] Loading {total_rows:,} rows in batches of {BATCH_SIZE:,}...")
    t0 = time.time()
    cur = conn.cursor()
    inserted = 0
    med_id_counter = 1
    while inserted < total_rows:
        batch_n = min(BATCH_SIZE, total_rows - inserted)
        rows = []
        for i in range(batch_n):
            clientid  = random.randint(1, 10000)
            signifyid = f"SIG{random.randint(1,255):012d}"
            med_id    = med_id_counter + i
            ndc       = random.choice(NDCS)
            desc      = f"Medication_{ndc.replace('-','')}"
            qty       = f"{random.randint(30,90)}"
            filled    = datetime.datetime.combine(rnd_date(), datetime.time(8,0))
            rows.append((clientid, signifyid, med_id, rnd_str(32), random.randint(1,50000),
                         desc, qty, filled, "N", ndc, rnd_str(32),
                         "10mg", "Daily", "Oral", f"Dr. {rnd_str(6)}",
                         "10", "MG", "Tablet"))
        execute_values(cur,
            """INSERT INTO membermedications
               (clientid,signifyid,id,dimmemberhashkey,memberplanid,description,quantity,
                datelastfilled,highrisk,ndc,factmembermedicationshashkey,strength,
                frequency,route,prescriber,activenumeratorstrength,activeingredunit,dosageformname)
               VALUES %s
               ON CONFLICT DO NOTHING""",
            rows, page_size=BATCH_SIZE)
        conn.commit()
        inserted += batch_n
        med_id_counter += batch_n
    total_time = time.time() - t0
    cur.close()
    return total_time

def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print(f"Connecting to Postgres: {_HOST}")
    conn = get_conn()
    conn.autocommit = False

    metrics = []
    load_start = time.time()

    # Table 1: labresult_neil_oltp — 15M rows
    t = load_labresult_oltp(conn, LABRESULT_OLTP_ROWS)
    metrics.append({"table": "labresult_neil_oltp", "rows": LABRESULT_OLTP_ROWS,
                    "duration_secs": round(t, 1),
                    "rows_per_sec": round(LABRESULT_OLTP_ROWS / t, 0)})

    # Table 2: memberdiagnosis — 3M rows
    t = load_memberdiagnosis(conn, MEMBERDIAG_ROWS)
    metrics.append({"table": "memberdiagnosis", "rows": MEMBERDIAG_ROWS,
                    "duration_secs": round(t, 1),
                    "rows_per_sec": round(MEMBERDIAG_ROWS / t, 0)})

    # Table 3: membermedications — 2M rows
    t = load_membermedications(conn, MEMBERMEDS_ROWS)
    metrics.append({"table": "membermedications", "rows": MEMBERMEDS_ROWS,
                    "duration_secs": round(t, 1),
                    "rows_per_sec": round(MEMBERMEDS_ROWS / t, 0)})

    conn.close()

    total_time = time.time() - load_start
    total_rows = LABRESULT_OLTP_ROWS + MEMBERDIAG_ROWS + MEMBERMEDS_ROWS
    metrics.append({"table": "TOTAL", "rows": total_rows,
                    "duration_secs": round(total_time, 1),
                    "rows_per_sec": round(total_rows / total_time, 0)})

    with open(METRICS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["table","rows","duration_secs","rows_per_sec"])
        writer.writeheader()
        writer.writerows(metrics)

    print(f"\n=== Bulk load complete ===")
    print(f"Total rows: {total_rows:,}")
    print(f"Total time: {total_time:.1f}s  ({total_rows/total_time:,.0f} rows/s)")
    print(f"Metrics saved to: {METRICS_CSV}")

if __name__ == "__main__":
    main()
