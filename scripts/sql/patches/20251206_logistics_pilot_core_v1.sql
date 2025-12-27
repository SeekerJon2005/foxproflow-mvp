-- 20251206_logistics_pilot_core_v1.sql
-- stack=sql
-- project_ref=logistics-pilot-001
-- goal=Пилот логистики 5–15 ТС: ядро таблиц staging/logistics и первые KPI-витрины по реальным рейсам/ТС.
-- summary=Создаёт схемы staging/logistics (если нет), базовые таблицы для пилота и две KPI-витрины по рейсам/ТС.

-- 1. Гарантируем наличие схем staging и logistics

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_namespace WHERE nspname = 'staging'
    ) THEN
        EXECUTE 'CREATE SCHEMA staging';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_namespace WHERE nspname = 'logistics'
    ) THEN
        EXECUTE 'CREATE SCHEMA logistics';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 2. STAGING-ТАБЛИЦЫ (универсальные jsonb-контейнеры для импорта CSV/Excel)

CREATE TABLE IF NOT EXISTS staging.logistics_vehicles (
    id            bigserial PRIMARY KEY,
    imported_at   timestamptz NOT NULL DEFAULT now(),
    source_system text,
    raw_payload   jsonb       NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.logistics_trips (
    id            bigserial PRIMARY KEY,
    imported_at   timestamptz NOT NULL DEFAULT now(),
    source_system text,
    raw_payload   jsonb       NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.logistics_orders (
    id            bigserial PRIMARY KEY,
    imported_at   timestamptz NOT NULL DEFAULT now(),
    source_system text,
    raw_payload   jsonb       NOT NULL
);

-- 3. ОСНОВНЫЕ ЛОГИСТИЧЕСКИЕ ТАБЛИЦЫ ПИЛОТА

-- 3.1. Транспортные средства (ТС)
CREATE TABLE IF NOT EXISTS logistics.vehicles (
    vehicle_id      uuid        PRIMARY KEY,
    project_ref     text        NOT NULL DEFAULT 'logistics-pilot-001',
    external_id     text,
    plate_number    text        NOT NULL,
    vehicle_type    text,
    capacity_tons   numeric,
    capacity_m3     numeric,
    is_active       boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_vehicles_project_ref
    ON logistics.vehicles (project_ref);

-- 3.2. Загрузки / заказы (loads)
CREATE TABLE IF NOT EXISTS logistics.loads (
    load_id               uuid        PRIMARY KEY,
    project_ref           text        NOT NULL DEFAULT 'logistics-pilot-001',
    external_id           text,
    customer_name         text,

    origin_city           text,
    origin_address        text,
    destination_city      text,
    destination_address   text,

    pickup_window_start      timestamptz,
    pickup_window_end        timestamptz,
    delivery_window_start    timestamptz,
    delivery_window_end      timestamptz,

    price_amount          numeric,
    currency_code         text,

    status                text,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_loads_project_ref
    ON logistics.loads (project_ref);

-- 3.3. Рейсы (trips)
CREATE TABLE IF NOT EXISTS logistics.trips (
    trip_id            uuid        PRIMARY KEY,
    project_ref        text        NOT NULL DEFAULT 'logistics-pilot-001',

    vehicle_id         uuid        REFERENCES logistics.vehicles (vehicle_id),
    load_id            uuid        REFERENCES logistics.loads (load_id),

    origin_city        text,
    origin_address     text,
    destination_city   text,
    destination_address text,

    planned_start_at   timestamptz,
    planned_end_at     timestamptz,
    actual_start_at    timestamptz,
    actual_end_at      timestamptz,

    route_distance_km  numeric,
    status             text,

    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_trips_project_ref
    ON logistics.trips (project_ref);

CREATE INDEX IF NOT EXISTS ix_trips_vehicle_project
    ON logistics.trips (project_ref, vehicle_id);

-- 3.4. Сегменты рейсов (trip_segments)
CREATE TABLE IF NOT EXISTS logistics.trip_segments (
    trip_segment_id   uuid        PRIMARY KEY,
    project_ref       text        NOT NULL DEFAULT 'logistics-pilot-001',

    trip_id           uuid        REFERENCES logistics.trips (trip_id),
    seq_no            integer     NOT NULL,

    from_city         text,
    from_address      text,
    to_city           text,
    to_address        text,

    distance_km       numeric,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_trip_segments_trip
    ON logistics.trip_segments (trip_id);

CREATE INDEX IF NOT EXISTS ix_trip_segments_project_ref
    ON logistics.trip_segments (project_ref);

-- 4. KPI ВИТРИНЫ ПО РЕЙСАМ/ТС (pilot core)

-- гарантируем наличие analytics (на случай, если патч с DevFactory-KPI ещё не применён)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_namespace WHERE nspname = 'analytics'
    ) THEN
        EXECUTE 'CREATE SCHEMA analytics';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 4.1. KPI по ТС/дню (рейсы, пробег, выручка)

CREATE OR REPLACE VIEW analytics.logistics_pilot_vehicle_day_kpi_v1 AS
WITH trips_enriched AS (
    SELECT
        t.trip_id,
        t.project_ref,
        t.vehicle_id,
        (COALESCE(t.actual_start_at, t.planned_start_at) AT TIME ZONE 'UTC')::date AS day_utc,
        t.route_distance_km,
        l.price_amount
    FROM logistics.trips t
    LEFT JOIN logistics.loads l
        ON l.load_id = t.load_id
    WHERE t.project_ref = 'logistics-pilot-001'
)
SELECT
    day_utc,
    project_ref,
    vehicle_id,
    COUNT(*)                           AS trips_count,
    COALESCE(SUM(route_distance_km), 0) AS distance_km_sum,
    COALESCE(SUM(price_amount), 0)      AS revenue_sum
FROM trips_enriched
GROUP BY
    day_utc,
    project_ref,
    vehicle_id
ORDER BY
    day_utc DESC,
    vehicle_id;

-- 4.2. KPI по пилоту в целом (агрегат по ТС)
CREATE OR REPLACE VIEW analytics.logistics_pilot_revenue_kpi_v1 AS
SELECT
    day_utc,
    project_ref,
    SUM(trips_count)      AS trips_count,
    SUM(distance_km_sum)  AS distance_km_sum,
    SUM(revenue_sum)      AS revenue_sum
FROM analytics.logistics_pilot_vehicle_day_kpi_v1
GROUP BY
    day_utc,
    project_ref
ORDER BY
    day_utc DESC;
