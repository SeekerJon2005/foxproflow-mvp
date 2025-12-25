-- 20251208_flowsec_policies_fix_action_v1.sql
-- NDC-патч: добавляем колонку action в sec.policies для совместимости
-- с кодом FlowSec, который обращается к p.action.

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

    -- Добавляем колонку action text NOT NULL DEFAULT '*', если её ещё нет.
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'policies'
      AND column_name  = 'action';
    IF NOT FOUND THEN
        EXECUTE '
            ALTER TABLE sec.policies
            ADD COLUMN action text NOT NULL DEFAULT ''*'';
        ';
    END IF;
END;
$$ LANGUAGE plpgsql;
