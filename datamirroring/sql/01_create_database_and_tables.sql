-- =============================================================================
-- Data Mirroring Performance Test
-- Script 01: Create Database & Tables on rkdbmirrortest Postgres Instance
--
-- Tables adapted from Signify_postgres_680M with PKs on all tables
-- (required for UPDATE/DELETE support in data mirroring)
-- =============================================================================

-- Run as snowflake_admin connected to the instance:
-- CREATE DATABASE rkdb_mirror;
-- Then connect to rkdb_mirror:
-- \c rkdb_mirror

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- TABLE 1: labresult_neil  (46 columns, VARCHAR dates)
-- PK added on unique_row_id for mirroring support
-- =============================================================================

DROP TABLE IF EXISTS labresult_neil CASCADE;
CREATE TABLE labresult_neil (
    unique_row_id               VARCHAR(36)     NOT NULL,  -- promoted to PK
    lab_result_hash_key         VARCHAR(32),
    file_source_id              VARCHAR(20),
    client_id                   VARCHAR(50),
    master_person_id            VARCHAR(36),
    product_indicator           VARCHAR(20),
    file_row_id                 VARCHAR(20),
    file_import_id              VARCHAR(36),
    member_id                   VARCHAR(256),
    loinc                       VARCHAR(256),
    procedure_code_qualifier    VARCHAR(20),
    procedure_code              VARCHAR(20),
    procedure_code_modifier_1   VARCHAR(10),
    procedure_code_modifier_2   VARCHAR(10),
    ordering_provider_id        VARCHAR(20),
    ordering_provider_tin       VARCHAR(15),
    ordering_provider_npi       VARCHAR(15),
    diagnosis_indicator         VARCHAR(20),
    diagnosis_code              VARCHAR(20),
    lab_result_value            VARCHAR(1000),
    lab_result_low_cut_off      VARCHAR(20),
    lab_result_high_cut_off     VARCHAR(20),
    lab_result_unit_of_measure  VARCHAR(20),
    lab_result_status           VARCHAR(20),
    lab_plan_id                 VARCHAR(20),
    lab_name                    VARCHAR(1000),
    action_or_reason_code       VARCHAR(20),
    json_attributes             TEXT,       -- JSONB cast to TEXT for Iceberg compat
    json_enrichment             TEXT,
    ordered_date                VARCHAR(10),
    service_date                VARCHAR(10),
    result_report_date          VARCHAR(10),
    bill_amount                 VARCHAR(20),
    allowed_amount              VARCHAR(20),
    patient_pay_amount          VARCHAR(20),
    paid_amount                 VARCHAR(20),
    tax_amount                  VARCHAR(20),
    total_cost                  VARCHAR(20),
    paid_date                   VARCHAR(10),
    denied_date                 VARCHAR(10),
    member_medicare_id          VARCHAR(20),
    member_medicaid_id          VARCHAR(25),
    global_unique_id            VARCHAR(50),
    claim_id                    VARCHAR(30),
    _loaded_at                  TIMESTAMP DEFAULT now(),
    _dagster_run_id             VARCHAR(36),
    _file_import_id             VARCHAR(36),

    CONSTRAINT pk_labresult_neil PRIMARY KEY (unique_row_id)
);

CREATE INDEX idx_labresult_neil_member ON labresult_neil (member_id);
CREATE INDEX idx_labresult_neil_pk_cols ON labresult_neil (client_id, member_id, file_import_id, loinc, ordered_date);


-- =============================================================================
-- TABLE 2: labresult_neil_oltp  (8 columns, native DATE PK — already has PK)
-- =============================================================================

DROP TABLE IF EXISTS labresult_neil_oltp CASCADE;
CREATE TABLE labresult_neil_oltp (
    client_id           VARCHAR(50)     NOT NULL,
    file_import_id      VARCHAR(36)     NOT NULL,
    member_id           VARCHAR(256)    NOT NULL,
    loinc               VARCHAR(256)    NOT NULL,
    lab_result_value    VARCHAR(1000),
    lab_name            VARCHAR(1000),
    ordered_date        DATE            NOT NULL,
    result_report_date  DATE,

    CONSTRAINT pk_labresult_neil_oltp
        PRIMARY KEY (client_id, member_id, file_import_id, loinc, ordered_date)
);

CREATE INDEX idx_labresult_oltp_member ON labresult_neil_oltp (member_id);


-- =============================================================================
-- TABLE 3: memberdiagnosis  (already has PK)
-- =============================================================================

DROP TABLE IF EXISTS memberdiagnosis CASCADE;
CREATE TABLE memberdiagnosis (
    clientid                     BIGINT          NOT NULL,
    signifyid                    VARCHAR(10)     NOT NULL,
    dimdiagnosishashkey          VARCHAR(50)     NOT NULL,
    diagnosisversiondescription  VARCHAR(500),
    diagnosiscode                VARCHAR(20),
    lastoccurrence               TIMESTAMP,
    description                  VARCHAR(500),
    diagnosissummarygroupname    VARCHAR(500),
    dimmemberhashkey             VARCHAR(50),

    CONSTRAINT pk_memberdiagnosis PRIMARY KEY (clientid, signifyid, dimdiagnosishashkey)
);

CREATE INDEX idx_memberdiag_signifyid
    ON memberdiagnosis (signifyid)
    INCLUDE (diagnosiscode, description, lastoccurrence);

CREATE INDEX idx_memberdiag_dxcode
    ON memberdiagnosis (diagnosiscode)
    INCLUDE (signifyid, clientid, description);


-- =============================================================================
-- TABLE 4: membermedications  (already has PK)
-- =============================================================================

DROP TABLE IF EXISTS membermedications CASCADE;
CREATE TABLE membermedications (
    clientid                     BIGINT          NOT NULL,
    signifyid                    VARCHAR(255)    NOT NULL,
    id                           BIGINT          NOT NULL,
    dimmemberhashkey             VARCHAR(32),
    memberplanid                 BIGINT,
    description                  VARCHAR(255),
    quantity                     VARCHAR(50),
    datelastfilled               TIMESTAMP,
    highrisk                     VARCHAR(10),
    ndc                          VARCHAR(15),
    factmembermedicationshashkey VARCHAR(32),
    strength                     VARCHAR(100),
    frequency                    VARCHAR(100),
    route                        VARCHAR(500),
    prescriber                   VARCHAR(255),
    activenumeratorstrength      VARCHAR(15),
    activeingredunit             VARCHAR(15),
    dosageformname               VARCHAR(100),

    CONSTRAINT pk_membermedications PRIMARY KEY (clientid, signifyid, id)
);

CREATE INDEX idx_membermed_signifyid_plan
    ON membermedications (signifyid, memberplanid)
    INCLUDE (description, ndc, datelastfilled);

CREATE INDEX idx_membermed_ndc
    ON membermedications (ndc)
    INCLUDE (signifyid, clientid, description, strength);


-- =============================================================================
-- VERIFY
-- =============================================================================
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size
FROM pg_tables
WHERE tablename IN ('labresult_neil', 'labresult_neil_oltp', 'memberdiagnosis', 'membermedications')
ORDER BY tablename;
