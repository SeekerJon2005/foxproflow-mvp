-- 20251203_crm_leads_trial_candidates_v.sql
-- Витрина лидов, готовых к автозапуску trial SalesFox-агентом.
-- NDC-патч: создаём представление только если его ещё нет.

DO $$
BEGIN
    -- Проверяем, что представление ещё не создано
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'crm'
          AND c.relkind = 'v'
          AND c.relname = 'leads_trial_candidates_v'
    ) THEN
        CREATE VIEW crm.leads_trial_candidates_v AS
        SELECT
            l.id            AS lead_id,
            l.company_name,
            l.status,
            l.payload,
            l.created_at
        FROM crm.leads AS l
        WHERE l.status = 'ready_for_trial';

        COMMENT ON VIEW crm.leads_trial_candidates_v IS
            'Лиды со статусом ready_for_trial для SalesFox-агента, который запускает crm.fn_lead_win_trial_and_onboarding.';
    END IF;
END;
$$ LANGUAGE plpgsql;
