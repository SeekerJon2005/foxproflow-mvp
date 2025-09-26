-- src/data_layer/create_freights_enriched.sql
-- 1) Таблица под выборки /freights (синхронизировано с BASE_SELECT в repo.py)
CREATE TABLE IF NOT EXISTS freights_enriched (
    id                           TEXT PRIMARY KEY,
    hash                         TEXT,
    loading_city                 TEXT,
    unloading_city               TEXT,
    distance                     NUMERIC(10,2),
    cargo                        TEXT,
    weight                       NUMERIC(10,2),
    volume                       NUMERIC(10,2),
    body_type                    TEXT,
    loading_date                 TIMESTAMPTZ,
    revenue_rub                  NUMERIC(14,2),
    profit_per_km                NUMERIC(10,2),
    loading_lat                  NUMERIC(10,6),
    loading_lon                  NUMERIC(10,6),
    unloading_lat                NUMERIC(10,6),
    unloading_lon                NUMERIC(10,6),
    loading_region               TEXT,
    unloading_region             TEXT,
    parsed_at                    TIMESTAMPTZ DEFAULT now(),
    session_id                   TEXT,
    source                       TEXT,
    usd_rate                     NUMERIC(10,4),
    eur_rate                     NUMERIC(10,4),
    fuel_price_avg               NUMERIC(10,3),
    loading_region_trucks        INT,
    loading_region_requests      INT,
    unloading_region_trucks      INT,
    unloading_region_requests    INT
);

-- 2) Индексы под фильтры/сортировки, которыми пользуется repo.py
CREATE INDEX IF NOT EXISTS idx_fe_loading_city      ON freights_enriched (loading_city);
CREATE INDEX IF NOT EXISTS idx_fe_unloading_city    ON freights_enriched (unloading_city);
CREATE INDEX IF NOT EXISTS idx_fe_loading_date      ON freights_enriched (loading_date);
CREATE INDEX IF NOT EXISTS idx_fe_parsed_at         ON freights_enriched (parsed_at DESC);

-- 3) Пара тестовых строк (для проверки /freights и /freights/{fid})
INSERT INTO freights_enriched (
    id, hash, loading_city, unloading_city, distance, cargo, weight, volume,
    body_type, loading_date, revenue_rub, profit_per_km,
    loading_lat, loading_lon, unloading_lat, unloading_lon,
    loading_region, unloading_region, parsed_at, session_id, source,
    usd_rate, eur_rate, fuel_price_avg,
    loading_region_trucks, loading_region_requests,
    unloading_region_trucks, unloading_region_requests
) VALUES
('1','h1','Москва','Санкт-Петербург',700,'Овощи',20000,80,'REF',
 '2025-09-25T10:00:00+03:00',50000,71.43,
 55.7558,37.6173,59.9311,30.3609,
 'Москва','СПб', now(),'test','seed',90.00,95.00,58.50,120,340,140,320),

('2','h2','Казань','Нижний Новгород',400,'Металл',10000,50,'TENT',
 '2025-09-25T12:00:00+03:00',30000,75.00,
 55.7963,49.1088,56.2965,43.9361,
 'Татарстан','Нижегородская', now(),'test','seed',90.00,95.00,58.50,80,210,95,180)
ON CONFLICT (id) DO NOTHING;
