-- 20251206_flowsec_seed_architect_subject.sql
-- NDC-патч: назначить роль architect субъекту e.yatskov@foxproflow.ru.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec'
          AND table_name   = 'subject_roles'
    ) THEN
        RAISE EXCEPTION 'sec.subject_roles does not exist';
    END IF;
END
$$;

-- Гарантируем базовые колонки (на случай очень старой схемы)
DO $$
BEGIN
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'subject_roles' AND column_name = 'subject_type';
    IF NOT FOUND THEN
        ALTER TABLE sec.subject_roles ADD COLUMN subject_type text;
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'subject_roles' AND column_name = 'subject_id';
    IF NOT FOUND THEN
        ALTER TABLE sec.subject_roles ADD COLUMN subject_id text;
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'subject_roles' AND column_name = 'role_code';
    IF NOT FOUND THEN
        ALTER TABLE sec.subject_roles ADD COLUMN role_code text;
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'subject_roles' AND column_name = 'is_active';
    IF NOT FOUND THEN
        ALTER TABLE sec.subject_roles ADD COLUMN is_active boolean DEFAULT true;
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'subject_roles' AND column_name = 'assigned_at';
    IF NOT FOUND THEN
        ALTER TABLE sec.subject_roles ADD COLUMN assigned_at timestamptz DEFAULT now();
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'subject_roles' AND column_name = 'assigned_by';
    IF NOT FOUND THEN
        ALTER TABLE sec.subject_roles ADD COLUMN assigned_by text;
    END IF;
END
$$;

-- Назначаем роль architect субъекту e.yatskov@foxproflow.ru (user)
INSERT INTO sec.subject_roles (subject_type, subject_id, role_code, is_active, assigned_at, assigned_by)
SELECT
    'user'                        AS subject_type,
    'e.yatskov@foxproflow.ru'     AS subject_id,
    'architect'                   AS role_code,
    true                          AS is_active,
    now()                         AS assigned_at,
    'system:patch_20251206_seed_architect' AS assigned_by
WHERE NOT EXISTS (
    SELECT 1
    FROM sec.subject_roles sr
    WHERE sr.subject_type = 'user'
      AND sr.subject_id   = 'e.yatskov@foxproflow.ru'
      AND sr.role_code    = 'architect'
      AND sr.is_active    = true
);
