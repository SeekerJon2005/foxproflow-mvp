-- file: scripts/sql/20251110_ops_region_centroids_autoseed.sql
CREATE OR REPLACE FUNCTION ops.fn_region_centroids_autoseed(max_rows int DEFAULT 100)
RETURNS int
LANGUAGE plpgsql
AS $$
DECLARE
  n int := 0;
BEGIN
  INSERT INTO public.region_centroids (code, region, name, lat, lon)
  SELECT s.region_key AS code,
         s.region_key AS region,
         s.region_key AS name,
         s.lat_suggest::float,
         s.lon_suggest::float
  FROM ops.region_centroids_suggest_v s
  WHERE s.lat_suggest IS NOT NULL AND s.lon_suggest IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM public.region_centroids rc
      WHERE UPPER(rc.code)=s.region_key
         OR public.fn_norm_key(rc.region)=public.fn_norm_key(s.region_key)
         OR public.fn_norm_key(rc.name)=public.fn_norm_key(s.region_key)
    )
  LIMIT max_rows;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END$$;
