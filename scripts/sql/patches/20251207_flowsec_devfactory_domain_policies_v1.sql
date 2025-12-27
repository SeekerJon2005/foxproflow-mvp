-- 20251207_flowsec_devfactory_domain_policies_v1.sql
-- NDC-патч: базовые доменные политики FlowSec для devfactory (tasks).
-- stack=sql-postgres
-- goal=Ввести политики devfactory_view_tasks и devfactory_manage_tasks
--      и привязать их к ключевым ролям (architect, devfactory_core,
--      devfactory_external_operator, foxshell_operator).

-------------------------------
-- 0. Базовые проверки
-------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'sec'
    ) THEN
        RAISE EXCEPTION 'Schema sec does not exist. Apply sec_core patch first.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec' AND table_name = 'policies'
    ) THEN
        RAISE EXCEPTION 'sec.policies does not exist.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'sec' AND table_name = 'role_policy_bindings'
    ) THEN
        RAISE EXCEPTION 'sec.role_policy_bindings does not exist.';
    END IF;
END
$$;

-------------------------------
-- 1. Гарантируем колонки domain/action/decision
-------------------------------

DO $$
BEGIN
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'policies'
      AND column_name  = 'domain';
    IF NOT FOUND THEN
        ALTER TABLE sec.policies ADD COLUMN domain text;
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'policies'
      AND column_name  = 'action';
    IF NOT FOUND THEN
        ALTER TABLE sec.policies ADD COLUMN action text;
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec'
      AND table_name   = 'policies'
      AND column_name  = 'decision';
    IF NOT FOUND THEN
        ALTER TABLE sec.policies ADD COLUMN decision text;
    END IF;
END
$$;

-------------------------------
-- 2. Политика devfactory_view_tasks
-------------------------------

INSERT INTO sec.policies (
    policy_code,
    title,
    description,
    target_domain,
    effect,
    condition,
    is_active,
    domain,
    action,
    decision
)
VALUES (
    'devfactory_view_tasks',
    'DevFactory: просмотр задач',
    'Разрешает просмотр задач DevFactory (dev.dev_task) и связанных витрин/контекстов.',
    'devfactory',
    'allow',
    '{}'::jsonb,
    true,
    'devfactory',
    'view_tasks',
    'allow'
)
ON CONFLICT (policy_code) DO UPDATE
SET
    title         = EXCLUDED.title,
    description   = EXCLUDED.description,
    target_domain = EXCLUDED.target_domain,
    effect        = EXCLUDED.effect,
    condition     = EXCLUDED.condition,
    is_active     = EXCLUDED.is_active,
    domain        = EXCLUDED.domain,
    action        = EXCLUDED.action,
    decision      = EXCLUDED.decision;

-------------------------------
-- 3. Политика devfactory_manage_tasks
-------------------------------

INSERT INTO sec.policies (
    policy_code,
    title,
    description,
    target_domain,
    effect,
    condition,
    is_active,
    domain,
    action,
    decision
)
VALUES (
    'devfactory_manage_tasks',
    'DevFactory: управление задачами',
    'Разрешает создание, обновление и управление задачами DevFactory (dev.dev_task), включая изменение статусов и result_spec.',
    'devfactory',
    'allow',
    '{}'::jsonb,
    true,
    'devfactory',
    'manage_tasks',
    'allow'
)
ON CONFLICT (policy_code) DO UPDATE
SET
    title         = EXCLUDED.title,
    description   = EXCLUDED.description,
    target_domain = EXCLUDED.target_domain,
    effect        = EXCLUDED.effect,
    condition     = EXCLUDED.condition,
    is_active     = EXCLUDED.is_active,
    domain        = EXCLUDED.domain,
    action        = EXCLUDED.action,
    decision      = EXCLUDED.decision;

-------------------------------
-- 4. Привязка политик к ролям
-------------------------------

-- Просмотр задач DevFactory
INSERT INTO sec.role_policy_bindings (role_code, policy_code)
VALUES
    ('architect',                    'devfactory_view_tasks'),
    ('devfactory_core',              'devfactory_view_tasks'),
    ('devfactory_external_operator', 'devfactory_view_tasks'),
    ('foxshell_operator',            'devfactory_view_tasks')
ON CONFLICT (role_code, policy_code) DO NOTHING;

-- Управление задачами DevFactory (ограниченный круг)
INSERT INTO sec.role_policy_bindings (role_code, policy_code)
VALUES
    ('architect',       'devfactory_manage_tasks'),
    ('devfactory_core', 'devfactory_manage_tasks')
ON CONFLICT (role_code, policy_code) DO NOTHING;

-------------------------------
-- 5. Быстрые проверки (для ручного запуска)
-------------------------------
-- SELECT policy_code, domain, action, decision, is_active
--   FROM sec.policies
--  WHERE policy_code IN ('devfactory_view_tasks', 'devfactory_manage_tasks');
--
-- SELECT role_code, policy_code
--   FROM sec.role_policy_bindings
--  WHERE policy_code IN ('devfactory_view_tasks', 'devfactory_manage_tasks')
--  ORDER BY role_code, policy_code;
