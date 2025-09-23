-- Создание таблицы грузов (адаптированная версия существующей структуры)
CREATE TABLE IF NOT EXISTS freights (
    id TEXT PRIMARY KEY,
    hash VARCHAR(32) UNIQUE,
    loading_city TEXT NOT NULL,
    unloading_city TEXT NOT NULL,
    distance REAL NOT NULL,
    cargo TEXT NOT NULL,
    weight REAL NOT NULL,
    volume REAL NOT NULL,
    body_type TEXT NOT NULL,
    loading_date TEXT NOT NULL,
    revenue_rub REAL NOT NULL,
    profit_per_km REAL NOT NULL,
    loading_lat REAL,
    loading_lon REAL,
    unloading_lat REAL,
    unloading_lon REAL,
    loading_region TEXT,
    unloading_region TEXT,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id INTEGER,
    source VARCHAR(50) DEFAULT 'ati'
);

-- Создание таблицы для данных о транспорте (спрос)
CREATE TABLE IF NOT EXISTS transport_demand (
    id SERIAL PRIMARY KEY,
    region VARCHAR(100) NOT NULL,
    trucks_available INTEGER,
    requests INTEGER,
    date DATE NOT NULL,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы макроэкономических данных
CREATE TABLE IF NOT EXISTS macro_data (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    usd_rate DECIMAL(10, 4),
    eur_rate DECIMAL(10, 4),
    fuel_price_avg DECIMAL(10, 2),
    source VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы сессий парсинга
CREATE TABLE IF NOT EXISTS parsing_sessions (
    id SERIAL PRIMARY KEY,
    region VARCHAR(100) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    items_processed INTEGER DEFAULT 0,
    items_added INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'running'
);

-- Индексы для ускорения запросов
CREATE INDEX IF NOT EXISTS idx_freights_route ON freights(loading_city, unloading_city);
CREATE INDEX IF NOT EXISTS idx_freights_date ON freights(loading_date);
CREATE INDEX IF NOT EXISTS idx_freights_hash ON freights(hash);
CREATE INDEX IF NOT EXISTS idx_freights_combined ON freights(loading_city, unloading_city, loading_date);
CREATE INDEX IF NOT EXISTS idx_transport_demand_region_date ON transport_demand(region, date);
CREATE INDEX IF NOT EXISTS idx_macro_data_date ON macro_data(date);
CREATE INDEX IF NOT EXISTS idx_parsing_sessions_region_time ON parsing_sessions(region, start_time);

-- Создание представления для часто используемых запросов
CREATE OR REPLACE VIEW freights_enriched AS
SELECT 
    f.*,
    md.usd_rate,
    md.eur_rate,
    md.fuel_price_avg,
    td_loading.trucks_available as loading_region_trucks,
    td_loading.requests as loading_region_requests,
    td_unloading.trucks_available as unloading_region_trucks,
    td_unloading.requests as unloading_region_requests
FROM freights f
LEFT JOIN macro_data md ON f.loading_date::DATE = md.date
LEFT JOIN transport_demand td_loading ON f.loading_region = td_loading.region AND f.loading_date::DATE = td_loading.date
LEFT JOIN transport_demand td_unloading ON f.unloading_region = td_unloading.region AND f.loading_date::DATE = td_unloading.date;
