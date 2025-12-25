-- logistics_autoplan_seed_demo_vehicles.sql
-- DevTask: (коммит будет с [DEVTASK:<id>])
-- Создал Архитектор: Яцков Евгений Анатольевич
-- Назначение: демо ТС для автоплана (реальные vehicle_code вместо VIRTUAL-*)
-- Принцип: upsert по vehicle_code (без delete/truncate)

\set ON_ERROR_STOP on

\echo ''
\echo '--- Seeding demo vehicles for autoplan (upsert) ---'

WITH seed AS (
  SELECT
    ('TRUCK-' || lpad(gs::text, 3, '0'))::text AS vehicle_code,
    'demo'::text AS region,
    (current_date::timestamptz) AS available_from,
    true AS is_active,
    jsonb_build_object('source','demo_seed','kind','truck') AS meta
  FROM generate_series(1, 10) gs
),
upserted AS (
  INSERT INTO logistics.vehicles (vehicle_code, region, available_from, is_active, meta)
  SELECT vehicle_code, region, available_from, is_active, meta
  FROM seed
  ON CONFLICT (vehicle_code) DO UPDATE
    SET region = EXCLUDED.region,
        available_from = EXCLUDED.available_from,
        is_active = true,
        meta = COALESCE(logistics.vehicles.meta, '{}'::jsonb) || EXCLUDED.meta
  RETURNING vehicle_code
)
SELECT count(*) AS upserted_rows
FROM upserted;

\echo ''
\echo '--- Vehicles (top 20) ---'
SELECT
  vehicle_code, region, available_from, is_active, meta
FROM logistics.vehicles
ORDER BY vehicle_code
LIMIT 20;
