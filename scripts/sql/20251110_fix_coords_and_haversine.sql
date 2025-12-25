-- file: scripts/sql/20251110_fix_coords_and_haversine.sql
-- 0) Вспомогательная функция Haversine (км), идемпотентно
CREATE SCHEMA IF NOT EXISTS ops;

CREATE OR REPLACE FUNCTION ops.fn_haversine_km(
  lat1 double precision, lon1 double precision,
  lat2 double precision, lon2 double precision
) RETURNS double precision
LANGUAGE sql IMMUTABLE AS $$
  SELECT 2*6371.0*asin(
           sqrt(
             sin((($3-$1)*pi()/180)/2)^2
             + cos($1*pi()/180)*cos($3*pi()/180)*sin((($4-$2)*pi()/180)/2)^2
           )
         );
$$;

-- 1) Подлить origin-координаты из region_centroids там, где пусто
UPDATE public.trips t
   SET meta = jsonb_set(
                jsonb_set(
                  jsonb_set(
                    jsonb_set(COALESCE(t.meta,'{}'::jsonb),
                              '{autoplan,origin_lat}', to_jsonb((rc.lat)::numeric), true),
                              '{autoplan,origin_lon}', to_jsonb((rc.lon)::numeric), true),
                              '{autoplan,from_lat}',   to_jsonb((rc.lat)::numeric), true),
                              '{autoplan,from_lon}',   to_jsonb((rc.lon)::numeric), true
              ),
       updated_at = now()
FROM public.region_centroids rc
WHERE t.status='confirmed'
  AND (COALESCE(t.meta->'autoplan'->>'origin_lat','')='' OR
       COALESCE(t.meta->'autoplan'->>'origin_lon','')='' OR
       COALESCE(t.meta->'autoplan'->>'from_lat','')  ='' OR
       COALESCE(t.meta->'autoplan'->>'from_lon','')  ='')
  AND (
        public.fn_norm_key(rc.region) = public.fn_norm_key(t.meta->'autoplan'->>'origin_region')
     OR UPPER(rc.code)                = UPPER(t.meta->'autoplan'->>'origin_region')
     OR public.fn_norm_key(rc.name)   = public.fn_norm_key(t.meta->'autoplan'->>'origin_region')
  );

-- 2) Подлить dest-координаты из region_centroids там, где пусто
UPDATE public.trips t
   SET meta = jsonb_set(
                jsonb_set(
                  jsonb_set(
                    jsonb_set(COALESCE(t.meta,'{}'::jsonb),
                              '{autoplan,dest_lat}', to_jsonb((rc.lat)::numeric), true),
                              '{autoplan,dest_lon}', to_jsonb((rc.lon)::numeric), true),
                              '{autoplan,to_lat}',   to_jsonb((rc.lat)::numeric), true),
                              '{autoplan,to_lon}',   to_jsonb((rc.lon)::numeric), true
              ),
       updated_at = now()
FROM public.region_centroids rc
WHERE t.status='confirmed'
  AND (COALESCE(t.meta->'autoplan'->>'dest_lat','')='' OR
       COALESCE(t.meta->'autoplan'->>'dest_lon','')='' OR
       COALESCE(t.meta->'autoplan'->>'to_lat','')  ='' OR
       COALESCE(t.meta->'autoplan'->>'to_lon','')  ='')
  AND (
        public.fn_norm_key(rc.region) = public.fn_norm_key(t.meta->'autoplan'->>'dest_region')
     OR UPPER(rc.code)                = UPPER(t.meta->'autoplan'->>'dest_region')
     OR public.fn_norm_key(rc.name)   = public.fn_norm_key(t.meta->'autoplan'->>'dest_region')
  );

-- 3) Haversine-фолбэк: проставить road_km и drive_sec всем confirmed без дороги,
--    у кого обе пары координат уже есть
WITH c AS (
  SELECT t.id,
         NULLIF(COALESCE(t.meta->'autoplan'->>'from_lat',   t.meta->'autoplan'->>'origin_lat'),'')::double precision AS a_lat,
         NULLIF(COALESCE(t.meta->'autoplan'->>'from_lon',   t.meta->'autoplan'->>'origin_lon'),'')::double precision AS a_lon,
         NULLIF(COALESCE(t.meta->'autoplan'->>'to_lat',     t.meta->'autoplan'->>'dest_lat'),'')::double precision   AS b_lat,
         NULLIF(COALESCE(t.meta->'autoplan'->>'to_lon',     t.meta->'autoplan'->>'dest_lon'),'')::double precision   AS b_lon
  FROM public.trips t
  WHERE t.status='confirmed'
    AND COALESCE(NULLIF(t.meta->'autoplan'->>'road_km',''),'') = ''
)
UPDATE public.trips t
   SET meta = jsonb_set(
               jsonb_set(
                 COALESCE(t.meta,'{}'::jsonb),
                 '{autoplan,road_km}',
                 to_jsonb(ops.fn_haversine_km(c.a_lat,c.a_lon,c.b_lat,c.b_lon)::numeric),
                 true
               ),
               '{autoplan,drive_sec}',
               to_jsonb( CEIL( ops.fn_haversine_km(c.a_lat,c.a_lon,c.b_lat,c.b_lon) / 55.0 * 3600.0 )::int ),
               true
             ),
       updated_at = now()
FROM c
WHERE t.id=c.id
  AND c.a_lat IS NOT NULL AND c.a_lon IS NOT NULL
  AND c.b_lat IS NOT NULL AND c.b_lon IS NOT NULL;
