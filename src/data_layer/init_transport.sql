-- Таблица транспорта (доступные машины)
CREATE TABLE IF NOT EXISTS transport (
    id UUID PRIMARY KEY,                 -- UUID карточки (из data-qa="truck-card-...")
    truck_type TEXT,                     -- тип кузова (тент, полуприцеп и т.д.)
    weight NUMERIC,                      -- грузоподъёмность (тонн)
    volume NUMERIC,                      -- объём (м3)
    dimensions TEXT,                     -- размеры кузова (строкой)
    loading_params TEXT,                 -- растентовки/параметры погрузки

    loading_city TEXT,                   -- город, где стоит машина
    loading_distance TEXT,               -- расстояние до города (как на сайте)
    loading_period TEXT,                 -- период доступности ("19–21 сен")

    unloading_main TEXT,                 -- основной город выгрузки
    unloading_options JSONB,             -- массив вариантов [{city, rate}, ...]

    rate_cash TEXT,                      -- ставка наличные
    rate_with_vat TEXT,                  -- ставка с НДС
    rate_without_vat TEXT,               -- ставка без НДС
    rate_bargain BOOLEAN DEFAULT FALSE,  -- торг (есть/нет)

    parsed_at TIMESTAMP DEFAULT now()    -- когда спарсили
);

-- Индексы для ускорения выборок
CREATE INDEX IF NOT EXISTS idx_transport_loading_city   ON transport(loading_city);
CREATE INDEX IF NOT EXISTS idx_transport_unloading_main ON transport(unloading_main);
CREATE INDEX IF NOT EXISTS idx_transport_parsed_at      ON transport(parsed_at DESC);
