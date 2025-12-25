-- 2025-11-15 — FoxProFlow
-- Универсальная UPSERT-функция для freights по source_uid.

CREATE OR REPLACE FUNCTION public.fn_upsert_freight(
    p_source_uid         text,
    p_loading_region     text,
    p_unloading_region   text,
    p_loading_date       timestamptz,
    p_unloading_date     timestamptz,
    p_distance           numeric,
    p_revenue_rub        numeric,
    p_body_type          text,
    p_weight             numeric,
    p_source             text,
    p_parsed_at          timestamptz,
    p_payload            jsonb,
    p_loading_lat        double precision,
    p_loading_lon        double precision,
    p_unloading_lat      double precision,
    p_unloading_lon      double precision
)
RETURNS bigint
LANGUAGE plpgsql
AS $func$
DECLARE
    v_id bigint;
BEGIN
    INSERT INTO public.freights (
        source_uid,
        loading_region,
        unloading_region,
        loading_date,
        unloading_date,
        distance,
        revenue_rub,
        body_type,
        weight,
        source,
        parsed_at,
        payload,
        loading_lat,
        loading_lon,
        unloading_lat,
        unloading_lon
    )
    VALUES (
        p_source_uid,
        p_loading_region,
        p_unloading_region,
        p_loading_date,
        p_unloading_date,
        p_distance,
        p_revenue_rub,
        p_body_type,
        p_weight,
        p_source,
        p_parsed_at,
        p_payload,
        p_loading_lat,
        p_loading_lon,
        p_unloading_lat,
        p_unloading_lon
    )
    ON CONFLICT (source_uid) DO UPDATE
    SET
        loading_region   = EXCLUDED.loading_region,
        unloading_region = EXCLUDED.unloading_region,
        loading_date     = EXCLUDED.loading_date,
        unloading_date   = EXCLUDED.unloading_date,
        distance         = EXCLUDED.distance,
        revenue_rub      = EXCLUDED.revenue_rub,
        body_type        = EXCLUDED.body_type,
        weight           = EXCLUDED.weight,
        source           = EXCLUDED.source,
        parsed_at        = EXCLUDED.parsed_at,
        payload          = EXCLUDED.payload,
        loading_lat      = EXCLUDED.loading_lat,
        loading_lon      = EXCLUDED.loading_lon,
        unloading_lat    = EXCLUDED.unloading_lat,
        unloading_lon    = EXCLUDED.unloading_lon
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$func$;
