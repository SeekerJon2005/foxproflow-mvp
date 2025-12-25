-- FoxProFlow • Verify/Smoke • P0 DevOrders unblock: dev.dev_order + dev.v_dev_order_commercial_ctx
-- file: scripts/sql/verify/20251224_dev_order_min_smoke.sql

\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

DO $$
DECLARE
  v_id bigint;
BEGIN
  -- existence checks
  IF to_regclass('dev.dev_order') IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing dev.dev_order';
  END IF;

  IF to_regclass('dev.v_dev_order_commercial_ctx') IS NULL THEN
    RAISE EXCEPTION 'FAILED: missing dev.v_dev_order_commercial_ctx';
  END IF;

  -- minimal insert (API-like)
  INSERT INTO dev.dev_order (title, status)
  VALUES ('smoke', 'new')
  RETURNING dev_order_id INTO v_id;

  -- view must return row for inserted id
  IF NOT EXISTS (
    SELECT 1
    FROM dev.v_dev_order_commercial_ctx v
    WHERE v.dev_order_id = v_id
  ) THEN
    RAISE EXCEPTION 'FAILED: view did not return row for dev_order_id=%', v_id;
  END IF;

  -- cleanup (keep db tidy)
  DELETE FROM dev.dev_order WHERE dev_order_id = v_id;
END $$;

SELECT 'PASS: dev.dev_order + dev.v_dev_order_commercial_ctx ok' AS pass;
