-- 2025-11-19 — FoxProFlow
-- analytics.autoplan_daily_v: минимальная дневная витрина по работе автоплана.
-- Версия 1 (NDC-safe): считаем только количество записей в autoplан_audit по дням.
-- Когда будет удобно, можно расширить (добавить outcome/mode/thresholds) после просмотра схемы таблицы.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.autoplan_daily_v AS
SELECT
    date_trunc('day', created_at)::date AS d,
    COUNT(*)                            AS runs_total
FROM public.autoplan_audit
GROUP BY date_trunc('day', created_at)::date
ORDER BY d DESC;
