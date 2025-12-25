-- FoxProFlow • Verify/Smoke • CityMap MIN
-- file: scripts/sql/verify/20251223_city_map_min_smoke.sql
\set ON_ERROR_STOP on
\pset pager off

SELECT now() AS ts_now, current_database() AS db, current_user AS db_user;

SELECT coalesce(to_regclass('public.city_map')::text,'MISSING') AS city_map;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema='public' AND table_name='city_map'
ORDER BY ordinal_position;

SELECT count(*) AS city_map_cnt FROM public.city_map;

-- prove lookup for test keys
SELECT id, key, region_key, region_code, name, city, lat, lon
FROM public.city_map
WHERE lower(coalesce(key,'')) IN ('test_origin','test_dest')
   OR lower(coalesce(region_key,'')) IN ('test_origin','test_dest')
   OR lower(coalesce(region_code,'')) IN ('test_origin','test_dest')
   OR lower(coalesce(name,'')) IN ('test_origin','test_dest')
   OR lower(coalesce(city,'')) IN ('test_origin','test_dest')
ORDER BY id
LIMIT 10;

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname='public' AND tablename='city_map'
ORDER BY indexname;
