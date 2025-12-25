-- 20251210_logistics_autoplan_engine_stub_v1.sql
-- NDC: добавляет stub-движок автоплана в БД.
-- Реального планирования пока нет, только "каркас" и JSON-ответ.

CREATE SCHEMA IF NOT EXISTS logistics;

CREATE OR REPLACE FUNCTION logistics.logistics_apply_autoplan(
    p_date   date,
    p_window text DEFAULT 'day'
)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN jsonb_build_object(
        'ok', true,
        'mode', 'autoplan_db_stub',
        'date', to_char(p_date, 'YYYY-MM-DD'),
        'window', COALESCE(NULLIF(p_window, ''), 'day'),
        'summary', jsonb_build_object(
            'note', 'DB-level stub; real Rolling Horizon engine is not implemented yet'
        )
    );
END;
$$;
