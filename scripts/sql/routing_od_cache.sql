-- Координатный OD-кэш маршрутов (квантованные координаты, чтобы не плодить ключи)
CREATE TABLE IF NOT EXISTS public.routing_od_cache(
  id            bigserial PRIMARY KEY,
  src_lat_q     numeric(9,5)  NOT NULL,
  src_lon_q     numeric(10,5) NOT NULL,
  dst_lat_q     numeric(9,5)  NOT NULL,
  dst_lon_q     numeric(10,5) NOT NULL,
  profile       text          NOT NULL DEFAULT 'driving',
  distance_m    bigint        NOT NULL,
  duration_s    integer       NOT NULL,
  polyline      text,
  updated_at    timestamptz   NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_routing_od_cache_key
  ON public.routing_od_cache(src_lat_q, src_lon_q, dst_lat_q, dst_lon_q, profile);

CREATE INDEX IF NOT EXISTS ix_routing_od_cache_updated
  ON public.routing_od_cache(updated_at DESC);
