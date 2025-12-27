CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION public.fn_norm_key(txt text)
RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT UPPER(
    REGEXP_REPLACE(
      REGEXP_REPLACE(
        REGEXP_REPLACE(
          TRANSLATE(COALESCE($1,''),'ёЁ"''`.,;:()[]{}','ее                '),
          '^(Г(\.|)\s+|ГОРОД\s+|РЕСП(УБЛИКА|)\s+|РЕСП\.\s+)', '', 'i'
        ),
      '\s+(ОБЛ(АСТЬ|)\.?|КРАЙ|РЕСП(УБЛИКА|)\.?|РФ|РБ)\s*$', '', 'i'),
    '\s+', ' ', 'g')
  );
$$;

-- функциональные индексы
CREATE INDEX IF NOT EXISTS city_map_region_norm_idx ON public.city_map (public.fn_norm_key(region));
CREATE INDEX IF NOT EXISTS city_map_city_norm_idx   ON public.city_map (public.fn_norm_key(city));
CREATE INDEX IF NOT EXISTS region_centroids_region_norm_idx ON public.region_centroids (public.fn_norm_key(region));
CREATE INDEX IF NOT EXISTS region_centroids_name_norm_idx   ON public.region_centroids (public.fn_norm_key(name));
CREATE INDEX IF NOT EXISTS region_centroids_code_upper_idx  ON public.region_centroids (UPPER(code));

-- GIN-trgm для fuzzy
CREATE INDEX IF NOT EXISTS city_map_region_trgm ON public.city_map USING gin (public.fn_norm_key(region) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS city_map_city_trgm   ON public.city_map USING gin (public.fn_norm_key(city) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS region_centroids_region_trgm ON public.region_centroids USING gin (public.fn_norm_key(region) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS region_centroids_name_trgm   ON public.region_centroids USING gin (public.fn_norm_key(name) gin_trgm_ops);
