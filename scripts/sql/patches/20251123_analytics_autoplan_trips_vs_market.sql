CREATE SCHEMA IF NOT EXISTS analytics;

-- Витрина рейсов автоплана с возможностью привязки к рынку.
-- На текущем этапе содержит те же поля, что analytics.autoplan_trips_detailed_v.
-- При появлении стабильных рыночных витрин (ATI/DynRPM) может быть расширена
-- дополнительными полями через JOIN без изменения имени и базового контракта.

CREATE OR REPLACE VIEW analytics.autoplan_trips_vs_market_v AS
SELECT
    t.*
FROM analytics.autoplan_trips_detailed_v t;
