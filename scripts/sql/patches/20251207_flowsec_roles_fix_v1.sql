-- 20251207_flowsec_roles_fix_v1.sql
-- NDC-патч: доводим sec.roles до схемы, ожидаемой 20251206_sec_core_v1.sql.
-- Добавляем колонку is_system, если её нет.

DO $$
BEGIN
    -- Если таблицы sec.roles нет, выходим: её создаст sec_core_v1
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'roles'
    ) THEN
        RETURN;
    END IF;

    -- is_system boolean NOT NULL DEFAULT false
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'roles'
      AND column_name  = 'is_system';
    IF NOT FOUND THEN
        EXECUTE 'ALTER TABLE sec.roles ADD COLUMN is_system boolean NOT NULL DEFAULT false';
    END IF;
END;
$$ LANGUAGE plpgsql;
