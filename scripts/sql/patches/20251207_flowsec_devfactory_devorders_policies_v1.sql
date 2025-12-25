-- 20251207_flowsec_devfactory_devorders_policies_v1.sql
-- NDC-патч: политики FlowSec для DevOrders в домене devfactory.
-- stack=sql-postgres
-- goal=Ввести devfactory_view_orders и devfactory_manage_orders
--      и привязать их к ключевым ролям.

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
-- 2. Политика devfactory_view_orders
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
    'devfactory_view_orders',
    'DevFactory: просмотр DevOrders',
    'Разрешает просмотр DevOrders (/api/devorders*, dev.dev_order, dev.v_dev_order_commercial_ctx).',
    'devfactory',
    'allow',
    '{}'::jsonb,
    true,
    'devfactory',
    'view_orders',
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
-- 3. Политика devfactory_manage_orders
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
    'devfactory_manage_orders',
    'DevFactory: управление DevOrders',
    'Разрешает управление DevOrders (создание/изменение, линковки с billing/CRM/tenant).',
    'devfactory',
    'allow',
    '{}'::jsonb,
    true,
    'devfactory',
    'manage_orders',
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

-- Просмотр DevOrders
INSERT INTO sec.role_policy_bindings (role_code, policy_code)
VALUES
    ('architect',                    'devfactory_view_orders'),
    ('devfactory_core',              'devfactory_view_orders'),
    ('devfactory_external_operator', 'devfactory_view_orders'),
    ('foxshell_operator',            'devfactory_view_orders')
ON CONFLICT (role_code, policy_code) DO NOTHING;

-- Управление DevOrders (ограниченный круг)
INSERT INTO sec.role_policy_bindings (role_code, policy_code)
VALUES
    ('architect',       'devfactory_manage_orders'),
    ('devfactory_core', 'devfactory_manage_orders')
ON CONFLICT (role_code, policy_code) DO NOTHING;

-------------------------------
-- 5. Быстрые проверки (для ручного запуска)
-------------------------------
-- SELECT policy_code, domain, action, decision, is_active
--   FROM sec.policies
--  WHERE policy_code IN ('devfactory_view_orders', 'devfactory_manage_orders');
--
-- SELECT role_code, policy_code
--   FROM sec.role_policy_bindings
--  WHERE policy_code IN ('devfactory_view_orders', 'devfactory_manage_orders')
--  ORDER BY role_code, policy_code;
