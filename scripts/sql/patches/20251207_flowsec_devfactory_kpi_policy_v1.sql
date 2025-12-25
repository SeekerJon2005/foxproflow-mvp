-- 20251207_flowsec_devfactory_kpi_policy_v1.sql
-- NDC-патч: политика FlowSec для просмотра KPI DevFactory.
-- stack=sql-postgres
-- goal=Ввести devfactory_view_kpi и привязать её к ролям
--       architect/devfactory_core/devfactory_external_operator/foxshell_operator.

-------------------------------
-- 0. Базовые проверки
-------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'sec'
    ) THEN
        RAISE EXCEPTION 'Schema sec does not exist. Apply 20251206_sec_core_v1.sql first.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'sec' AND table_name = 'policies'
    ) THEN
        RAISE EXCEPTION 'sec.policies does not exist.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
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
-- 2. Политика devfactory_view_kpi
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
    'devfactory_view_kpi',
    'DevFactory: просмотр KPI',
    'Разрешает просмотр агрегированных KPI DevFactory (витрина analytics.devfactory_task_kpi_v2, UI KPI dashboard).',
    'devfactory',
    'allow',
    '{}'::jsonb,
    true,
    'devfactory',
    'view_kpi',
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
-- 3. Привязка политики к ролям
-------------------------------

INSERT INTO sec.role_policy_bindings (role_code, policy_code)
VALUES
    ('architect',                    'devfactory_view_kpi'),
    ('devfactory_core',              'devfactory_view_kpi'),
    ('devfactory_external_operator', 'devfactory_view_kpi'),
    ('foxshell_operator',            'devfactory_view_kpi')
ON CONFLICT (role_code, policy_code) DO NOTHING;

-------------------------------
-- 4. Быстрые проверки (для отладки, не выполняются автоматически)
-------------------------------
-- SELECT * FROM sec.policies
--  WHERE policy_code = 'devfactory_view_kpi';
--
-- SELECT *
--   FROM sec.role_policy_bindings
--  WHERE policy_code = 'devfactory_view_kpi';
