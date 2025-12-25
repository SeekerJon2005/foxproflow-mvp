\pset pager off
\set ON_ERROR_STOP on

\echo '---'
\echo 'VERIFY M0 START'
\echo '---'

-- 0) Hard dependency check: gen_random_uuid()
DO $$
BEGIN
    PERFORM gen_random_uuid();
EXCEPTION WHEN undefined_function THEN
    RAISE EXCEPTION 'M0 VERIFY FAIL: gen_random_uuid() is missing (pgcrypto extension not installed)';
END$$;

-- 1) Required relations existence (DevFactory + CRM + Ops)
DO $$
DECLARE
    rel text;
BEGIN
    FOREACH rel IN ARRAY ARRAY[
        'dev.dev_task',
        'dev.dev_order',
        'dev.v_dev_order_commercial_ctx',
        'crm.tenants',
        'crm.leads',
        'crm.leads_trial_candidates_v',
        'ops.audit_events'
    ]
    LOOP
        IF to_regclass(rel) IS NULL THEN
            RAISE EXCEPTION 'M0 VERIFY FAIL: missing relation %', rel;
        END IF;
    END LOOP;
END$$;

-- 2) Column-level contract checks (minimal, but non-empty)
DO $$
DECLARE
    missing_cols text[];
BEGIN
    -- dev.dev_order columns used by API INSERT
    SELECT array_agg(col) INTO missing_cols
    FROM (
        SELECT col FROM (VALUES
            ('title'),
            ('description'),
            ('customer_name'),
            ('order_tenant_external_id'),
            ('tenant_id'),
            ('total_amount'),
            ('currency_code'),
            ('status')
        ) v(col)
        WHERE NOT EXISTS (
            SELECT 1
            FROM information_schema.columns c
            WHERE c.table_schema='dev'
              AND c.table_name='dev_order'
              AND c.column_name=v.col
        )
    ) q;

    IF missing_cols IS NOT NULL THEN
        RAISE EXCEPTION 'M0 VERIFY FAIL: dev.dev_order missing columns: %', missing_cols;
    END IF;

    -- crm.tenants.id must be uuid with default
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='crm' AND table_name='tenants' AND column_name='id' AND udt_name='uuid'
    ) THEN
        RAISE EXCEPTION 'M0 VERIFY FAIL: crm.tenants.id is not uuid';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='crm' AND table_name='tenants' AND column_name='id'
          AND column_default IS NOT NULL AND btrim(column_default) <> ''
    ) THEN
        RAISE EXCEPTION 'M0 VERIFY FAIL: crm.tenants.id has no DEFAULT';
    END IF;

    -- crm.leads core columns (as expected by CRM smoke v2)
    SELECT array_agg(col) INTO missing_cols
    FROM (
        SELECT col FROM (VALUES
            ('id'),
            ('status'),
            ('payload'),
            ('created_at'),
            ('updated_at')
        ) v(col)
        WHERE NOT EXISTS (
            SELECT 1
            FROM information_schema.columns c
            WHERE c.table_schema='crm'
              AND c.table_name='leads'
              AND c.column_name=v.col
        )
    ) q;

    IF missing_cols IS NOT NULL THEN
        RAISE EXCEPTION 'M0 VERIFY FAIL: crm.leads missing columns: %', missing_cols;
    END IF;

    -- ops.audit_events must have core fields
    SELECT array_agg(col) INTO missing_cols
    FROM (
        SELECT col FROM (VALUES
            ('ts'),
            ('actor'),
            ('action'),
            ('ok'),
            ('payload'),
            ('evidence_refs')
        ) v(col)
        WHERE NOT EXISTS (
            SELECT 1
            FROM information_schema.columns c
            WHERE c.table_schema='ops'
              AND c.table_name='audit_events'
              AND c.column_name=v.col
        )
    ) q;

    IF missing_cols IS NOT NULL THEN
        RAISE EXCEPTION 'M0 VERIFY FAIL: ops.audit_events missing columns: %', missing_cols;
    END IF;
END$$;

-- 3) DML proof (transactional, must not leave data)
BEGIN;

-- 3.1 DevOrder insert + view proof
INSERT INTO dev.dev_order (title, status)
VALUES ('verify-m0', 'new')
RETURNING dev_order_id AS v_dev_order_id \gset

SELECT 1
FROM dev.v_dev_order_commercial_ctx
WHERE dev_order_id = :v_dev_order_id
LIMIT 1;

-- 3.2 CRM insert/update + view queryability proof
INSERT INTO crm.leads (source, company_name, contact_name, email, phone, country, region)
VALUES ('verify', 'verify-company', 'verify-contact', 'verify@example.local', '+10000000000', 'RU', 'RU-MOW')
RETURNING id AS v_lead_id \gset

UPDATE crm.leads
SET company_name = 'verify-company-upd'
WHERE id = :v_lead_id;

SELECT count(*) FROM crm.leads_trial_candidates_v;

-- 3.3 Audit event insert proof (references dev_order_id)
INSERT INTO ops.audit_events (actor, action, ok, dev_order_id, payload, evidence_refs)
VALUES ('verify_m0', 'verify.m0', TRUE, :v_dev_order_id, '{}'::jsonb, '[]'::jsonb)
RETURNING audit_event_id AS v_audit_event_id \gset

ROLLBACK;

\echo 'OK: VERIFY M0 PASS'
SELECT 'OK: verify_m0 PASS' AS ok;
