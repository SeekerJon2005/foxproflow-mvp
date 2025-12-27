-- 20251203_crm_trial_accounts_overview_v.sql
-- Витрина активных и недавно истёкших trial-аккаунтов.
-- NDC-патч: создаём представление только если его ещё нет.
-- Источник данных: crm.account_overview_v (trial_until_v2 / trial_ends_at_v1).

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'crm'
          AND c.relkind = 'v'
          AND c.relname = 'trial_accounts_overview_v'
    ) THEN

        CREATE VIEW crm.trial_accounts_overview_v AS
        WITH trial_base AS (
            SELECT
                ao.account_id,
                ao.company_name,
                ao.product_code,
                ao.plan_code,
                COALESCE(ao.trial_until_v2, ao.trial_ends_at_v1) AS trial_until
            FROM crm.account_overview_v AS ao
            WHERE COALESCE(ao.trial_until_v2, ao.trial_ends_at_v1) IS NOT NULL
        )
        SELECT
            b.account_id,
            b.company_name,
            b.product_code,
            b.plan_code,
            b.trial_until,
            -- Просрочен ли trial по дате (true, если дата trial уже в прошлом)
            (b.trial_until::date < CURRENT_DATE) AS is_expired,
            -- Семантический статус trial
            CASE
                WHEN b.trial_until IS NULL THEN 'none'
                WHEN b.trial_until::date < CURRENT_DATE THEN 'expired'
                WHEN b.trial_until::date <= CURRENT_DATE + 3 THEN 'expiring_soon'
                ELSE 'active'
            END AS trial_status,
            -- Количество дней до конца trial (0, если уже истёк)
            GREATEST(
                0,
                (b.trial_until::date - CURRENT_DATE)
            ) AS days_left
        FROM trial_base AS b;

        COMMENT ON VIEW crm.trial_accounts_overview_v IS
            'Текущие trial-аккаунты FoxProFlow (по account_overview_v): дата окончания trial, статус (active/expiring_soon/expired), признак просрочки и количество дней до конца.';
    END IF;
END;
$$ LANGUAGE plpgsql;
