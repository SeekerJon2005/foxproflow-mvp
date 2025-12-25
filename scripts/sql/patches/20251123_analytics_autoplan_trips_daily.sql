-- 2025-11-23 — FoxProFlow
-- Дневная статистика по рейсам автоплана.
-- Источник: public.trips (только статус confirmed) + public.autoplan_audit (decision = 'confirm', applied = true).
-- NDC: CREATE SCHEMA IF NOT EXISTS + CREATE OR REPLACE VIEW + COMMENT (без DROP/ALTER таблиц).

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.autoplan_trips_daily_v AS
WITH trips_applied AS (
    SELECT
        t.id        AS trip_id,
        t.status,
        t.created_at,
        t.confirmed_at,
        a.ts        AS decision_ts,
        COALESCE(
            a.plan_name,
            a.thresholds->>'flow_plan',
            'unknown'
        )           AS flow_plan
    FROM public.trips t
    JOIN public.autoplan_audit a
      ON a.trip_id  = t.id
     AND a.decision = 'confirm'
     AND a.applied  IS TRUE
    WHERE t.status = 'confirmed'
)
SELECT
    date(COALESCE(ta.confirmed_at, ta.decision_ts)) AS d,              -- день (по дате подтверждения/решения)
    ta.flow_plan,                                                      -- FlowLang-план (msk_day, longhaul_night и т.п.)

    COUNT(DISTINCT ta.trip_id)                     AS trips_cnt,       -- количество подтверждённых рейсов за день
    COUNT(*)                                       AS trip_events_cnt, -- количество событий по этим рейсам в audit'е

    COALESCE(SUM(s.price_rub), 0::numeric)        AS sum_price_rub    -- суммарная выручка по сегментам рейса
FROM trips_applied ta
LEFT JOIN public.trip_segments s
       ON s.trip_id = ta.trip_id
GROUP BY
    1,  -- d
    2;  -- flow_plan

COMMENT ON VIEW analytics.autoplan_trips_daily_v IS
    'Дневная статистика по подтверждённым рейсам автоплана (count, events, суммарная цена) по flow_plan.';

COMMENT ON COLUMN analytics.autoplan_trips_daily_v.d IS
    'День (date) по дате подтверждения рейса или моменту решения автоплана.';

COMMENT ON COLUMN analytics.autoplan_trips_daily_v.flow_plan IS
    'Имя плана автоплана/FlowLang (msk_day, longhaul_night и т.п.).';

COMMENT ON COLUMN analytics.autoplan_trips_daily_v.trips_cnt IS
    'Количество уникальных подтверждённых рейсов за день по данному flow_plan.';

COMMENT ON COLUMN analytics.autoplan_trips_daily_v.trip_events_cnt IS
    'Количество событий (строк) в autoplan_audit, привязанных к этим рейсам за день.';

COMMENT ON COLUMN analytics.autoplan_trips_daily_v.sum_price_rub IS
    'Суммарная стоимость сегментов (price_rub) по всем рейсам за день и flow_plan.';
