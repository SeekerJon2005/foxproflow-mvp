-- 20251207_flowsec_subject_roles_fix_v1.sql
-- NDC-патч: доводим sec.subject_roles до схемы, ожидаемой 20251206_sec_core_v1.sql.
-- Добавляем tenant_id, assigned_at, assigned_by, если их нет.

DO $$
BEGIN
    -- Если таблицы sec.subject_roles нет, просто выходим: её создаст sec_core_v1
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'subject_roles'
    ) THEN
        RETURN;
    END IF;

    -- tenant_id text
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'subject_roles'
      AND column_name  = 'tenant_id';
    IF NOT FOUND THEN
        EXECUTE 'ALTER TABLE sec.subject_roles ADD COLUMN tenant_id text';
    END IF;

    -- assigned_at timestamptz NOT NULL DEFAULT now()
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'subject_roles'
      AND column_name  = 'assigned_at';
    IF NOT FOUND THEN
        EXECUTE 'ALTER TABLE sec.subject_roles ADD COLUMN assigned_at timestamptz NOT NULL DEFAULT now()';
    END IF;

    -- assigned_by text
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'subject_roles'
      AND column_name  = 'assigned_by';
    IF NOT FOUND THEN
        EXECUTE 'ALTER TABLE sec.subject_roles ADD COLUMN assigned_by text';
    END IF;
END;
$$ LANGUAGE plpgsql;
