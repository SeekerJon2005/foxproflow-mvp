-- 20251206_flowsec_devfactory_policies_v1.sql
-- NDC-патч: политики FlowSec для домена devfactory + биндинг к ролям.
-- goal=Определить разрешающие политики для DevFactory/DevOrders и привязать их к architect/devfactory_core/devfactory_external_operator.
-- summary=FlowSec: домен devfactory — просмотр/контекст/линковки заказов DevFactory.

-------------------------------
-- 0. Проверка наличия схемы sec
-------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'sec'
    ) THEN
        RAISE EXCEPTION 'Schema sec does not exist. Apply sec_core_v1.sql first.';
    END IF;
END
$$;

-------------------------------
-- 1. (Опционально) гарантируем наличие нужных колонок в sec.policies
--    На твоей схеме они уже есть, но IF NOT EXISTS не повредит.
-------------------------------

DO $$
BEGIN
    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'policies' AND column_name = 'domain';

    IF NOT FOUND THEN
        ALTER TABLE sec.policies ADD COLUMN domain text;
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'policies' AND column_name = 'action';

    IF NOT FOUND THEN
        ALTER TABLE sec.policies ADD COLUMN action text;
    END IF;

    PERFORM 1
    FROM information_schema.columns
    WHERE table_schema = 'sec' AND table_name = 'policies' AND column_name = 'decision';

    IF NOT FOUND THEN
        ALTER TABLE sec.policies ADD COLUMN decision text;
    END IF;
END
$$;

-------------------------------
-- 2. Добавляем/обновляем политики для домена devfactory
-------------------------------
-- Структура sec.policies по факту:
--   policy_code   text      NOT NULL
--   title         text      NOT NULL
--   description   text      NULL
--   target_domain text      NOT NULL
--   effect        text      NOT NULL
--   condition     jsonb     NOT NULL
--   is_active     boolean   NOT NULL
--   created_at    timestamptz NOT NULL (есть default NOW())
--   domain        text      NULL
--   action        text      NULL
--   decision      text      NULL

-- Политики:
--  - devfactory_view_orders        : просмотр списка dev-заказов
--  - devfactory_view_order_ctx     : просмотр коммерческого контекста dev-заказов
--  - devfactory_link_order_tenant  : привязка dev-заказа к CRM-tenant
--  - devfactory_link_order_billing : привязка dev-заказа к Billing (subscription/invoice)
--  - devfactory_link_order_lead    : привязка dev-заказа к CRM-лиду

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
VALUES
    (
        'devfactory_view_orders',
        'DevFactory: просмотр заказов',
        'Просмотр списка dev-заказов DevFactory',
        'devfactory',
        'allow',
        '{}'::jsonb,
        true,
        'devfactory',
        'view_orders',
        'allow'
    ),
    (
        'devfactory_view_order_ctx',
        'DevFactory: коммерческий контекст заказа',
        'Просмотр коммерческого контекста dev-заказов (CRM/Billing)',
        'devfactory',
        'allow',
        '{}'::jsonb,
        true,
        'devfactory',
        'view_order_ctx',
        'allow'
    ),
    (
        'devfactory_link_order_tenant',
        'DevFactory: привязка к tenant',
        'Привязка dev-заказа к CRM-tenant (crm.tenant.id)',
        'devfactory',
        'allow',
        '{}'::jsonb,
        true,
        'devfactory',
        'link_order_tenant',
        'allow'
    ),
    (
        'devfactory_link_order_billing',
        'DevFactory: привязка к Billing',
        'Привязка dev-заказа к Billing (subscription/invoice)',
        'devfactory',
        'allow',
        '{}'::jsonb,
        true,
        'devfactory',
        'link_order_billing',
        'allow'
    ),
    (
        'devfactory_link_order_lead',
        'DevFactory: привязка к CRM-лиду',
        'Привязка dev-заказа к CRM-лиду по внешнему коду',
        'devfactory',
        'allow',
        '{}'::jsonb,
        true,
        'devfactory',
        'link_order_lead',
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
-- 3. Привязка политик к ролям через role_code/policy_code
-------------------------------
-- Структура sec.roles:
--   role_code text NOT NULL
--   title     text NOT NULL
--   ...

-- Структура sec.role_policy_bindings:
--   role_code   text NOT NULL
--   policy_code text NOT NULL
--   granted_at  timestamptz NOT NULL
--   granted_by  text NULL

-- architect / devfactory_core      : полный доступ к devorders
-- devfactory_external_operator     : только просмотр списка/контекста

-- architect + devfactory_core: полный набор
WITH rp AS (
    SELECT r.role_code, p.policy_code
    FROM sec.roles r
    JOIN sec.policies p
      ON p.policy_code IN (
          'devfactory_view_orders',
          'devfactory_view_order_ctx',
          'devfactory_link_order_tenant',
          'devfactory_link_order_billing',
          'devfactory_link_order_lead'
      )
    WHERE r.role_code IN ('architect', 'devfactory_core')
)
INSERT INTO sec.role_policy_bindings (role_code, policy_code, granted_at, granted_by)
SELECT
    rp.role_code,
    rp.policy_code,
    now() AS granted_at,
    'system:patch_20251206_flowsec_devfactory' AS granted_by
FROM rp
WHERE NOT EXISTS (
    SELECT 1
    FROM sec.role_policy_bindings b
    WHERE b.role_code   = rp.role_code
      AND b.policy_code = rp.policy_code
);

-- devfactory_external_operator: только просмотр (view_*), без линковок
WITH rp AS (
    SELECT r.role_code, p.policy_code
    FROM sec.roles r
    JOIN sec.policies p
      ON p.policy_code IN (
          'devfactory_view_orders',
          'devfactory_view_order_ctx'
      )
    WHERE r.role_code = 'devfactory_external_operator'
)
INSERT INTO sec.role_policy_bindings (role_code, policy_code, granted_at, granted_by)
SELECT
    rp.role_code,
    rp.policy_code,
    now() AS granted_at,
    'system:patch_20251206_flowsec_devfactory' AS granted_by
FROM rp
WHERE NOT EXISTS (
    SELECT 1
    FROM sec.role_policy_bindings b
    WHERE b.role_code   = rp.role_code
      AND b.policy_code = rp.policy_code
);
