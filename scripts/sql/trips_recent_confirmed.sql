-- file: C:\Users\Evgeniy\projects\foxproflow-mvp 2.0\scripts\sql\trips_recent_confirmed.sql
-- FoxProFlow — последние подтверждённые рейсы (быстрый срез)

SELECT
  id,
  truck_id,
  meta->'autoplan'->>'origin_region' AS o,
  meta->'autoplan'->>'dest_region'   AS d,
  meta->'autoplan'->>'road_km'       AS km,
  meta->'autoplan'->>'drive_sec'     AS sec,
  meta->'autoplan'->>'rph'           AS rph,
  status,
  to_char(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated_at
FROM public.trips
WHERE status = 'confirmed'
ORDER BY updated_at DESC
LIMIT 50;
