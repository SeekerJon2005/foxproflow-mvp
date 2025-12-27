-- 20251208_flowsec_policies_fix_domain_v1.sql
-- NDC-патч: добавляем колонку domain в sec.policies для совместимости
-- с кодом FlowSec, который обращается к p.domain.

DO $$
BEGIN
    -- Если таблицы sec.policies нет — выходим, её создаёт sec_core_v1.
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'policies'
    ) THEN
        RETURN;
    END IF;

    -- Добавляем колонку domain, если её ещё нет.
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'policies'
      AND column_name  = 'domain';
    IF NOT FOUND THEN
        EXECUTE 'ALTER TABLE sec.policies ADD COLUMN domain text';
        -- Заполняем существующие записи по target_domain
        EXECUTE 'UPDATE sec.policies SET domain = target_domain';
    END IF;
END;
$$ LANGUAGE plpgsql;
