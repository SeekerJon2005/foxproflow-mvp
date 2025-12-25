-- 20251208_flowsec_policies_fix_v1.sql
-- NDC-патч: доводим sec.policies до схемы, ожидаемой FlowSec core.
-- Добавляем колонку decision, если её нет.

DO $$
BEGIN
    -- Если таблицы sec.policies нет, выходим:
    -- её создаёт 20251206_sec_core_v1.sql.
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'policies'
    ) THEN
        RETURN;
    END IF;

    -- Колонка decision text NOT NULL DEFAULT 'allow'
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'policies'
      AND column_name  = 'decision';
    IF NOT FOUND THEN
        EXECUTE '
            ALTER TABLE sec.policies
            ADD COLUMN decision text NOT NULL DEFAULT ''allow'';
        ';
    END IF;
END;
$$ LANGUAGE plpgsql;
