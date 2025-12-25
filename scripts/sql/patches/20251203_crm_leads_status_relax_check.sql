-- 20251203_crm_leads_status_relax_check.sql
-- Ослабляем CHECK для crm.leads.status:
-- вместо жёсткого списка значений разрешаем любой непустой статус.
-- Патч идемпотентен: можно выполнять несколько раз.

DO $$
BEGIN
    -- Если старый constraint существует — снимаем его
    IF EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t      ON c.conrelid = t.oid
        JOIN pg_namespace n  ON t.relnamespace = n.oid
        WHERE n.nspname = 'crm'
          AND t.relname = 'leads'
          AND c.conname = 'leads_status_check'
    ) THEN
        ALTER TABLE crm.leads
            DROP CONSTRAINT leads_status_check;
    END IF;

    -- Ставим более мягкий CHECK: статус просто должен быть непустой строкой
    ALTER TABLE crm.leads
        ADD CONSTRAINT leads_status_check
        CHECK (status IS NOT NULL AND length(status) > 0);
END;
$$ LANGUAGE plpgsql;
