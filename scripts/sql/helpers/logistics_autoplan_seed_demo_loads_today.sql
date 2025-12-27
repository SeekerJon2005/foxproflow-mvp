-- logistics_autoplan_seed_demo_loads_today.sql
-- DevTask: (заполни в коммите маркером [DEVTASK:<id>])
-- Создал Архитектор: Яцков Евгений Анатольевич
-- Назначение: демо-грузы для автоплана (planned/in_transit) на current_date
-- Принцип: add-only + идемпотентность через WHERE NOT EXISTS

\set ON_ERROR_STOP on

\echo ''
\echo '--- Seeding autoplan demo loads for current_date (DB timezone) ---'

WITH seed AS (
  SELECT
    (current_date::timestamptz + interval '08 hours' + (gs-1) * interval '45 minutes') AS pickup_planned_at,
    (current_date::timestamptz + interval '10 hours' + (gs-1) * interval '45 minutes') AS delivery_planned_at,
    CASE
      WHEN gs IN (1,2) THEN 'in_transit'
      ELSE 'planned'
    END AS status
  FROM generate_series(1, 8) gs
),
ins AS (
  INSERT INTO logistics.loads (
    pickup_planned_at,
    pickup_actual_at,
    delivery_planned_at,
    delivery_actual_at,
    status
  )
  SELECT
    s.pickup_planned_at,
    NULL::timestamptz,
    s.delivery_planned_at,
    NULL::timestamptz,
    s.status
  FROM seed s
  WHERE NOT EXISTS (
    SELECT 1
    FROM logistics.loads l
    WHERE l.pickup_planned_at   = s.pickup_planned_at
      AND l.delivery_planned_at = s.delivery_planned_at
      AND l.status              = s.status
  )
  RETURNING id, pickup_planned_at, delivery_planned_at, status
)
SELECT count(*) AS inserted_rows
FROM ins;

\echo ''
\echo '--- Autoplan candidates for today (current_date window) ---'
WITH w AS (
  SELECT (current_date::timestamptz) AS ws, (current_date::timestamptz + interval '1 day') AS we
)
SELECT
  count(*) AS candidates,
  min(l.pickup_planned_at) AS min_pickup,
  max(l.pickup_planned_at) AS max_pickup
FROM logistics.loads l
CROSS JOIN w
WHERE l.pickup_planned_at IS NOT NULL
  AND l.delivery_planned_at IS NOT NULL
  AND l.pickup_planned_at >= w.ws
  AND l.pickup_planned_at <  w.we
  AND l.status NOT IN ('delivered','cancelled');

\echo ''
\echo '--- Sample candidates (next 20 by pickup) ---'
WITH w AS (
  SELECT (current_date::timestamptz) AS ws, (current_date::timestamptz + interval '1 day') AS we
)
SELECT
  id, status, pickup_planned_at, delivery_planned_at
FROM logistics.loads l
CROSS JOIN w
WHERE l.pickup_planned_at IS NOT NULL
  AND l.delivery_planned_at IS NOT NULL
  AND l.pickup_planned_at >= w.ws
  AND l.pickup_planned_at <  w.we
  AND l.status NOT IN ('delivered','cancelled')
ORDER BY pickup_planned_at
LIMIT 20;
