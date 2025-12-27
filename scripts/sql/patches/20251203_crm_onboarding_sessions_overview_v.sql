-- 20251203_crm_onboarding_sessions_overview_v.sql
-- Витрина по онбординг-сессиям: прогресс по шагам, блокировки, проценты.
-- NDC-патч: создаём представление только если его ещё нет.
-- Источник данных: crm.onboarding_sessions (id, account_id, status, created_at, updated_at, steps jsonb).

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'crm'
          AND c.relkind = 'v'
          AND c.relname = 'onboarding_sessions_overview_v'
    ) THEN

        CREATE VIEW crm.onboarding_sessions_overview_v AS
        WITH step_elems AS (
            SELECT
                s.id AS onboarding_id,
                e ->> 'status'       AS status,
                e ->> 'step_code'    AS step_code,
                NULLIF(e ->> 'updated_at', '')::timestamptz AS step_updated_at
            FROM crm.onboarding_sessions AS s
            LEFT JOIN LATERAL jsonb_array_elements(s.steps) AS e ON true
        )
        SELECT
            s.id         AS onboarding_id,
            s.account_id,
            s.status,
            s.created_at,
            s.updated_at,

            -- Общее количество шагов
            COALESCE(jsonb_array_length(s.steps), 0) AS total_steps,

            -- Шаги со статусом done
            COUNT(*) FILTER (WHERE se.status = 'done') AS done_steps,

            -- Шаги со статусом in_progress
            COUNT(*) FILTER (WHERE se.status = 'in_progress') AS in_progress_steps,

            -- Шаги со статусом blocked
            COUNT(*) FILTER (WHERE se.status = 'blocked') AS blocked_steps,

            -- Есть ли вообще заблокированные шаги
            (
                COUNT(*) FILTER (WHERE se.status = 'blocked') > 0
            ) AS has_blocked,

            -- Количество "открытых" шагов (не done)
            GREATEST(
                0,
                COALESCE(jsonb_array_length(s.steps), 0)
                - COUNT(*) FILTER (WHERE se.status = 'done')
            ) AS open_steps,

            -- Процент завершения (done / total * 100)
            CASE
                WHEN COALESCE(jsonb_array_length(s.steps), 0) = 0 THEN 0.0
                ELSE ROUND(
                    100.0 * COUNT(*) FILTER (WHERE se.status = 'done')::numeric
                    / NULLIF(jsonb_array_length(s.steps), 0),
                    1
                )
            END AS done_pct,

            -- Последний шаг по порядку в массиве steps
            CASE
                WHEN COALESCE(jsonb_array_length(s.steps), 0) = 0 THEN NULL
                ELSE (s.steps -> (jsonb_array_length(s.steps) - 1)) ->> 'step_code'
            END AS last_step_code,

            -- Время последнего обновления любого шага (по шагам)
            MAX(se.step_updated_at) AS last_step_updated_at,

            -- Массив кодов заблокированных шагов (может быть пустым)
            COALESCE(
                ARRAY_AGG(se.step_code) FILTER (WHERE se.status = 'blocked'),
                ARRAY[]::text[]
            ) AS blocked_step_codes

        FROM crm.onboarding_sessions AS s
        LEFT JOIN step_elems AS se
            ON se.onboarding_id = s.id
        GROUP BY
            s.id,
            s.account_id,
            s.status,
            s.created_at,
            s.updated_at,
            s.steps;

        COMMENT ON VIEW crm.onboarding_sessions_overview_v IS
            'Прогресс онбординга по сессиям: количество шагов, done/in_progress/blocked, наличие блокировок, открытые шаги, процент завершения, последний шаг и список заблокированных шагов.';
    END IF;
END;
$$ LANGUAGE plpgsql;
